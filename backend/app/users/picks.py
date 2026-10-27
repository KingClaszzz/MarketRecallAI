"""User calls: UP or DOWN for the next 4h window, scored on the market."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from app.config import get_settings
from app.data.collector import last_closed_hour
from app.data.validation import HOUR_MS
from app.db import Forecast, Pick, get_session
from app.memory import formats, store
from app.users import credits

DIRECTIONS = {"UP", "DOWN"}


class PickError(Exception):
    pass


def user_namespace(address: str) -> str:
    """Per-user Walrus namespace (hashed, not the raw address)."""
    return "mr-user-" + hashlib.sha256(address.encode()).hexdigest()[:16]


def next_slot() -> int:
    """Next decision time. Calls lock when it starts."""
    return last_closed_hour() + 2 * HOUR_MS


def place_pick(address: str, asset: str, direction: str, slot_t: int, *, session_id: int | None = None,
               mode: str = "own", model_p: float | None = None, model_action: str | None = None) -> Pick:
    direction = direction.upper()
    if asset not in get_settings().assets:
        raise PickError(f"unknown asset {asset}")
    if direction not in DIRECTIONS:
        raise PickError("direction must be UP or DOWN")
    if slot_t <= last_closed_hour() + HOUR_MS:
        raise PickError("this window has already started; open a new session for the next one")
    with get_session() as session:
        if session.exec(select(Pick).where(Pick.address == address, Pick.asset == asset, Pick.slot_t == slot_t)).first():
            raise PickError(f"you already have a {asset} call for this window")
        pick = Pick(address=address, asset=asset, slot_t=slot_t, direction=direction, session_id=session_id,
                    mode=mode, model_p=model_p, model_action=model_action)
        session.add(pick)
        try:
            session.commit()
        except IntegrityError:
            raise PickError(f"you already have a {asset} call for this window") from None
        session.refresh(pick)
    return pick


def _regime_of_window(asset: str, t: int) -> dict:
    with get_session() as session:
        f = session.exec(select(Forecast).where(Forecast.asset == asset, Forecast.t == t, Forecast.source == "live")).first()
    return f.regime if f else {}


def user_episode_text(pick: Pick, regime: dict | None = None) -> str:
    outcome = "UP" if pick.close_at_resolve > pick.close_at_t else "DOWN_OR_FLAT"
    model = "model=none"
    if pick.model_p is not None:
        model = f"model {pick.model_action} p={pick.model_p:.2f} agreed={pick.agrees_with_model}"
    header = (
        f"[USER_EPISODE] {pick.asset} 4h @{formats.iso(pick.slot_t)} | regime "
        f"{formats.regime_text(regime) if regime else 'unknown'} | mode={pick.mode}\n"
        f"call={pick.direction} outcome={outcome} result={pick.status} | {model}"
    )
    return formats._with_data(header, {
        "type": "user_episode", "asset": pick.asset, "slot_t": pick.slot_t, "direction": pick.direction,
        "mode": pick.mode, "outcome": outcome, "result": pick.status, "regime": regime or {},
        "model": None if pick.model_p is None else {
            "p": pick.model_p, "action": pick.model_action, "agreed": pick.agrees_with_model,
        },
        "close_at_t": pick.close_at_t, "close_at_resolve": pick.close_at_resolve,
    })


def resolve_picks(close_of_candle) -> int:
    """Resolve ended calls, pay out right ones, and remember each in the user's namespace."""
    horizon = get_settings().forecast_horizon_h
    latest_close_time = last_closed_hour() + HOUR_MS
    with get_session() as session:
        pending = session.exec(select(Pick).where(Pick.status == "PENDING")).all()
    resolved = 0
    for pick in pending:
        end = pick.slot_t + horizon * HOUR_MS
        if end > latest_close_time:
            continue
        start_close = close_of_candle(pick.asset, pick.slot_t - HOUR_MS)
        end_close = close_of_candle(pick.asset, end - HOUR_MS)
        ref = {"pick_id": pick.id, "asset": pick.asset, "slot_t": pick.slot_t}
        with get_session() as session:
            pick = session.get(Pick, pick.id)
            if start_close is None or end_close is None:
                if latest_close_time - end > 24 * HOUR_MS:
                    pick.status = "REFUNDED"
                    session.add(pick)
                    session.commit()
                    credits.grant(pick.address, credits.SESSION_COST, "call_refund", ref)
                continue
            went_up = end_close > start_close
            pick.close_at_t, pick.close_at_resolve = start_close, end_close
            pick.status = "WON" if (pick.direction == "UP") == went_up else "LOST"
            pick.resolved_at = datetime.now(timezone.utc)
            session.add(pick)
            session.commit()
            session.refresh(pick)
        if pick.status == "WON":
            credits.grant(pick.address, credits.CALL_REWARD, "call_right", ref)
        text = user_episode_text(pick, _regime_of_window(pick.asset, pick.slot_t))
        mem = store.remember(user_namespace(pick.address), "USER_EPISODE", text, ref=ref)
        with get_session() as session:
            pick = session.get(Pick, pick.id)
            pick.memory_id = mem.id
            session.add(pick)
            session.commit()
        resolved += 1
    return resolved
