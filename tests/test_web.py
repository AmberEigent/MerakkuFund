"""Tests for the web chat layer (no LLM / no network)."""
from __future__ import annotations


def test_build_tools_exposes_the_trading_surface():
    from polyagents.web.agent import build_tools

    tools = build_tools()
    names = {t.name for t in tools}
    for expected in ("scan_markets", "market_snapshot", "size_position",
                     "paper_execute", "portfolio_status", "settle_markets",
                     "pnl_report", "evaluation_report"):
        assert expected in names


def test_system_prompt_is_the_skill():
    from polyagents.web.agent import system_prompt

    sp = system_prompt()
    low = sp.lower()
    assert "polymarket" in low and "scan_markets" in sp and "p_true" in sp
    assert not sp.startswith("---")            # frontmatter stripped


def test_server_app_builds_with_routes():
    from polyagents.web.server import app

    paths = {r.path for r in app.routes}
    assert "/" in paths
    assert "/api/chat" in paths
