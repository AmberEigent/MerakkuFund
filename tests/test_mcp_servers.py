"""Tests for the no-key MCP servers (tool registration + compliance math)."""
from __future__ import annotations

from pytest import approx


def _tool_names(server_mod) -> set:
    return {t.name for t in server_mod.mcp._tool_manager.list_tools()}


def test_crypto_server_registers_tools():
    from polyagents.mcp_servers import crypto
    assert {"crypto_price", "crypto_24h", "crypto_klines"} <= _tool_names(crypto)


def test_polydata_server_registers_tools():
    from polyagents.mcp_servers import polydata
    assert {"list_events", "recent_trades", "price_history"} <= _tool_names(polydata)


def test_compliance_server_registers_tools():
    from polyagents.mcp_servers import compliance
    assert {"verify_trade_math", "audit_log", "risk_limits"} <= _tool_names(compliance)


def test_verify_trade_math_passes_consistent_trade():
    from polyagents.mcp_servers.compliance import verify_trade_math
    # p_true 0.70 vs 0.50: edge 0.20, quarter-Kelly capped at 5% -> $25 of $500
    r = verify_trade_math(p_true=0.70, market_price=0.50, size_usdc=25.0,
                          days_to_expiry=20, bankroll=500.0)
    assert r["pass"] is True
    assert r["expected_size_usdc"] == approx(25.0)
    assert r["edge"] == approx(0.20)


def test_verify_trade_math_flags_oversized():
    from polyagents.mcp_servers.compliance import verify_trade_math
    r = verify_trade_math(p_true=0.70, market_price=0.50, size_usdc=100.0,
                          days_to_expiry=20, bankroll=500.0)
    assert r["pass"] is False
    assert any("exceeds cap" in f for f in r["flags"])


def test_verify_trade_math_flags_long_dated_low_apy():
    from polyagents.mcp_servers.compliance import verify_trade_math
    # small edge over a long horizon -> APY below floor
    r = verify_trade_math(p_true=0.55, market_price=0.50, size_usdc=10.0,
                          days_to_expiry=400, bankroll=500.0)
    assert any("APY" in f for f in r["flags"])


def test_risk_limits_exposes_config():
    from polyagents.mcp_servers.compliance import risk_limits
    lims = risk_limits()
    assert lims["edge_floor"] == 0.06 and "max_position_fraction" in lims
