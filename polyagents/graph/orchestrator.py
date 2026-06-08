"""PolyAgentsGraph — the run entrypoint.

Wires up the read-only clients, compiles the graph once, and runs it per
market. Mirrors TradingAgents' ``TradingAgentsGraph`` shape (build once, run per
target).

  * ``collect(market)``  — Layer 1 only (deterministic data collection).
  * ``analyze(market)``  — Layer 1 + Layer 2 (signal → decision → reflection);
                           needs an LLM (``ANTHROPIC_API_KEY``), or inject one.

Quick read-only data smoke test against the most-active market:

    python -m polyagents
"""
from __future__ import annotations

from typing import Any

from polyagents.dataflows.forecaster import CandleForecaster, NullForecaster
from polyagents.dataflows.news import NewsClient
from polyagents.dataflows.polymarket_client import PolymarketDataClient
from polyagents.dataflows.sentiment import LexiconSentimentScorer, SentimentScorer
from polyagents.dataflows.types import Market
from polyagents.dataflows.utils import utcnow
from polyagents.default_config import DEFAULT_CONFIG
from polyagents.execution.agent import create_execution_agent
from polyagents.execution.circuit_breaker import CircuitBreaker
from polyagents.execution.clients import (
    ExecutionClient,
    LiveCLOBExecutionClient,
    PaperExecutionClient,
)
from polyagents.execution.portfolio import Portfolio

from .setup import build_analysis_graph, build_data_collection_graph, build_trading_graph
from .state import build_initial_state


class PolyAgentsGraph:
    def __init__(
        self,
        config: dict | None = None,
        scorer: SentimentScorer | None = None,
        forecaster: CandleForecaster | None = None,
        llm: Any | None = None,
        execution_client: ExecutionClient | None = None,
    ) -> None:
        self.config = config or DEFAULT_CONFIG.copy()
        self.client = PolymarketDataClient.from_config(self.config)
        self.news_client = NewsClient(self.config.get("tavily_api_key"))
        # FinGPT / Kronos seams — swap these for model-backed implementations later.
        self.scorer = scorer or LexiconSentimentScorer()
        self.forecaster = forecaster or NullForecaster()
        self._llm = llm                 # lazily built on first analyze() if None
        self._data_graph = None
        self._analysis_graph = None
        self._trading_graph = None

        # Layer 3 — persistent across markets (held here, not in per-run state).
        self.portfolio = Portfolio(starting_cash=self.config["bankroll_usdc"])
        self.circuit_breaker = CircuitBreaker(self.config)
        self.execution_client = execution_client or self._default_execution_client()

    def _default_execution_client(self) -> ExecutionClient:
        if self.config.get("execution_mode") == "live":
            return LiveCLOBExecutionClient(self.config)
        return PaperExecutionClient(slippage_bps=self.config["paper_slippage_bps"])

    # ----- graphs (compiled lazily) -----------------------------------------

    @property
    def data_graph(self):
        if self._data_graph is None:
            self._data_graph = build_data_collection_graph(
                self.client, self.news_client, self.config,
                scorer=self.scorer, forecaster=self.forecaster,
            )
        return self._data_graph

    def _get_llm(self):
        if self._llm is None:
            from langchain_anthropic import ChatAnthropic

            self._llm = ChatAnthropic(
                model=self.config["anthropic_model"],
                temperature=self.config.get("anthropic_temperature", 0.0),
            )
        return self._llm

    @property
    def analysis_graph(self):
        if self._analysis_graph is None:
            self._analysis_graph = build_analysis_graph(
                self.client, self.news_client, self.config, self._get_llm(),
                scorer=self.scorer, forecaster=self.forecaster,
            )
        return self._analysis_graph

    @property
    def trading_graph(self):
        if self._trading_graph is None:
            execute_node = create_execution_agent(
                self.execution_client, self.portfolio, self.circuit_breaker,
            )
            self._trading_graph = build_trading_graph(
                self.client, self.news_client, self.config, self._get_llm(), execute_node,
                scorer=self.scorer, forecaster=self.forecaster,
            )
        return self._trading_graph

    # ----- runs --------------------------------------------------------------

    def collect(self, market: Market, as_of: str | None = None) -> dict[str, Any]:
        """Layer 1 only: data collection for one market; returns final state."""
        as_of = as_of or utcnow().isoformat()
        return self.data_graph.invoke(build_initial_state(market, as_of))

    def analyze(self, market: Market, as_of: str | None = None) -> dict[str, Any]:
        """Layer 1 + Layer 2: collect, then signal → decision → reflection."""
        as_of = as_of or utcnow().isoformat()
        return self.analysis_graph.invoke(build_initial_state(market, as_of))

    def trade(self, market: Market, as_of: str | None = None) -> dict[str, Any]:
        """Layer 1 + 2 + 3: analyse then execute (paper by default) through the
        circuit breaker; the portfolio persists across calls."""
        as_of = as_of or utcnow().isoformat()
        return self.trading_graph.invoke(build_initial_state(market, as_of))

    def most_active_market(self) -> Market | None:
        """Discovery helper: the single most-active tradeable side right now."""
        raw = self.client.list_active_markets(limit=self.config["markets_limit"])
        markets = self.client.to_markets(raw)
        return markets[0] if markets else None

    def close(self) -> None:
        self.client.close()


def _format_state(state: dict[str, Any]) -> str:
    lines = [
        "=" * 70,
        state["market_context"],
        "=" * 70,
        f"\n[price]\n{state['price_report']}",
        f"\n[volume]\n{state['volume_report']}",
        f"\n[orderbook]\n{state['orderbook_report']}",
        f"\n[trades_flow]\n{state['trades_flow_report']}",
        f"\n[news]\n{state['news_report']}",
        f"\n[features]\n{state['features_report']}",
    ]
    # Layer 2/3 sections appear only when analyze()/trade() ran.
    for key, label in (("signal_report", "signal"), ("decision_report", "decision"),
                       ("reflection_report", "reflection"), ("execution_report", "execution")):
        if state.get(key):
            lines.append(f"\n[{label}]\n{state[key]}")
    return "\n".join(lines)


def main() -> None:
    ta = PolyAgentsGraph()
    try:
        market = ta.most_active_market()
        if market is None:
            print("No active markets returned by Gamma.")
            return
        state = ta.collect(market)
        print(_format_state(state))
    finally:
        ta.close()


if __name__ == "__main__":
    main()
