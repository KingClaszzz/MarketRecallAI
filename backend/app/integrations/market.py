"""Price sources: Tatum OHLCV (live), Binance public klines (bulk backfill), CoinGecko (overview)."""
from app.config import get_settings
from app.integrations.http import get_json
from app.integrations.tracking import tracked

HOUR_MS = 3_600_000


def tatum_candle(symbol: str, open_time_ms: int) -> dict:
    """One closed 1h candle from Tatum Data API (50 credits per call)."""
    s = get_settings()
    with tracked("tatum_ohlcv", "GET /v4/data/rate/symbol/OHLCV"):
        raw = get_json(
            f"{s.tatum_data_api_url}/v4/data/rate/symbol/OHLCV",
            params={"symbol": symbol, "interval": "1h", "unix": open_time_ms},
            headers={"x-api-key": s.tatum_api_key},
        )
    return {
        "source": "tatum",
        "symbol": raw["symbol"],
        "open_time": int(raw["openTime"]),
        "close_time": int(raw["closeTime"]),
        "open": float(raw["open"]),
        "high": float(raw["high"]),
        "low": float(raw["low"]),
        "close": float(raw["close"]),
        "volume": float(raw["volume"]),
        "quote_volume": float(raw["quoteAssetVolume"]),
        "trades": int(raw["numberOfTrades"]),
        "taker_buy_base": float(raw["takerBuyBaseAssetVolume"]),
    }


def binance_candles(symbol: str, start_ms: int, limit: int = 1000) -> list[dict]:
    """Up to 1000 1h candles from Binance's public market-data mirror (same feed as Tatum OHLCV)."""
    s = get_settings()
    with tracked("binance", "GET /api/v3/klines"):
        rows = get_json(
            f"{s.binance_api_url}/api/v3/klines",
            params={"symbol": f"{symbol}USDT", "interval": "1h", "startTime": start_ms, "limit": limit},
        )
    return [
        {
            "source": "binance",
            "symbol": symbol,
            "open_time": int(r[0]),
            "close_time": int(r[6]),
            "open": float(r[1]),
            "high": float(r[2]),
            "low": float(r[3]),
            "close": float(r[4]),
            "volume": float(r[5]),
            "quote_volume": float(r[7]),
            "trades": int(r[8]),
            "taker_buy_base": float(r[9]),
        }
        for r in rows
    ]


def coingecko_overview(coin_id: str = "sui") -> dict:
    s = get_settings()
    with tracked("coingecko", "GET /simple/price"):
        raw = get_json(
            f"{s.coingecko_api_url}/simple/price",
            params={
                "ids": coin_id,
                "vs_currencies": "usd",
                "include_market_cap": "true",
                "include_24hr_vol": "true",
                "include_24hr_change": "true",
            },
            headers={"x-cg-demo-api-key": s.coingecko_api_key},
        )[coin_id]
    return {
        "price_usd": float(raw["usd"]),
        "market_cap_usd": raw.get("usd_market_cap"),
        "volume_24h_usd": raw.get("usd_24h_vol"),
        "change_24h_pct": raw.get("usd_24h_change"),
    }
