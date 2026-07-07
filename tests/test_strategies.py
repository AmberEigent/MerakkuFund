"""Strategy signal library — the pluggable p_true estimators used by batch backtests."""
from __future__ import annotations

from dataclasses import dataclass

from polyagents.strategies import SIGNALS


@dataclass
class _C:
    close: float
    volume: float = 1.0


def _series(vals, vols=None):
    vols = vols or [1.0] * len(vals)
    return [_C(v, w) for v, w in zip(vals, vols)]


def test_library_has_multiple_signals():
    assert {"naive", "momentum", "mean_reversion", "favorite_longshot"} <= set(SIGNALS)
    assert len(SIGNALS) >= 6


def test_all_signals_return_valid_probabilities():
    candles = _series([0.30, 0.35, 0.40, 0.50, 0.55], [1, 2, 3, 4, 8])
    for name, fn in SIGNALS.items():
        p = fn(candles, 0.55)
        assert 0.0 <= p <= 1.0, f"{name} out of range: {p}"


def test_naive_trusts_market_and_signals_differ():
    candles = _series([0.30, 0.35, 0.40, 0.50, 0.55], [1, 2, 3, 4, 8])
    assert SIGNALS["naive"](candles, 0.55) == 0.55                 # baseline = market
    # momentum leans up on an uptrend; mean_reversion leans the other way
    assert SIGNALS["momentum"](candles, 0.55) > 0.55
    assert SIGNALS["mean_reversion"](candles, 0.55) < 0.55


def test_favorite_longshot_pushes_away_from_half():
    c = _series([0.1, 0.1, 0.1, 0.1])
    assert SIGNALS["favorite_longshot"](c, 0.10) < 0.10           # longshot -> even lower
    assert SIGNALS["favorite_longshot"](c, 0.90) > 0.90           # favorite -> even higher


def test_short_history_falls_back_to_market():
    c = _series([0.5, 0.5])                                       # too short for trend signals
    for name in ("momentum", "mean_reversion", "trend_strength", "volume_momentum"):
        assert SIGNALS[name](c, 0.5) == 0.5
