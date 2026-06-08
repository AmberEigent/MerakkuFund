"""Tests for the execution circuit breaker."""
from __future__ import annotations

from datetime import datetime, timezone

from polyagents.execution.circuit_breaker import CircuitBreaker
from polyagents.execution.portfolio import ClosedTrade, Portfolio
from polyagents.execution.types import Order, Position
from polyagents.default_config import DEFAULT_CONFIG

NOW = datetime.now(timezone.utc)


def _cfg():
    return DEFAULT_CONFIG.copy()           # bankroll 500, exposure cap 50%, etc.


def _buy_order(token="t", size=100.0):
    return Order(token_id=token, side="buy", size_usdc=size, ref_price=0.50)


def test_allows_normal_entry():
    ok, _ = CircuitBreaker(_cfg()).check(_buy_order(), Portfolio(500.0))
    assert ok


def test_blocks_on_insufficient_cash():
    pf = Portfolio(50.0)
    ok, reason = CircuitBreaker(_cfg()).check(_buy_order(size=100.0), pf)
    assert not ok and "cash" in reason


def test_blocks_on_exposure_cap():
    pf = Portfolio(500.0)
    pf.positions["a"] = Position("a", shares=480, avg_price=0.50)   # exposure 240
    ok, reason = CircuitBreaker(_cfg()).check(_buy_order(token="b", size=50.0), pf)
    assert not ok and "exposure" in reason                          # 240+50 > 250


def test_blocks_on_max_concurrent_positions():
    cfg = _cfg(); cfg["max_concurrent_positions"] = 2; cfg["max_total_exposure_pct"] = 10.0
    pf = Portfolio(5000.0)
    pf.positions["a"] = Position("a", 1, 0.1)
    pf.positions["b"] = Position("b", 1, 0.1)
    ok, reason = CircuitBreaker(cfg).check(_buy_order(token="c", size=10.0), pf)
    assert not ok and "concurrent" in reason


def test_blocks_on_daily_loss_halt():
    pf = Portfolio(500.0)
    pf.closed.append(ClosedTrade("x", -30.0, NOW))                  # > 5% of 500 = 25
    ok, reason = CircuitBreaker(_cfg()).check(_buy_order(), pf)
    assert not ok and "daily loss" in reason


def test_blocks_on_consecutive_losses():
    pf = Portfolio(500.0)
    pf.consecutive_losses = 5
    ok, reason = CircuitBreaker(_cfg()).check(_buy_order(), pf)
    assert not ok and "consecutive" in reason


def test_sell_exit_allowed_only_with_position():
    pf = Portfolio(500.0)
    sell = Order(token_id="t", side="sell", size_usdc=0.0, ref_price=0.50)
    ok, reason = CircuitBreaker(_cfg()).check(sell, pf)
    assert not ok and "no open position" in reason
    pf.positions["t"] = Position("t", 100, 0.5)
    ok, _ = CircuitBreaker(_cfg()).check(sell, pf)
    assert ok
