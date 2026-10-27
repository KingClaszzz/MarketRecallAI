from app.data.collector import last_closed_hour
from app.data.validation import HOUR_MS, candle_errors, is_closed


def candle(**overrides) -> dict:
    base = {
        "open_time": 1792972800000,
        "close_time": 1792972800000 + HOUR_MS - 1,
        "open": 0.92,
        "high": 0.93,
        "low": 0.91,
        "close": 0.925,
        "volume": 1000.0,
        "trades": 10,
    }
    return base | overrides


def test_valid_candle_has_no_errors():
    assert candle_errors(candle()) == []


def test_misaligned_open_time_is_rejected():
    assert "open_time not aligned to hour" in candle_errors(candle(open_time=1792972800001, close_time=None))


def test_high_below_close_is_rejected():
    assert "high/low inconsistent with open/close" in candle_errors(candle(high=0.92, close=0.925))


def test_open_candle_is_not_closed():
    c = candle()
    assert not is_closed(c, c["open_time"] + HOUR_MS - 1)
    assert is_closed(c, c["open_time"] + HOUR_MS)


def test_last_closed_hour_never_returns_the_current_hour():
    now = 1792972800000 + 30 * 60 * 1000  # 30 minutes into an hour
    assert last_closed_hour(now) == 1792972800000 - HOUR_MS


def test_old_gaps_are_filled_from_binance(temp_db, monkeypatch):
    from app.data import collector

    target = last_closed_hour()
    have = [target - h * HOUR_MS for h in range(collector.GAP_FILL_HOURS) if not 20 <= h < 30]  # a 10h hole, 20h ago

    def candle(source, t):
        return {"source": source, "symbol": "SUI", "open_time": t, "close_time": t + HOUR_MS - 1, "open": 1.0,
                "high": 1.1, "low": 0.9, "close": 1.0, "volume": 1.0, "quote_volume": 1.0, "trades": 1, "taker_buy_base": 0.5}

    monkeypatch.setattr(collector.get_settings(), "assets", ["SUI"])
    collector.save_candles([candle("tatum", t) for t in have])
    asked = []
    monkeypatch.setattr(collector.market, "binance_candles",
                        lambda symbol, start, limit: asked.append(start) or [candle("binance", t) for t in range(start, target + 1, HOUR_MS)])
    collector.collect_candles()
    assert asked == [target - 29 * HOUR_MS]  # one request, from the oldest missing hour
    assert collector.missing_hours(None, "SUI", target, collector.GAP_FILL_HOURS) == []
