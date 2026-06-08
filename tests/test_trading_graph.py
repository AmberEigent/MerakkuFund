"""End-to-end Layer 1+2+3 trading graph with fakes (no network, no key)."""
from __future__ import annotations

from polyagents.dataflows.news import NewsClient
from polyagents.default_config import DEFAULT_CONFIG
from polyagents.execution.agent import create_execution_agent
from polyagents.execution.circuit_breaker import CircuitBreaker
from polyagents.execution.clients import PaperExecutionClient
from polyagents.execution.portfolio import Portfolio
from polyagents.graph.setup import build_trading_graph
from polyagents.graph.state import build_initial_state


def _trading_graph(config, fake_client, fake_llm, portfolio):
    execute = create_execution_agent(
        PaperExecutionClient(slippage_bps=config["paper_slippage_bps"]),
        portfolio,
        CircuitBreaker(config),
    )
    return build_trading_graph(
        fake_client, NewsClient(api_key=None), config, fake_llm, execute,
    )


def test_buy_decision_executes_into_portfolio(fake_client, fake_llm, sample_market):
    config = DEFAULT_CONFIG.copy()
    config["max_spread_bps"] = 1000.0          # let the fake book's ~444bps pass
    pf = Portfolio(config["bankroll_usdc"])
    graph = _trading_graph(config, fake_client, fake_llm, pf)

    final = graph.invoke(build_initial_state(sample_market, as_of="2026-06-08T00:00:00+00:00"))

    assert final["trade_decision"].action == "buy"
    assert final["execution_result"].status == "filled"
    assert len(pf.positions) == 1               # paper position opened
    assert pf.cash < config["bankroll_usdc"]    # cash deployed
    assert "execution" in final["execution_report"].lower()


def test_hold_decision_skips_execution(fake_client, fake_llm, sample_market):
    config = DEFAULT_CONFIG.copy()              # default 300bps gate trips on ~444bps -> hold
    pf = Portfolio(config["bankroll_usdc"])
    graph = _trading_graph(config, fake_client, fake_llm, pf)
    final = graph.invoke(build_initial_state(sample_market, as_of="2026-06-08T00:00:00+00:00"))
    assert final["trade_decision"].action == "hold"
    assert final["execution_result"].status == "skipped"
    assert not pf.positions
