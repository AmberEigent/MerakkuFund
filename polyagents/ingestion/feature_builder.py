"""PIT-safe feature construction for historical Lab collections."""
from __future__ import annotations

from datetime import datetime

from polyagents.dataflows.features import extract_features
from polyagents.dataflows.types import Candle


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def build_price_raw(candles: list[Candle], *, available_at: datetime) -> dict:
    """Build raw collector-like data using only PIT-safe price candles."""
    closes = [float(c.close) for c in candles]
    highs = [float(c.high) for c in candles]
    lows = [float(c.low) for c in candles]
    first, last = closes[0], closes[-1]
    pct_change = ((last - first) / first) if first else 0.0
    available = _iso(available_at)
    raw = {
        "price": {
            "last_price": last,
            "high": max(highs),
            "low": min(lows),
            "pct_change": pct_change,
            "closes": closes,
            "available_at": available,
        },
        "volume": {
            "total_volume": sum(float(c.volume or 0.0) for c in candles),
            "recent_5bar_volume": 0.0,
            "baseline_avg_volume": 0.0,
            "available_at": available,
        },
        "orderbook": {
            "book_pressure": 0.0,
            "spread_bps": 0.0,
            "micro_price": None,
            "mid": None,
            "available_at": available,
        },
        "trades_flow": {
            "flow_imbalance": 0.0,
            "n_trades": 0,
            "available_at": available,
        },
        "news": {
            "sentiment": {"mean": 0.0},
            "available_at": available,
        },
    }
    raw["features"] = extract_features(raw)
    raw["features"]["available_at"] = available
    return raw
