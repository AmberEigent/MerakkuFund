"""Goal-1 acceptance — a request to analyze one market runs the loop end to end:
resolve_market → analyze_market, producing the structured framework
(explore → reason → data analysis → backtest comparison → conclusion). Driven by a
scripted fake LLM (no network); the capabilities use injected fakes."""
from __future__ import annotations

from polyagents.kernel.controller import KernelController
from polyagents.kernel.capabilities import (analyze_market_capability,
                                             resolve_market_capability)


class FakeLLM:
    def __init__(self, *replies: str):
        self.replies = list(replies)
        self.prompts: list[str] = []

    def invoke(self, messages):
        self.prompts.append(messages[-1][1])
        text = self.replies.pop(0) if self.replies else '{"action":"final","answer":"(end)"}'
        return type("R", (), {"content": text})()


def _framework_result(ref):
    return {
        "market": {"token_id": ref["token_id"], "question": "Will X happen?",
                   "price": 0.42, "category": "politics"},
        "explore": {"price_report": "…", "orderbook_report": "…"},
        "microstructure": {"book_pressure": 0.3, "flow_imbalance": -0.1},
        "reasoning": {"p_true": 0.55, "direction": "yes", "conviction": "medium",
                      "rationale": "informed buying, thin ask"},
        "backtest": {"n_markets": 12, "brier_delta": 0.03, "beats_market": True,
                     "ci": [0.01, 0.05]},
        "similar_markets": [{"question": "Similar past?", "resolved_winner": "YES"}],
        "conclusion": {"action": "buy", "edge": 0.13, "p_calibrated": 0.5,
                       "annualized_edge": 0.4, "size_usdc": 50.0,
                       "reasons": ["edge above floor"], "risk_flags": ["thin book"]},
    }


def _registry(captured):
    def resolve(query):
        captured["resolved_query"] = query
        return {"token_id": "tok_1", "question": "Will X happen?", "price": 0.42}

    def analyze(ref):
        captured["analyzed_ref"] = ref
        return _framework_result(ref)

    return [resolve_market_capability(resolve), analyze_market_capability(analyze)]


def test_analyze_market_runs_resolve_then_framework():
    captured: dict = {}
    llm = FakeLLM('{"action":"call","capability":"resolve_market"}',
                  '{"action":"call","capability":"analyze_market"}',
                  '{"action":"final","answer":"分析完成:建议 BUY"}')
    res = KernelController(_registry(captured), llm).run("分析一下 Will X happen 这个市场")
    assert [s.capability for s in res.trace] == ["resolve_market", "analyze_market"]
    a = res.facts["market_analysis"]
    # all five framework sections present
    for section in ("reasoning", "microstructure", "backtest", "similar_markets", "conclusion"):
        assert section in a
    assert a["reasoning"]["p_true"] == 0.55            # ② reasoning
    assert a["backtest"]["n_markets"] == 12            # ③ historical comparison
    assert a["conclusion"]["action"] == "buy"          # ⑤ conclusion
    assert captured["analyzed_ref"]["token_id"] == "tok_1"


def test_analyze_market_hidden_until_market_resolved():
    # analyze_market needs `market_ref`; menu must not offer it before resolve_market
    captured: dict = {}
    llm = FakeLLM('{"action":"call","capability":"resolve_market"}',
                  '{"action":"final","answer":"ok"}')
    KernelController(_registry(captured), llm).run("分析这个市场", question="分析这个市场")
    assert "resolve_market" in llm.prompts[0] and "analyze_market" not in llm.prompts[0]
    assert "analyze_market" in llm.prompts[1]           # appears only after market_ref exists
