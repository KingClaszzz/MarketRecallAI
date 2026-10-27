"""Feature frame: one row per decision time t (close of a 1h candle), using only data available at t."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sqlmodel import select

from app.data.validation import HOUR_MS
from app.db import Candle, OnchainSnapshot, get_session

PRICE_FEATURES = [
    "ret_1h", "ret_4h", "ret_12h", "ret_24h",
    "vol_24h", "vol_ratio",
    "ema24_dist", "ema72_dist",
    "rsi_14", "range_pct",
    "volume_z", "trades_z", "taker_buy_ratio",
    "hour_sin", "hour_cos", "is_weekend",
]
ONCHAIN_FEATURES = ["tx_log", "tx_z_7d", "tx_change_24h", "gas_per_tx_z"]


def load_candles(symbol: str = "SUI") -> pd.DataFrame:
    """Tatum candles take precedence; Binance fills history (same feed, verified identical)."""
    with get_session() as session:
        rows = session.exec(select(Candle).where(Candle.symbol == symbol)).all()
    df = pd.DataFrame([r.model_dump() for r in rows])
    if df.empty:
        return df
    df["prio"] = df["source"].map({"tatum": 0, "binance": 1})
    df = df.sort_values(["open_time", "prio"]).drop_duplicates("open_time", keep="first")
    return df.set_index("open_time").sort_index().drop(columns=["prio", "ingested_at"])


def load_onchain() -> pd.DataFrame:
    with get_session() as session:
        rows = session.exec(select(OnchainSnapshot)).all()
    df = pd.DataFrame([r.model_dump() for r in rows])
    return df.set_index("hour_ts").sort_index() if not df.empty else df


def _rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + gain / loss.replace(0, np.nan))


def _z(s: pd.Series, window: int) -> pd.Series:
    mean = s.rolling(window, min_periods=window // 2).mean()
    std = s.rolling(window, min_periods=window // 2).std()
    return (s - mean) / std.replace(0, np.nan)


def onchain_features(onchain: pd.DataFrame) -> pd.DataFrame:
    """Indexed by hour boundary (= candle close time)."""
    full = onchain.reindex(range(onchain.index.min(), onchain.index.max() + 1, HOUR_MS))
    tx = full["total_tx"].diff()
    # Rolling gas cost resets at each epoch; the hourly delta is only valid within one epoch.
    same_epoch = full["epoch"].eq(full["epoch"].shift())
    gas = full["computation_cost"].diff().where(same_epoch)
    out = pd.DataFrame(index=full.index)
    out["tx_per_hour"] = tx
    out["tx_log"] = np.log1p(tx)
    out["tx_z_7d"] = _z(out["tx_log"], 168)
    out["tx_change_24h"] = out["tx_log"] - out["tx_log"].rolling(24, min_periods=12).mean()
    out["gas_per_tx_z"] = _z(np.log1p(gas / tx.replace(0, np.nan)), 168)
    return out


def build_frame(candles: pd.DataFrame, onchain: pd.DataFrame | None, horizon_h: int) -> pd.DataFrame:
    """Rows indexed by decision time t = candle close (open_time + 1h). Label uses close at t + horizon."""
    c = candles.reindex(range(candles.index.min(), candles.index.max() + 1, HOUR_MS))
    close = c["close"]
    logret = np.log(close).diff()

    f = pd.DataFrame(index=c.index + HOUR_MS)
    f.index.name = "t"
    f["open_time"] = c.index
    f["close"] = close.values
    for h in (1, 4, 12, 24):
        f[f"ret_{h}h"] = np.log(close / close.shift(h)).values
    vol_24 = logret.rolling(24, min_periods=20).std()
    vol_168 = logret.rolling(168, min_periods=120).std()
    f["vol_24h"] = vol_24.values
    f["vol_ratio"] = (vol_24 / vol_168).values
    ema24 = close.ewm(span=24, adjust=False).mean()
    ema72 = close.ewm(span=72, adjust=False).mean()
    f["ema24_dist"] = (close / ema24 - 1).values
    f["ema72_dist"] = (close / ema72 - 1).values
    f["ema24_above_72"] = (ema24 > ema72).values
    f["rsi_14"] = (_rsi(close) / 100).values
    f["range_pct"] = ((c["high"] - c["low"]) / close).values
    f["volume_z"] = _z(np.log1p(c["volume"]), 168).values
    f["trades_z"] = _z(np.log1p(c["trades"].astype(float)), 168).values
    f["taker_buy_ratio"] = (c["taker_buy_base"] / c["volume"].replace(0, np.nan)).rolling(4, min_periods=2).mean().values

    ts = pd.to_datetime(f.index, unit="ms", utc=True)
    f["hour_utc"] = ts.hour
    f["hour_sin"] = np.sin(2 * np.pi * ts.hour / 24)
    f["hour_cos"] = np.cos(2 * np.pi * ts.hour / 24)
    f["is_weekend"] = (ts.dayofweek >= 5).astype(float)

    f["vol_pct_30d"] = f["vol_24h"].rolling(720, min_periods=168).rank(pct=True)

    if onchain is not None and not onchain.empty:
        f = f.join(onchain_features(onchain), how="left")

    future_close = close.shift(-horizon_h).values
    f["close_future"] = future_close
    f["label"] = np.where(np.isnan(future_close), np.nan, (future_close > close.values).astype(float))
    f["resolved_at"] = f.index + horizon_h * HOUR_MS
    return f


FEATURE_LABELS = {
    "ret_1h": "the last 1h move", "ret_4h": "the last 4h move", "ret_12h": "the last 12h move",
    "ret_24h": "the last 24h move", "vol_24h": "24h volatility", "vol_ratio": "volatility versus the past week",
    "ema24_dist": "distance from the 24h average price", "ema72_dist": "distance from the 72h average price",
    "rsi_14": "RSI (14h)", "range_pct": "the last candle's high-low range", "volume_z": "trading volume versus the past week",
    "trades_z": "number of trades versus the past week", "taker_buy_ratio": "share of aggressive buying",
    "time_of_day": "time of day", "is_weekend": "weekend or weekday", "tx_log": "Sui transaction count",
    "tx_z_7d": "Sui network activity versus the past week", "tx_change_24h": "Sui network activity versus the past day",
    "gas_per_tx_z": "gas per transaction versus the past week",
}
