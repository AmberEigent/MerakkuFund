"""Strategy signal library — pluggable ``p_true`` estimators for backtesting.

Each signal maps ``(candles, market_price) -> estimated true probability``, seeing
only the price/volume history up to the prediction time (point-in-time). Adding a
signal = write a function + register it in :data:`SIGNALS`; ``backtest_strategies`` /
``promotion_gate`` / any batch backtest then picks it up automatically.

The signals here are principled (documented market inefficiencies / classic
technicals), not curve-fit — most of the time prediction markets are efficient and
these will honestly show no alpha. The point is a real menu to compare, and to
surface the occasional edge (e.g. the favorite-longshot bias).
"""
from __future__ import annotations

from polyagents.lab.backtest import momentum_signal, naive_signal


def _clamp(p: float) -> float:
    return max(0.02, min(0.98, p))


def _closes(candles) -> list[float]:
    return [c.close for c in candles]


def mean_reversion_signal(candles, market_price: float) -> float:
    """Contrarian: fade the recent move — a sharp run-up reverts partway toward
    where it came from. The opposite bet to momentum."""
    c = _closes(candles)
    if len(c) < 4:
        return market_price
    look = min(len(c), 12)
    trend = c[-1] - c[-look]
    return _clamp(market_price - 0.3 * trend)


def favorite_longshot_signal(candles, market_price: float) -> float:
    """Favorite-longshot bias — a well-documented inefficiency in betting/prediction
    markets: longshots (low prob) are overpriced and favorites (high prob) are
    underpriced. Push the probability away from 0.5 toward the side it already leans."""
    return _clamp(market_price + 0.15 * (market_price - 0.5))


def trend_strength_signal(candles, market_price: float) -> float:
    """Momentum scaled by how *consistent* the recent trend is (fraction of up-moves).
    A steady grind gets a bigger nudge than a choppy net move."""
    c = _closes(candles)
    if len(c) < 5:
        return market_price
    look = min(len(c), 12)
    seg = c[-look:]
    ups = sum(1 for i in range(1, len(seg)) if seg[i] > seg[i - 1])
    consistency = abs((2 * ups / (len(seg) - 1)) - 1)   # 0 (choppy) .. 1 (all one way)
    trend = c[-1] - c[-look]
    return _clamp(market_price + 0.6 * trend * consistency)


def volume_momentum_signal(candles, market_price: float) -> float:
    """Momentum confirmed by volume — a trend backed by *rising* volume gets more
    weight than one on fading volume (informed flow vs noise)."""
    c = _closes(candles)
    if len(c) < 5:
        return market_price
    look = min(len(c), 12)
    trend = c[-1] - c[-look]
    vols = [x.volume for x in candles[-look:]]
    half = len(vols) // 2 or 1
    earlier = sum(vols[:half]) or 1.0
    recent = sum(vols[half:])
    conf = min(2.0, recent / earlier)                   # >1 = volume rising into the move
    return _clamp(market_price + 0.4 * trend * conf)


#: The strategy library — name -> signal fn. Batch backtests iterate over this.
SIGNALS = {
    "naive": naive_signal,                              # baseline: trust the market (delta 0)
    "momentum": momentum_signal,                        # follow the recent trend
    "mean_reversion": mean_reversion_signal,            # fade the recent move
    "favorite_longshot": favorite_longshot_signal,      # correct the longshot bias
    "trend_strength": trend_strength_signal,            # momentum x consistency
    "volume_momentum": volume_momentum_signal,          # momentum x rising volume
}
