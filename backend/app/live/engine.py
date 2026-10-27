"""Hourly loop: forecast, resolve, remember on Walrus, snapshot. Each asset has its own models and state."""
from __future__ import annotations

import logging
import time
from dataclasses import asdict
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sqlmodel import desc, select

from app.agent import agent
from app.backtest.walkforward import BacktestConfig, simulate_recall, voice_predictions
from app.config import get_settings
from app.data.collector import last_closed_hour
from app.data.validation import HOUR_MS
from app.db import Candle, Forecast, Lesson, Pick, PolicyState, get_session
from app.features.build import FEATURE_LABELS, PRICE_FEATURES, build_frame, load_candles, load_onchain
from app.features.regime import regime_of
from app.memory import formats, store
from app.models.voices import POLICY_VOICES, PRIMARY_VOICE, make_voices
from app.policy.gate import config_from_lessons, evaluate_rules
from app.policy.recall_policy import decide
from app.policy.stats import StatsBook
from app.users import picks

log = logging.getLogger(__name__)

TRAIN_WINDOW_H = 60 * 24
RETRAIN_EVERY_MS = 24 * HOUR_MS


class ModelRegistry:
    def __init__(self) -> None:
        self.voices: list = []
        self.fitted_at: int | None = None
        self.version = "untrained"

    def ensure_fitted(self, frame: pd.DataFrame, now: int) -> None:
        if self.fitted_at is not None and now - self.fitted_at < RETRAIN_EVERY_MS:
            return
        train = frame.dropna(subset=PRICE_FEATURES)
        train = train[(train["resolved_at"] <= now) & train["label"].notna() & (train.index > now - TRAIN_WINDOW_H * HOUR_MS)]
        voices = [v for v in make_voices(with_onchain=True) if v.name in POLICY_VOICES]
        for v in voices:
            v.fit(train)
        self.voices, self.fitted_at = voices, now
        self.version = f"v1@{formats.iso(now)}/n={len(train)}"


registries: dict[str, ModelRegistry] = {}


def registry(asset: str) -> ModelRegistry:
    return registries.setdefault(asset, ModelRegistry())


def now_ms() -> int:
    return int(time.time() * 1000)


def frame_for(asset: str) -> pd.DataFrame:
    return build_frame(load_candles(asset), load_onchain(), get_settings().forecast_horizon_h)


def latest_policy_state(asset: str) -> PolicyState | None:
    with get_session() as session:
        return session.exec(
            select(PolicyState).where(PolicyState.asset == asset).order_by(desc(PolicyState.id)).limit(1)
        ).first()


def current_book(asset: str) -> tuple[StatsBook, int]:
    state = latest_policy_state(asset)
    book = StatsBook.from_dict(state.book) if state else StatsBook()
    covers_until = state.covers_until if state else 0
    with get_session() as session:
        rows = session.exec(
            select(Forecast).where(
                Forecast.asset == asset, Forecast.status == "RESOLVED", Forecast.source == "live", Forecast.t > covers_until
            )
        ).all()
    for f in rows:
        book.add_episode(f.regime, f.voices, f.label)
        covers_until = max(covers_until, f.t)
    return book, covers_until


def lesson_status(asset: str) -> dict[str, str]:
    with get_session() as session:
        lessons = session.exec(select(Lesson).where(Lesson.asset == asset).order_by(Lesson.id)).all()
    return {lesson.rule: lesson.status for lesson in lessons}


def _evidence(asset: str, regime: dict) -> dict:
    query = f"{asset} 4h regime {formats.regime_text(regime)}"
    out = {"query": query}
    for name, ns in (("credibility", store.NS_CREDIBILITY), ("episodes", store.NS_EPISODES)):
        try:
            out[name] = [
                {"blob_id": m["blob_id"], "distance": m["distance"], "text": m["text"].split("\n", 1)[0][:240]}
                for m in store.recall(ns, query, limit=3)
                if m["text"].split(" ", 2)[1:2] == [asset]  # recall is semantic; keep this asset only
            ]
        except Exception as exc:
            out[f"{name}_error"] = f"{type(exc).__name__}: {exc}"[:200]
    return out


def community_voice(asset: str, t: int) -> float | None:
    """Laplace-smoothed share of user calls saying UP for slot t."""
    with get_session() as session:
        rows = session.exec(select(Pick.direction).where(Pick.asset == asset, Pick.slot_t == t)).all()
    if not rows:
        return None
    return (sum(d == "UP" for d in rows) + 1) / (len(rows) + 2)


def predict(asset: str, t: int, frame: pd.DataFrame | None = None) -> dict:
    """Amnesiac + Recall forecast at decision time t. Writes nothing."""
    frame = frame if frame is not None else frame_for(asset)
    if t not in frame.index or frame.loc[[t], PRICE_FEATURES].isna().any(axis=None):
        raise LookupError(f"{asset}: price data incomplete for {formats.iso(t)}")
    row = frame.loc[[t]]
    flags = ["onchain_missing"] if row[["tx_z_7d"]].isna().any(axis=None) else []
    reg = registry(asset)
    reg.ensure_fitted(frame, now_ms())
    probs = {v.name: float(v.predict(row)[0]) for v in reg.voices}
    crowd = community_voice(asset, t)
    if crowd is not None:
        probs["community"] = crowd
    regime = regime_of(row.iloc[0])
    book, _ = current_book(asset)
    policy = config_from_lessons(lesson_status(asset))
    decision = decide(regime, probs, book, PRIMARY_VOICE, policy)
    evidence = _evidence(asset, regime)
    if any(k.endswith("_error") for k in evidence):
        flags.append("walrus_recall_failed")
    return {
        "asset": asset, "t": t, "close": float(row["close"].iloc[0]), "voices": probs, "regime": regime,
        "decision": decision, "policy": policy, "book_episodes": book.episodes, "evidence": evidence,
        "flags": flags, "model_version": reg.version, "drivers": drivers(reg, row),
    }


def drivers(reg: ModelRegistry, row: pd.DataFrame, top: int = 4) -> list[dict]:
    primary = next((v for v in reg.voices if v.name == PRIMARY_VOICE), None)
    contrib = primary.contributions(row) if primary is not None and hasattr(primary, "contributions") else None
    if not contrib:
        return []
    contrib["time_of_day"] = contrib.pop("hour_sin", 0.0) + contrib.pop("hour_cos", 0.0)
    ranked = sorted(contrib.items(), key=lambda kv: abs(kv[1]), reverse=True)[:top]
    return [{"feature": FEATURE_LABELS.get(f, f), "pushes": "UP" if c > 0 else "DOWN", "weight": round(abs(c), 2)}
            for f, c in ranked]


def _pct(x) -> float | None:
    return None if x is None or pd.isna(x) else round(float(x) * 100, 2)


def _num(x, digits: int = 2) -> float | None:
    return None if x is None or pd.isna(x) else round(float(x), digits)


def market_context(asset: str, t: int) -> dict:
    frame = frame_for(asset)
    if t not in frame.index:
        return {}
    row = frame.loc[[t]]
    r = row.iloc[0]
    week_ago = t - 168 * HOUR_MS
    reg = registry(asset)
    reg.ensure_fitted(frame, now_ms())
    return {
        "price_at_reading": _num(r["close"], 6),
        "move_1h_pct": _pct(np.expm1(r["ret_1h"])), "move_4h_pct": _pct(np.expm1(r["ret_4h"])),
        "move_24h_pct": _pct(np.expm1(r["ret_24h"])),
        "move_7d_pct": _pct(r["close"] / frame.loc[week_ago, "close"] - 1) if week_ago in frame.index else None,
        "volatility_rank_30d_pct": _pct(r["vol_pct_30d"]),
        "rsi_14": _num(r["rsi_14"] * 100, 1),
        "vs_24h_average_pct": _pct(r["ema24_dist"]), "vs_72h_average_pct": _pct(r["ema72_dist"]),
        "volume_vs_week_z": _num(r["volume_z"]),
        "sui_activity_vs_week_z": _num(r.get("tx_z_7d")),
        "drivers": drivers(reg, row),
    }


def forecast_asset(asset: str) -> dict:
    s = get_settings()
    t = last_closed_hour() + HOUR_MS
    with get_session() as session:
        if session.exec(select(Forecast).where(Forecast.asset == asset, Forecast.t == t, Forecast.source == "live")).first():
            return {"skipped": "already forecast", "t": t}
    try:
        p = predict(asset, t)
    except LookupError as exc:
        return {"skipped": str(exc), "t": t}
    decision = p["decision"]
    explanation = agent.explain_decision(asdict(decision), p["regime"], p["voices"])
    forecast = Forecast(
        asset=asset, t=t, horizon_h=s.forecast_horizon_h, close_at_t=p["close"], voices=p["voices"],
        model_version=p["model_version"], regime=p["regime"], amnesiac_p=p["voices"][PRIMARY_VOICE],
        recall_p=decision.p, recall_action=decision.action, data_flags=p["flags"],
        trace={"decision": asdict(decision), "policy": asdict(p["policy"]), "book_episodes": p["book_episodes"],
               "evidence": p["evidence"], "explanation": explanation, "drivers": p["drivers"]},
    )
    with get_session() as session:
        session.add(forecast)
        session.commit()
        session.refresh(forecast)
    return {"t": t, "amnesiac_p": forecast.amnesiac_p, "recall_p": forecast.recall_p, "action": forecast.recall_action}


def close_of_candle(asset: str, open_time: int) -> float | None:
    with get_session() as session:
        c = session.exec(
            select(Candle).where(Candle.symbol == asset, Candle.open_time == open_time).order_by(Candle.source.desc())
        ).first()  # "tatum" sorts after "binance": prefer Tatum when both exist
    return c.close if c else None


def resolve_due() -> int:
    with get_session() as session:
        pending = session.exec(select(Forecast).where(Forecast.status == "PENDING", Forecast.source == "live")).all()
    resolved = 0
    for f in pending:
        due = f.t + f.horizon_h * HOUR_MS
        if due > last_closed_hour() + HOUR_MS:
            continue
        close = close_of_candle(f.asset, due - HOUR_MS)
        with get_session() as session:
            f = session.get(Forecast, f.id)
            if close is None:
                if now_ms() - due > 24 * HOUR_MS:
                    f.status = "UNRESOLVABLE"
                    session.add(f)
                    session.commit()
                continue
            f.close_at_resolve = close
            f.label = 1.0 if close > f.close_at_t else 0.0
            f.amnesiac_brier = (f.amnesiac_p - f.label) ** 2
            f.recall_brier = (f.recall_p - f.label) ** 2
            f.status, f.resolved_at = "RESOLVED", datetime.now(timezone.utc)
            session.add(f)
            session.commit()
            session.refresh(f)
            text = formats.episode_text(f)
        mem = store.remember(store.NS_EPISODES, "EPISODE", text, ref={"asset": f.asset, "forecast_id": f.id, "t": f.t})
        with get_session() as session:
            f = session.get(Forecast, f.id)
            f.episode_memory_id = mem.id
            session.add(f)
            session.commit()
        resolved += 1
    return resolved


def snapshot_policy(asset: str, source: str = "live", book: StatsBook | None = None,
                    covers_until: int | None = None) -> PolicyState:
    if book is None:
        book, covers_until = current_book(asset)
    snapshot_id = f"cs-{asset}-{covers_until}"
    for text in formats.credibility_chunks(asset, book, snapshot_id, covers_until, source):
        store.remember(store.NS_CREDIBILITY, "CREDIBILITY", text, ref={"asset": asset, "snapshot_id": snapshot_id},
                       essential=True)
    state = PolicyState(asset=asset, source=source, covers_until=covers_until, book=book.to_dict(), snapshot_id=snapshot_id)
    with get_session() as session:
        session.add(state)
        session.commit()
        session.refresh(state)
    log.info("policy snapshot %s (%d episodes)", snapshot_id, book.episodes)
    return state


def record_lessons(asset: str, results: list[dict], source: str) -> list[Lesson]:
    saved = []
    previous = lesson_status(asset)
    for r in results:
        if previous.get(r["rule"]) == r["status"]:
            continue
        evidence = r["evidence"] | {"source": source}
        text = formats.lesson_text(asset, r["rule"], r["status"], r["statement"], evidence)
        mem = store.remember(store.NS_LESSONS, "LESSON", text, ref={"asset": asset, "rule": r["rule"]}, essential=True)
        lesson = Lesson(asset=asset, rule=r["rule"], status=r["status"], statement=r["statement"],
                        evidence=evidence, memory_id=mem.id)
        with get_session() as session:
            session.add(lesson)
            session.commit()
            session.refresh(lesson)
        saved.append(lesson)
    return saved


def bootstrap(asset: str) -> dict:
    """First run: walk-forward over history to seed memory, validate rules, snapshot to Walrus."""
    if latest_policy_state(asset) is not None:
        return {"skipped": "policy state exists"}
    frame = frame_for(asset)
    preds = voice_predictions(frame, BacktestConfig(with_onchain=True, include_ablation=False))[list(POLICY_VOICES)]
    gate = evaluate_rules(frame, preds, simulate_recall)
    lessons = record_lessons(asset, gate, source="bootstrap-backtest")
    _, book = simulate_recall(frame, preds, config_from_lessons(lesson_status(asset)))
    covers_until = int(frame.loc[preds.index].dropna(subset=["label"]).index.max())
    state = snapshot_policy(asset, "bootstrap", book, covers_until)
    active = [r for r, st in lesson_status(asset).items() if st == "validated"]
    store.remember(store.NS_DECISIONS, "DECISION", formats.decision_text(
        asset, "bootstrap", f"seeded memory from {book.episodes} backtest episodes; active rules: {', '.join(active) or 'none'}",
        {"episodes": book.episodes, "covers_until": covers_until, "snapshot_id": state.snapshot_id, "gate": gate},
    ), ref={"asset": asset}, essential=True)
    return {"episodes": book.episodes, "gate": {g["rule"]: (g["status"], g["evidence"]["delta"]) for g in gate},
            "new_lessons": [(lesson.rule, lesson.status) for lesson in lessons], "snapshot": state.snapshot_id}


def restore_from_walrus(asset: str) -> dict:
    """Rebuild one asset's learned state from Walrus alone: latest complete snapshot + later EPISODEs + lessons."""
    parts: dict[str, dict[int, dict]] = {}
    for m in store.recall(store.NS_CREDIBILITY, f"[CREDIBILITY] {asset} 4h snapshot", limit=100):
        data = formats.parse_data(m["text"])
        if data and data.get("type") == "credibility" and data.get("asset") == asset:
            parts.setdefault(data["snapshot_id"], {})[data["part"]] = data
    complete = [sid for sid, p in parts.items() if len(p) == next(iter(p.values()))["parts"]]
    if not complete:
        raise RuntimeError(f"no complete {asset} credibility snapshot found on Walrus")
    sid = max(complete, key=lambda s: next(iter(parts[s].values()))["covers_until"])
    chunks = list(parts[sid].values())
    book = StatsBook.from_dict({"episodes": chunks[0]["episodes"], "stats": {k: v for c in chunks for k, v in c["stats"].items()}})
    covers_until = chunks[0]["covers_until"]

    replayed = 0
    for m in store.recall(store.NS_EPISODES, f"[EPISODE] {asset} 4h", limit=100):
        data = formats.parse_data(m["text"])
        if (data and data.get("type") == "episode" and data.get("asset") == asset
                and data["t"] > covers_until and data.get("label") is not None):
            book.add_episode(data["regime"], data["voices"], data["label"])
            covers_until = max(covers_until, data["t"])
            replayed += 1

    lessons, seen_at = {}, {}
    for m in store.recall(store.NS_LESSONS, f"[LESSON] {asset} rule", limit=50):
        data = formats.parse_data(m["text"])
        # Recall is ordered by relevance, so keep the newest lesson per rule explicitly.
        if (data and data.get("type") == "lesson" and data.get("asset") == asset
                and m["created_at"] > seen_at.get(data["rule"], "")):
            lessons[data["rule"]], seen_at[data["rule"]] = data, m["created_at"]
    with get_session() as session:
        session.add(PolicyState(asset=asset, source="restore", covers_until=covers_until, book=book.to_dict(), snapshot_id=sid))
        if not session.exec(select(Lesson).where(Lesson.asset == asset)).first():
            for rule, data in lessons.items():
                session.add(Lesson(asset=asset, rule=rule, status=data["status"], statement=data["statement"],
                                   evidence=data["evidence"]))
        session.commit()
    return {"asset": asset, "snapshot_id": sid, "episodes": book.episodes, "replayed_live_episodes": replayed,
            "lessons": {r: d["status"] for r, d in lessons.items()}}


def _each_asset(job) -> dict:
    out = {}
    for asset in get_settings().assets:
        try:
            out[asset] = job(asset)
        except Exception as exc:
            log.exception("%s %s failed", job.__name__, asset)
            out[asset] = f"error: {exc}"
    return out


def hourly_cycle() -> dict:
    out = {}
    for name, job in (("resolved", resolve_due), ("picks_resolved", lambda: picks.resolve_picks(close_of_candle))):
        try:
            out[name] = job()
        except Exception as exc:
            log.exception("%s failed", name)
            out[name] = f"error: {exc}"
    out["forecast"] = _each_asset(forecast_asset)
    return out


def observation_facts(asset: str, book: StatsBook) -> dict:
    with get_session() as session:
        rows = session.exec(
            select(Forecast).where(Forecast.asset == asset, Forecast.source == "live", Forecast.status == "RESOLVED")
        ).all()
    n = len(rows)
    race = {"n": n}
    if n:
        race |= {
            "amnesiac": sum(f.amnesiac_brier for f in rows) / n,
            "recall": sum(f.recall_brier for f in rows) / n,
            "no_calls": sum(f.recall_action == "NO_CALL" for f in rows),
        }
    regimes = [
        {"key": key, **s.summary()}
        for key, bucket in book.stats.items()
        if key.count("|") == 1 and (s := bucket.get(PRIMARY_VOICE)) is not None and s.n >= 20
    ]
    regimes.sort(key=lambda r: r["bss"])
    return {
        "asset": asset,
        "race": race,
        "worst_regime": regimes[0] if regimes else None,
        "best_regime": regimes[-1] if regimes else None,
        "active_rules": lesson_status(asset),
        "episodes_in_memory": book.episodes,
    }


def daily_asset(asset: str) -> dict:
    registry(asset).fitted_at = None  # retrain on the next forecast
    state = snapshot_policy(asset, "live")
    facts = observation_facts(asset, StatsBook.from_dict(state.book))
    observation = agent.daily_observation(facts)
    evidence = facts | {"by": observation["by"]}
    text = formats.lesson_text(asset, "observation", "observation", observation["text"], evidence)
    mem = store.remember(store.NS_LESSONS, "LESSON", text, ref={"asset": asset, "rule": "observation"})
    with get_session() as session:
        session.add(Lesson(asset=asset, rule="observation", status="observation", statement=observation["text"],
                           evidence=evidence, memory_id=mem.id))
        session.commit()
    return {"snapshot": state.snapshot_id, "observation": observation}


def daily_cycle() -> dict:
    return _each_asset(daily_asset)
