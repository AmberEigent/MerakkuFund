"""Execution clients — the port and its adapters (NautilusTrader-style).

``ExecutionClient`` is the port; strategies depend only on it. Two adapters:

  * ``PaperExecutionClient`` — simulates fills against the touch price plus
    modeled slippage and books them into the :class:`Portfolio`. The default.
  * ``LiveCLOBExecutionClient`` — posts real GTC limit orders via the official
    py-clob-client (needs ``POLYMARKET_PRIVATE_KEY``). Gated; never the default.

Swapping paper ↔ live changes nothing upstream — same port, different adapter.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol, runtime_checkable

from .portfolio import Portfolio
from .types import ExecutionResult, Fill, Order


@runtime_checkable
class ExecutionClient(Protocol):
    def submit(self, order: Order, portfolio: Portfolio) -> ExecutionResult:
        ...


class PaperExecutionClient:
    """Simulated venue: fill at touch ± slippage, book into the portfolio."""

    def __init__(self, slippage_bps: float = 50.0) -> None:
        self.slippage_bps = slippage_bps

    def submit(self, order: Order, portfolio: Portfolio) -> ExecutionResult:
        slip = self.slippage_bps / 10_000.0
        now = datetime.now(timezone.utc)

        if order.side == "buy":
            if order.size_usdc <= 0:
                return ExecutionResult("skipped", order, reason="zero size")
            price = order.ref_price * (1 + slip)
            if price <= 0:
                return ExecutionResult("rejected", order, reason="non-positive fill price")
            shares = order.size_usdc / price
            fill = Fill(order.token_id, "buy", price, shares, order.size_usdc, now)
            portfolio.apply_buy(fill)
            return ExecutionResult("filled", order, fill, 0.0,
                                   f"bought {shares:,.0f} @ {price:.3f}")

        # sell = full exit of the held position
        if order.token_id not in portfolio.positions:
            return ExecutionResult("skipped", order, reason="no position to sell")
        price = order.ref_price * (1 - slip)
        pos = portfolio.positions[order.token_id]
        shares = pos.shares
        pnl = portfolio.apply_sell_close(order.token_id, price, now)
        fill = Fill(order.token_id, "sell", price, shares, price * shares, now)
        return ExecutionResult("filled", order, fill, pnl,
                               f"sold {shares:,.0f} @ {price:.3f}, P&L {pnl:+,.2f}")


class LiveCLOBExecutionClient:
    """Real GTC limit orders via the official SDK. Requires private-key creds."""

    def __init__(self, config: dict) -> None:
        self._config = config
        self._clob = None
        self._init_error = ""
        self._init()

    def _init(self) -> None:
        import os

        key = os.getenv("POLYMARKET_PRIVATE_KEY")
        if not key:
            self._init_error = "POLYMARKET_PRIVATE_KEY not set"
            return
        try:
            from py_clob_client.client import ClobClient

            client = ClobClient(
                host=self._config["clob_base"],
                chain_id=self._config.get("polymarket_chain_id", 137),
                key=key,
            )
            client.set_api_creds(client.create_or_derive_api_creds())
            self._clob = client
        except Exception as exc:  # pragma: no cover - needs live creds
            self._init_error = f"CLOB init failed: {exc}"

    def submit(self, order: Order, portfolio: Portfolio) -> ExecutionResult:  # pragma: no cover - live only
        if self._clob is None:
            return ExecutionResult("error", order, reason=f"live disabled: {self._init_error}")
        try:
            from py_clob_client.clob_types import OrderArgs, OrderType

            price = order.ref_price
            shares = order.size_usdc / price if order.side == "buy" else portfolio.positions[order.token_id].shares
            signed = self._clob.create_order(
                OrderArgs(token_id=order.token_id, price=price, size=shares, side=order.side.upper())
            )
            resp = self._clob.post_order(signed, OrderType.GTC)
            return ExecutionResult("filled", order, reason=f"posted GTC: {resp}")
        except Exception as exc:
            return ExecutionResult("error", order, reason=f"post failed: {exc}")
