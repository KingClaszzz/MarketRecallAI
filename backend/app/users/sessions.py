"""Prediction sessions. One credit opens one asset in one of two modes:

  own    the user locks a call first, then sees the model's reading
  model  the user sees the reading first and may then lock a call

Both include follow-up questions answered from the session's data and the user's Walrus history.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import update
from sqlmodel import desc, select

from app.agent import agent
from app.config import get_settings
from app.data.validation import HOUR_MS
from app.db import ChatMessage, Forecast, Pick, PredictSession, get_session
from app.live import engine
from app.memory import formats, store
from app.users import credits, picks

MODES = {"own", "model"}
MAX_MESSAGES = 10
SESSION_TTL = timedelta(hours=24)
MAX_READING_AGE_H = 2  # refuse to charge for an older reading


class SessionError(Exception):
    pass


def _clock(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%b %d %H:%M UTC")


def _window(t: int) -> str:
    end = t + get_settings().forecast_horizon_h * HOUR_MS
    return f"{_clock(t)} to {datetime.fromtimestamp(end / 1000, tz=timezone.utc).strftime('%H:%M UTC')}"


def latest_forecast(asset: str) -> Forecast | None:
    with get_session() as session:
        return session.exec(
            select(Forecast).where(Forecast.asset == asset, Forecast.source == "live").order_by(desc(Forecast.t)).limit(1)
        ).first()


def _forecast_at(asset: str, t: int) -> Forecast | None:
    with get_session() as session:
        return session.exec(select(Forecast).where(Forecast.asset == asset, Forecast.t == t, Forecast.source == "live")).first()


def _empty() -> dict:
    return {"calls": 0, "right": 0, "agreed_calls": 0, "agreed_right": 0, "disagreed_calls": 0, "disagreed_right": 0}


def personal_record(address: str, asset: str | None = None) -> dict:
    """Aggregate the user's USER_EPISODE memories from Walrus."""
    memories = store.recall(picks.user_namespace(address), "[USER_EPISODE] call outcome", limit=100)
    total, by_vol, by_mode = _empty(), defaultdict(_empty), defaultdict(_empty)
    blobs = []
    for m in memories:
        data = formats.parse_data(m["text"])
        if not data or data.get("type") != "user_episode" or (asset and data["asset"] != asset):
            continue
        blobs.append(m["blob_id"])
        right = data["result"] == "WON"
        model = data.get("model") or {}
        agreed = model.get("agreed")
        vol = (data.get("regime") or {}).get("vol", "unknown")
        for bucket in (total, by_vol[vol], by_mode[data.get("mode", "own")]):
            bucket["calls"] += 1
            bucket["right"] += right
            if agreed is True:
                bucket["agreed_calls"] += 1
                bucket["agreed_right"] += right
            elif agreed is False:
                bucket["disagreed_calls"] += 1
                bucket["disagreed_right"] += right
    return {"asset": asset, "total": total, "by_volatility": dict(by_vol), "by_mode": dict(by_mode),
            "memory_blobs": blobs[:10]}


def open_session(address: str, asset: str, mode: str, direction: str | None = None) -> PredictSession:
    if mode not in MODES:
        raise SessionError("mode must be 'own' or 'model'")
    if mode == "own" and not direction:
        raise SessionError("make your call first: direction UP or DOWN")
    if direction is not None:
        direction = direction.upper()
        if direction not in picks.DIRECTIONS:
            raise SessionError("direction must be UP or DOWN")
    forecast = latest_forecast(asset)
    if forecast is None:
        raise LookupError(f"no {asset} reading yet")
    if forecast.t < picks.last_closed_hour() + HOUR_MS - (MAX_READING_AGE_H - 1) * HOUR_MS:
        raise LookupError(f"the latest {asset} reading is out of date; try again after the next hourly update")
    slot = picks.next_slot()
    if direction:
        with get_session() as session:
            if session.exec(select(Pick).where(Pick.address == address, Pick.asset == asset, Pick.slot_t == slot)).first():
                raise SessionError(f"you already have a {asset} call for this window")
    ref = {"asset": asset, "mode": mode, "forecast_id": forecast.id}
    credits.spend(address, credits.SESSION_COST, "session", ref)
    ps = None
    try:
        try:
            history = personal_record(address)
        except Exception as exc:
            history = {"error": f"walrus recall failed: {type(exc).__name__}"}
        try:
            context = engine.market_context(asset, forecast.t)
        except Exception as exc:
            context = {"error": type(exc).__name__}
        if forecast.trace.get("drivers"):
            context["drivers"] = forecast.trace["drivers"]
        ps = PredictSession(
            address=address, asset=asset, mode=mode, slot_t=slot, forecast_id=forecast.id,
            expires_at=datetime.now(timezone.utc) + SESSION_TTL, max_messages=MAX_MESSAGES, history=history,
            context=context,
        )
        with get_session() as session:
            session.add(ps)
            session.commit()
            session.refresh(ps)
        if mode == "own":
            pick = picks.place_pick(address, asset, direction, slot, session_id=ps.id, mode="own",
                                    model_p=forecast.recall_p, model_action=forecast.recall_action)
            ps = _attach_pick(ps.id, pick.id)
    except Exception:
        # a refunded session must not stay usable
        if ps is not None and ps.id is not None:
            with get_session() as session:
                row = session.get(PredictSession, ps.id)
                if row is not None:
                    session.delete(row)
                    session.commit()
        credits.grant(address, credits.SESSION_COST, "session_refund", ref)
        raise
    return ps


def _attach_pick(session_id: int, pick_id: int) -> PredictSession:
    with get_session() as session:
        ps = session.get(PredictSession, session_id)
        ps.pick_id = pick_id
        session.add(ps)
        session.commit()
        session.refresh(ps)
        return ps


def get_owned(address: str, session_id: int) -> PredictSession:
    with get_session() as session:
        ps = session.get(PredictSession, session_id)
    if ps is None or ps.address != address:
        raise LookupError("session not found")
    return ps


def lock_call(address: str, session_id: int, direction: str) -> PredictSession:
    ps = get_owned(address, session_id)
    if ps.pick_id is not None:
        raise SessionError("this session already has a call")
    forecast = _forecast(ps)
    pick = picks.place_pick(address, ps.asset, direction, ps.slot_t, session_id=ps.id, mode=ps.mode,
                            model_p=forecast.recall_p if forecast else None,
                            model_action=forecast.recall_action if forecast else None)
    return _attach_pick(ps.id, pick.id)


def _forecast(ps: PredictSession) -> Forecast | None:
    with get_session() as session:
        return session.get(Forecast, ps.forecast_id)


def _reading(f: Forecast) -> dict:
    d = f.trace.get("decision", {})
    lean = ("NO_CALL" if f.recall_action == "NO_CALL" else "NEUTRAL" if abs(f.recall_p - 0.5) < 0.005
            else "UP" if f.recall_p > 0.5 else "DOWN_OR_FLAT")
    out = {
        "made_at": _clock(f.t), "window": _window(f.t), "price_at_reading": f.close_at_t,
        "amnesiac_p_up": round(f.amnesiac_p, 2), "recall_p_up": round(f.recall_p, 2), "action": f.recall_action,
        "lean": lean, "voice": d.get("voice"), "policy_reasons": d.get("reasons", []),
        "similar_episodes": d.get("n_matched", 0), "regime_level_matched": d.get("level"),
        "credibility_in_similar_markets": {
            v: {k: round(x, 3) for k, x in c.items()} for v, c in d.get("credibility", {}).items()
        },
        "voices": {v: {"p_up": round(p, 2), "leans": "UP" if p > 0.505 else "DOWN" if p < 0.495 else "NEUTRAL"}
                   for v, p in f.voices.items()},
        "status": f.status,
    }
    if f.status == "RESOLVED":
        out["outcome"] = "UP" if f.label == 1 else "DOWN_OR_FLAT"
        out["price_at_window_end"] = f.close_at_resolve
    return out


def _live_record(asset: str) -> dict:
    with get_session() as session:
        rows = session.exec(
            select(Forecast).where(Forecast.asset == asset, Forecast.source == "live", Forecast.status == "RESOLVED")
        ).all()
    if not rows:
        return {"resolved": 0}
    called = [f for f in rows if f.recall_action != "NO_CALL"]
    return {
        "resolved": len(rows),
        "recall_brier": round(sum(f.recall_brier for f in rows) / len(rows), 4),
        "amnesiac_brier": round(sum(f.amnesiac_brier for f in rows) / len(rows), 4),
        "recall_direction_right": sum((f.recall_p > 0.5) == (f.label == 1) for f in called),
        "recall_calls": len(called),
    }


def build_facts(ps: PredictSession) -> dict:
    forecast = _forecast(ps)
    with get_session() as session:
        pick = session.get(Pick, ps.pick_id) if ps.pick_id else None
    facts: dict = {
        "asset": ps.asset,
        "session": {
            "mode": ps.mode, "your_window": _window(ps.slot_t), "calls_lock_at": _clock(ps.slot_t),
            "questions_left": ps.max_messages - ps.messages_used,
        },
        "your_call": None,
        "model_reading": _reading(forecast) if forecast else None,
        "regime": forecast.regime if forecast else None,
        "model_live_record": _live_record(ps.asset),
        "active_memory_rules": engine.lesson_status(ps.asset),
        "your_history": {k: v for k, v in ps.history.items() if k in ("total", "by_volatility", "by_mode", "error")},
    }
    if forecast:
        market = dict(ps.context)  # as of when the session opened
        facts["drivers"] = market.pop("drivers", [])
        facts["market"] = market
        evidence = forecast.trace.get("evidence", {})
        facts["memory_recalled_from_walrus"] = [e["text"] for e in evidence.get("credibility", []) + evidence.get("episodes", [])][:4]
    if pick:
        facts["your_call"] = {
            "direction": pick.direction, "status": pick.status, "made": pick.mode,
            "agrees_with_model": pick.agrees_with_model,
            "price_at_window_start": pick.close_at_t, "price_at_window_end": pick.close_at_resolve,
        }
    window_reading = _forecast_at(ps.asset, ps.slot_t)
    if window_reading and (forecast is None or window_reading.id != forecast.id):
        facts["model_reading_for_your_window"] = _reading(window_reading)
    others = {}
    for a in get_settings().assets:
        if a == ps.asset:
            continue
        f = latest_forecast(a)
        if f:
            others[a] = {"recall_p_up": round(f.recall_p, 2), "action": f.recall_action, "regime": f.regime}
    facts["other_assets"] = others
    return facts


def messages_of(session_id: int) -> list[ChatMessage]:
    with get_session() as session:
        return session.exec(select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.id)).all()


def message_out(m: ChatMessage) -> dict:
    """`problems` stays server-side."""
    return m.model_dump(exclude={"problems"})


def _replayable(messages: list[ChatMessage]) -> list[dict]:
    """Earlier turns for the LLM, minus refused questions and their refusals."""
    out = []
    for q, a in zip(messages[::2], messages[1::2]):
        if q.role != "user" or a.role != "assistant":
            continue
        if any(str(p).endswith(" request") for p in a.problems or []):
            continue
        out += [{"role": "user", "text": q.text}, {"role": "assistant", "text": a.text}]
    return out


def _reserve_question(session_id: int) -> None:
    """Atomically take one question from the session's allowance."""
    with get_session() as session:
        taken = session.execute(
            update(PredictSession)
            .where(PredictSession.id == session_id, PredictSession.messages_used < PredictSession.max_messages)
            .values(messages_used=PredictSession.messages_used + 1)
        ).rowcount
        session.commit()
    if not taken:
        raise SessionError("no questions left in this session")


def ask(address: str, session_id: int, question: str) -> dict:
    ps = get_owned(address, session_id)
    question = question.strip()
    if not question:
        raise SessionError("ask a question")
    if datetime.now(timezone.utc) > ps.expires_at.replace(tzinfo=ps.expires_at.tzinfo or timezone.utc):
        raise SessionError("this session has ended; open a new one")
    _reserve_question(ps.id)
    history = _replayable(messages_of(ps.id))
    answer = agent.session_answer(question, build_facts(ps), history)
    with get_session() as session:
        session.add(ChatMessage(session_id=ps.id, role="user", text=question[:1000]))
        reply = ChatMessage(session_id=ps.id, role="assistant", text=answer["text"], by=answer["by"],
                            problems=answer.get("llm_rejected", []))
        session.add(reply)
        session.commit()
        session.refresh(reply)
        ps = session.get(PredictSession, ps.id)
    return {"answer": message_out(reply), "questions_left": ps.max_messages - ps.messages_used}


def pick_out(pick: Pick | None) -> dict | None:
    return None if pick is None else pick.model_dump() | {"agrees_with_model": pick.agrees_with_model}


def view(ps: PredictSession) -> dict:
    forecast = _forecast(ps)
    with get_session() as session:
        pick = session.get(Pick, ps.pick_id) if ps.pick_id else None
    window_reading = _forecast_at(ps.asset, ps.slot_t)
    now = datetime.now(timezone.utc)
    expires = ps.expires_at.replace(tzinfo=ps.expires_at.tzinfo or timezone.utc)
    return {
        "session": ps,
        "forecast": forecast,
        "window_forecast": window_reading,
        "pick": pick_out(pick),
        "messages": [message_out(m) for m in messages_of(ps.id)],
        "questions_left": ps.max_messages - ps.messages_used,
        "can_call": pick is None and ps.slot_t > picks.last_closed_hour() + HOUR_MS,
        "active": now < expires and ps.messages_used < ps.max_messages,
    }


def list_sessions(address: str, limit: int = 20) -> list[dict]:
    with get_session() as session:
        rows = session.exec(
            select(PredictSession).where(PredictSession.address == address).order_by(desc(PredictSession.id)).limit(limit)
        ).all()
        picks_by_id = {p.id: p for p in session.exec(select(Pick).where(Pick.address == address)).all()}
    return [{"session": ps, "pick": pick_out(picks_by_id.get(ps.pick_id))} for ps in rows]
