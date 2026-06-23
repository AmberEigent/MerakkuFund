"""Historical replay — feed the alpha test real resolved markets, strictly PIT.

For each RESOLVED market in a slice we already know the outcome. We rewind to a
``prediction_time`` T = resolution − horizon, slice the price history to
``ts <= T`` (the point-in-time invariant — asserted, never assumed), take the
market price at T as the baseline, and run a *deterministic* signal over the
pre-T history to get the model's probability. Scoring those against the realised
outcomes with :func:`alpha_test` answers: does this signal beat the market in
this slice, with a bootstrap CI?

Why deterministic / price-only: historical order books and news cannot be
reconstructed point-in-time from public data, so an honest historical replay
*cannot* re-run the live LLM signal without leaking the future. This path tests
price-based signals over the abundant universe of resolved markets; forward
testing the LLM signal (the decision log) is the complementary path. Keeping the
two separate is deliberate — neither launders the other's edge.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from polyagents.evaluation.alpha import alpha_test
from polyagents.evaluation.evaluate import categorize


class PointInTimeError(AssertionError):
    """Raised if any feature used for a prediction post-dates prediction_time."""


def naive_signal(candles, market_price: float) -> float:
    """Trust the market — ties the baseline (a null-edge sanity check)."""
    return market_price


def momentum_signal(candles, market_price: float) -> float:
    """Nudge the market price by recent trend (a real, weak price hypothesis)."""
    closes = [c.close for c in candles]
    if len(closes) < 4:
        return market_price
    look = min(len(closes), 12)
    trend = closes[-1] - closes[-look]
    return max(0.02, min(0.98, market_price + 0.5 * trend))


@dataclass
class BacktestRunner:
    """Replay a deterministic signal over resolved markets, scored vs the market.

    ``client`` is a PolymarketDataClient (``list_resolved_markets`` /
    ``to_markets`` / ``fetch_price_history``). ``signal_fn(candles, market_price)``
    is the model under test; swap it to test a different price signal.
    """
    client: object
    predict_frac: float = 0.5            # predict this fraction through the price series
    max_markets: int = 30
    min_history: int = 4
    signal_fn: Callable = field(default=momentum_signal)

    def replay(self, category: str | None = None, *, markets=None) -> dict:
        rows = markets if markets is not None else self._resolved_yes_markets(category)
        records: list[dict] = []
        for m in rows:
            rec = self._score_market(m)
            if rec is not None:
                records.append(rec)
            if len(records) >= self.max_markets:
                break
        summary = alpha_test(records)          # records are already sliced
        return {"summary": summary, "records": records, "n_markets": len(records),
                "category": category, "predict_frac": self.predict_frac,
                "signal": getattr(self.signal_fn, "__name__", "signal")}

    # ----- internals ---------------------------------------------------------

    def _resolved_yes_markets(self, category: str | None) -> list:
        raw = self.client.list_resolved_markets(limit=self.max_markets * 5)
        yes = [m for m in self.client.to_markets(raw) if m.outcome == "YES"]
        if category:
            yes = [m for m in yes if categorize(m.question) == category]
        return yes

    def _score_market(self, m) -> dict | None:
        # a clearly-resolved market: final YES price is ~1 (won) or ~0 (lost)
        if not (m.price <= 0.05 or m.price >= 0.95):
            return None
        won = m.price >= 0.5

        candles = self.client.fetch_price_history(m.token_id, interval="max")
        n = len(candles)
        if n < self.min_history + 1:
            return None
        # prediction_time = the candle at predict_frac through the series; we may
        # only use STRICTLY-earlier candles (the point-in-time invariant).
        idx = min(max(int(self.predict_frac * n), self.min_history), n - 1)
        prediction_time = candles[idx].ts
        pit = [c for c in candles[:idx] if c.ts < prediction_time]
        if len(pit) < self.min_history:
            return None
        if any(c.ts >= prediction_time for c in pit):       # belt-and-suspenders
            raise PointInTimeError(f"{m.token_id}: feature at/after prediction_time")

        market_p = pit[-1].close
        if not (0.02 < market_p < 0.98):       # already decided at T → no decision to test
            return None
        p_model = float(self.signal_fn(pit, market_p))
        return {"status": "resolved", "won": bool(won), "p_true": p_model,
                "market_price": float(market_p), "question": m.question}
