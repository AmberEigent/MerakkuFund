"""Tests for the paper portfolio ledger."""
from __future__ import annotations

from datetime import datetime, timezone

from pytest import approx

from polyagents.execution.portfolio import Portfolio
from polyagents.execution.types import Fill

NOW = datetime(2026, 6, 8, tzinfo=timezone.utc)


def _buy(pf, token, price, shares):
    pf.apply_buy(Fill(token, "buy", price, shares, price * shares, NOW))


def test_buy_updates_cash_and_position():
    pf = Portfolio(1000.0)
    _buy(pf, "t", 0.50, 100)
    assert pf.cash == 950.0
    assert pf.positions["t"].shares == 100
    assert pf.positions["t"].avg_price == 0.50
    assert pf.exposure() == 50.0


def test_averaging_in():
    pf = Portfolio(1000.0)
    _buy(pf, "t", 0.50, 100)   # 50
    _buy(pf, "t", 0.60, 100)   # 60
    assert pf.positions["t"].shares == 200
    assert pf.positions["t"].avg_price == 0.55   # (50+60)/200


def test_winning_close_books_pnl_and_resets_streak():
    pf = Portfolio(1000.0)
    _buy(pf, "t", 0.50, 100)
    pnl = pf.apply_sell_close("t", 0.60, NOW)
    assert pnl == approx(10.0)                     # (0.6-0.5)*100
    assert pf.realized_pnl() == approx(10.0)
    assert "t" not in pf.positions
    assert pf.consecutive_losses == 0
    assert pf.cash == approx(1010.0)               # 950 + 60


def test_losing_close_increments_streak():
    pf = Portfolio(1000.0)
    _buy(pf, "t", 0.50, 100)
    pf.apply_sell_close("t", 0.40, NOW)
    assert pf.consecutive_losses == 1
    assert pf.realized_pnl() == approx(-10.0)


def test_realized_pnl_on_day_filters_by_date():
    pf = Portfolio(1000.0)
    _buy(pf, "t", 0.50, 100)
    pf.apply_sell_close("t", 0.40, NOW)
    assert pf.realized_pnl_on(NOW) == approx(-10.0)
    assert pf.realized_pnl_on(datetime(2026, 1, 1, tzinfo=timezone.utc)) == 0.0
