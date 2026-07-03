"""Loop→Lab bridge — the promotion_gate capability turns a domain backtest into a
Lab paper-ready verdict (sample / beats-market / ECE / PIT gates). Driven by a
scripted fake LLM; the capability uses an injected fake."""
from __future__ import annotations

from polyagents.kernel.controller import KernelController
from polyagents.kernel.capabilities import promotion_gate_capability


class FakeLLM:
    def __init__(self, *replies):
        self.replies = list(replies)

    def invoke(self, messages):
        text = self.replies.pop(0) if self.replies else '{"action":"final","answer":"(end)"}'
        return type("R", (), {"content": text})()


def _registry(captured):
    def fn(query):
        captured["query"] = query
        return {"domain": "sports", "n": 20, "paper_ready": False, "strategies": [
            {"signal": "naive", "n": 20, "brier_delta": 0.0, "ece": 0.02,
             "gates": {"sample_adequate": False, "beats_market": False,
                       "ece_pass": True, "pit_clean": True, "paper_ready": False},
             "paper_ready": False},
            {"signal": "momentum", "n": 20, "brier_delta": -0.0005, "ece": 0.04,
             "gates": {"sample_adequate": False, "beats_market": False,
                       "ece_pass": True, "pit_clean": True, "paper_ready": False},
             "paper_ready": False}]}
    return [promotion_gate_capability(fn)]


def test_promotion_gate_verdict():
    captured = {}
    llm = FakeLLM('{"action":"call","capability":"promotion_gate"}',
                  '{"action":"final","answer":"没有策略够上 paper"}')
    res = KernelController(_registry(captured), llm).run("这些策略够不够上 paper")
    assert [s.capability for s in res.trace] == ["promotion_gate"]
    v = res.facts["promotion_verdict"]
    assert v["paper_ready"] is False                     # nothing passes the gates
    assert {s["signal"] for s in v["strategies"]} == {"naive", "momentum"}
    # the failing gate is beats_market (no alpha)
    assert all(not s["gates"]["beats_market"] for s in v["strategies"])
