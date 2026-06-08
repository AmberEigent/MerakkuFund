"""Portfolio — virtual cash, positions, and realised P&L.

The paper venue and the circuit breaker both read/write this. Single-venue,
long-only (no shorting on Polymarket): a "sell" closes an existing position.
Realised P&L is booked on close; unrealised is marked against the current price.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from .types import Fill, Position


@dataclass
class ClosedTrade:
    token_id: str
    pnl: float
    ts: datetime


class Portfolio:
    def __init__(self, starting_cash: float) -> None:
        self.starting_cash = starting_cash
        self.cash = starting_cash
        self.positions: dict[str, Position] = {}
        self.closed: list[ClosedTrade] = []
        self.consecutive_losses = 0

    # ----- state reads -------------------------------------------------------

    def exposure(self) -> float:
        """Cost basis of all open positions (USDC at risk)."""
        return sum(p.cost_basis for p in self.positions.values())

    def realized_pnl(self) -> float:
        return sum(c.pnl for c in self.closed)

    def realized_pnl_on(self, day: datetime | None = None) -> float:
        d = (day or datetime.now(timezone.utc)).date()
        return sum(c.pnl for c in self.closed if c.ts.date() == d)

    def equity(self, marks: dict[str, float] | None = None) -> float:
        """Cash + marked value of open positions (marks: token_id -> price)."""
        marks = marks or {}
        held = sum(p.mark_value(marks.get(p.token_id, p.avg_price)) for p in self.positions.values())
        return self.cash + held

    # ----- mutations ---------------------------------------------------------

    def apply_buy(self, fill: Fill) -> None:
        self.cash -= fill.notional
        pos = self.positions.get(fill.token_id)
        if pos is None:
            self.positions[fill.token_id] = Position(fill.token_id, fill.shares, fill.price)
        else:
            total = pos.shares + fill.shares
            pos.avg_price = (pos.cost_basis + fill.notional) / total if total else fill.price
            pos.shares = total

    def apply_sell_close(self, token_id: str, sell_price: float, ts: datetime) -> float:
        """Close the whole position at ``sell_price``; book and return realised P&L."""
        pos = self.positions.pop(token_id)
        pnl = (sell_price - pos.avg_price) * pos.shares
        self.cash += sell_price * pos.shares
        self.closed.append(ClosedTrade(token_id, pnl, ts))
        self.consecutive_losses = self.consecutive_losses + 1 if pnl < 0 else 0
        return pnl
