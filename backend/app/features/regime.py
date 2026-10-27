"""Deterministic market regime labels used as the key for memory recall."""
from __future__ import annotations

import math

LEVELS = (("vol", "trend", "chain"), ("vol", "trend"), ("vol",))


def _nan(x) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x))


def vol_bucket(vol_pct: float) -> str:
    if _nan(vol_pct):
        return "normal"
    return "low" if vol_pct < 1 / 3 else "high" if vol_pct > 2 / 3 else "normal"


def trend_bucket(ema24_dist: float, ema72_dist: float, ema24_above_72: bool) -> str:
    if _nan(ema24_dist) or _nan(ema72_dist):
        return "sideways"
    if ema24_dist > 0 and ema72_dist > 0 and ema24_above_72:
        return "up"
    if ema24_dist < 0 and ema72_dist < 0 and not ema24_above_72:
        return "down"
    return "sideways"


def chain_bucket(tx_z_7d: float | None) -> str:
    if _nan(tx_z_7d):
        return "unknown"
    return "busy" if tx_z_7d > 1 else "quiet" if tx_z_7d < -1 else "normal"


def session_bucket(hour_utc: int, is_weekend: bool) -> str:
    name = "asia" if hour_utc < 8 else "eu" if hour_utc < 14 else "us"
    return f"{name}-{'weekend' if is_weekend else 'weekday'}"


def regime_of(row) -> dict[str, str]:
    return {
        "vol": vol_bucket(row["vol_pct_30d"]),
        "trend": trend_bucket(row["ema24_dist"], row["ema72_dist"], bool(row["ema24_above_72"])),
        "chain": chain_bucket(row.get("tx_z_7d")),
        "session": session_bucket(int(row["hour_utc"]), bool(row["is_weekend"])),
    }


def regime_key(regime: dict[str, str], dims=("vol", "trend", "chain", "session")) -> str:
    return "|".join(f"{d}={regime[d]}" for d in dims)
