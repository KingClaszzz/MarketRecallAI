"""One-off historical backfill for the walk-forward backtest."""
from __future__ import annotations

import logging

from sqlmodel import select

from app.config import get_settings
from app.data.collector import last_closed_hour, save_candles, save_onchain
from app.data.validation import HOUR_MS
from app.db import OnchainSnapshot, get_session
from app.integrations import market, onchain

log = logging.getLogger(__name__)


def backfill_candles(days: int) -> dict[str, int]:
    end = last_closed_hour()
    saved = {}
    for symbol in get_settings().assets:
        start, saved[symbol] = end - days * 24 * HOUR_MS, 0
        while start <= end:
            batch = market.binance_candles(symbol, start, limit=1000)
            if not batch:
                break
            saved[symbol] += save_candles(batch)
            start = batch[-1]["open_time"] + HOUR_MS
    return saved


def backfill_onchain(days: int, progress_every: int = 24) -> int:
    """Snapshot each hour boundary going back `days`. ~2-4 gRPC calls per hour; resumable."""
    end = last_closed_hour() + HOUR_MS
    hours = [end - i * HOUR_MS for i in range(days * 24 + 1)]
    with get_session() as session:
        have = set(session.exec(select(OnchainSnapshot.hour_ts).where(OnchainSnapshot.hour_ts >= hours[-1])).all())
    todo = [h for h in hours if h not in have]
    saved = 0
    for i, hour_ts in enumerate(todo, 1):
        try:
            save_onchain(hour_ts, onchain.checkpoint_at(hour_ts))
            saved += 1
        except Exception:
            log.exception("onchain backfill %s failed", hour_ts)
        if i % progress_every == 0:
            log.info("onchain backfill %d/%d", i, len(todo))
    return saved
