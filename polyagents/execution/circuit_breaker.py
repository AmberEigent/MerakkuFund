"""Circuit breaker — the safety boundary in front of every entry.

Pre-trade gates that block new exposure (buys); exits (sells that reduce risk)
always pass. Mirrors the polymarket reference repo's breaker: daily realised-loss
halt, total-exposure cap, max concurrent positions, consecutive-loss cooldown,
and a cash check. Returns ``(allowed, reason)`` — deterministic and auditable.
"""
from __future__ import annotations

from .portfolio import Portfolio
from .types import Order


class CircuitBreaker:
    def __init__(self, config: dict) -> None:
        self.bankroll = config["bankroll_usdc"]
        self.max_daily_loss_pct = config["max_daily_loss_pct"]
        self.max_total_exposure_pct = config["max_total_exposure_pct"]
        self.max_concurrent_positions = config["max_concurrent_positions"]
        self.max_consecutive_losses = config["max_consecutive_losses"]

    def check(self, order: Order, portfolio: Portfolio) -> tuple[bool, str]:
        # Exits always allowed — they reduce risk.
        if order.side == "sell":
            if order.token_id not in portfolio.positions:
                return False, "no open position to sell"
            return True, "exit permitted"

        # --- entry (buy) gates ---
        if portfolio.realized_pnl_on() <= -self.max_daily_loss_pct * self.bankroll:
            return False, (
                f"daily loss halt: realised {portfolio.realized_pnl_on():.2f} "
                f"≤ -{self.max_daily_loss_pct:.0%} bankroll"
            )
        if portfolio.consecutive_losses >= self.max_consecutive_losses:
            return False, f"cooldown: {portfolio.consecutive_losses} consecutive losses"
        new_position = order.token_id not in portfolio.positions
        if new_position and len(portfolio.positions) >= self.max_concurrent_positions:
            return False, f"max concurrent positions ({self.max_concurrent_positions}) reached"
        projected = portfolio.exposure() + order.size_usdc
        if projected > self.max_total_exposure_pct * self.bankroll:
            return False, (
                f"exposure cap: ${projected:,.0f} > {self.max_total_exposure_pct:.0%} "
                f"of ${self.bankroll:,.0f}"
            )
        if order.size_usdc > portfolio.cash:
            return False, f"insufficient cash: need ${order.size_usdc:,.2f}, have ${portfolio.cash:,.2f}"
        return True, "passed"
