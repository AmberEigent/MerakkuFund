from __future__ import annotations

import argparse
import json

import pytest

from scripts.manual_trade_ticket import build_ticket, write_ticket


def _args(**overrides):
    base = {
        "ticket_id": "",
        "created_at": "2026-07-20T00:00:00Z",
        "status": "open",
        "signal_source": "lab-monitor",
        "strategy_id": "momentum-v1",
        "hypothesis_id": "hyp_demo",
        "report_id": "eval_demo",
        "monitor_snapshot": "",
        "p_cal": "0.62",
        "market_price_at_signal": "0.54",
        "min_edge": "0.08",
        "trigger_rule": "BUY only if current price <= max_entry_price and edge remains positive.",
        "question": "Will Team A win?",
        "market_url": "https://polymarket.com/event/demo",
        "market_token_id": "123",
        "outcome": "YES",
        "category": "sports",
        "side": "buy",
        "size_usdc": "10",
        "entry_price": "0.55",
        "max_entry_price": "0.57",
        "executed_at": "",
        "operator": "tester",
        "exit_plan": "Hold until resolution.",
        "stop_price": "0.45",
        "take_profit_price": "0.75",
        "exit_price": "",
        "screenshot_path": "",
        "notes": "demo",
    }
    base.update(overrides)
    return argparse.Namespace(**base)


def test_build_manual_trade_ticket(tmp_path):
    ticket = build_ticket(_args())
    path = write_ticket(ticket, tmp_path)

    saved = json.loads(path.read_text())
    assert saved["mode"] == "manual_live_validation"
    assert saved["risk_limits"]["auto_execution"] is False
    assert saved["execution"]["size_usdc"] == 10
    assert saved["execution"]["estimated_shares"] == round(10 / 0.55, 6)
    assert saved["signal"]["strategy_id"] == "momentum-v1"
    assert (tmp_path / "manual_trade_tickets.jsonl").exists()


def test_ticket_rejects_size_above_manual_limit():
    with pytest.raises(ValueError, match="size_usdc must be <= 20"):
        build_ticket(_args(size_usdc="25"))


def test_ticket_rejects_price_above_trigger():
    with pytest.raises(ValueError, match="entry_price is above max_entry_price"):
        build_ticket(_args(entry_price="0.60", max_entry_price="0.57"))
