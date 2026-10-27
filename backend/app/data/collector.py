"""Hourly ingestion: Tatum candle + Sui onchain snapshot + CoinGecko overview."""
from __future__ import annotations

import logging
import time

from sqlmodel import select

from app.config import get_settings
from app.data.validation import HOUR_MS, candle_errors, is_closed
from app.db import Candle, MarketSnapshot, OnchainSnapshot, get_session
from app.integrations import market, onchain

log = logging.getLogger(__name__)

MAX_TATUM_CATCHUP_HOURS = 6
GAP_FILL_HOURS = 168  # older gaps are filled from Binance


def now_ms() -> int:
    return int(time.time() * 1000)


def last_closed_hour(ts_ms: int | None = None) -> int:
    """Open time of the most recent fully closed 1h candle."""
    ts_ms = ts_ms if ts_ms is not None else now_ms()
    return (ts_ms // HOUR_MS) * HOUR_MS - HOUR_MS


def save_candles(candles: list[dict]) -> int:
    current = now_ms()
    saved = 0
    with get_session() as session:
        for c in candles:
            if not is_closed(c, current):
                continue
            errors = candle_errors(c)
            if errors:
                log.warning("dropping invalid %s candle %s: %s", c["source"], c["open_time"], errors)
                continue
            fields = {k: v for k, v in c.items() if k != "close_time"}
            session.merge(Candle(**fields))
            saved += 1
        session.commit()
    return saved


def save_onchain(hour_ts: int, cp: onchain.Checkpoint, reference_gas_price: int | None = None) -> None:
    with get_session() as session:
        session.merge(
            OnchainSnapshot(
                hour_ts=hour_ts,
                checkpoint_seq=cp.seq,
                checkpoint_ts=cp.ts,
                total_tx=cp.total_tx,
                epoch=cp.epoch,
                computation_cost=cp.computation_cost,
                storage_cost=cp.storage_cost,
                storage_rebate=cp.storage_rebate,
                reference_gas_price=reference_gas_price,
            )
        )
        session.commit()


def missing_hours(source: str | None, symbol: str, until_open_time: int, lookback_hours: int) -> list[int]:
    start = until_open_time - (lookback_hours - 1) * HOUR_MS
    query = select(Candle.open_time).where(Candle.symbol == symbol, Candle.open_time >= start)
    if source:
        query = query.where(Candle.source == source)
    with get_session() as session:
        have = set(session.exec(query).all())
    return [t for t in range(start, until_open_time + 1, HOUR_MS) if t not in have]


def collect_candles() -> dict[str, int]:
    target = last_closed_hour()
    saved = {}
    for symbol in get_settings().assets:
        candles = []
        for open_time in missing_hours("tatum", symbol, target, MAX_TATUM_CATCHUP_HOURS):
            try:
                candles.append(market.tatum_candle(symbol, open_time))
            except Exception:
                log.exception("tatum candle %s %s failed", symbol, open_time)
        saved[symbol] = save_candles(candles)
        gaps = missing_hours(None, symbol, target, GAP_FILL_HOURS)
        if gaps:
            try:
                wanted = set(gaps)
                fill = [c for c in market.binance_candles(symbol, gaps[0], limit=GAP_FILL_HOURS) if c["open_time"] in wanted]
                saved[symbol] += save_candles(fill)
            except Exception:
                log.exception("binance gap fill %s failed", symbol)
    return saved


def collect_onchain() -> int:
    boundary = last_closed_hour() + HOUR_MS
    with get_session() as session:
        have = set(
            session.exec(
                select(OnchainSnapshot.hour_ts).where(
                    OnchainSnapshot.hour_ts >= boundary - (MAX_TATUM_CATCHUP_HOURS - 1) * HOUR_MS
                )
            ).all()
        )
    todo = [boundary - i * HOUR_MS for i in range(MAX_TATUM_CATCHUP_HOURS) if boundary - i * HOUR_MS not in have]
    gas_price = None
    try:
        gas_price = onchain.get_reference_gas_price()
    except Exception:
        log.exception("reference gas price failed")
    saved = 0
    for hour_ts in sorted(todo):
        try:
            save_onchain(hour_ts, onchain.checkpoint_at(hour_ts), gas_price if hour_ts == boundary else None)
            saved += 1
        except Exception:
            log.exception("onchain snapshot %s failed", hour_ts)
    return saved


def collect_market_overview() -> None:
    overview = market.coingecko_overview()
    with get_session() as session:
        session.add(MarketSnapshot(**overview))
        session.commit()


def collect_hour() -> dict:
    result = {}
    for name, job in (("candles", collect_candles), ("onchain", collect_onchain), ("market", collect_market_overview)):
        try:
            result[name] = job()
        except Exception as exc:
            log.exception("%s collection failed", name)
            result[name] = f"error: {exc}"
    return result
