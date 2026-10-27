HOUR_MS = 3_600_000


def candle_errors(c: dict) -> list[str]:
    errors = []
    if c["open_time"] % HOUR_MS != 0:
        errors.append("open_time not aligned to hour")
    if c.get("close_time") is not None and c["close_time"] != c["open_time"] + HOUR_MS - 1:
        errors.append("close_time does not match a 1h candle")
    if min(c["open"], c["high"], c["low"], c["close"]) <= 0:
        errors.append("non-positive price")
    if c["high"] < max(c["open"], c["close"]) or c["low"] > min(c["open"], c["close"]):
        errors.append("high/low inconsistent with open/close")
    if c["volume"] < 0 or c["trades"] < 0:
        errors.append("negative volume or trades")
    return errors


def is_closed(c: dict, now_ms: int) -> bool:
    return c["open_time"] + HOUR_MS <= now_ms
