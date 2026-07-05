"""backtest_matrix — strategy × domain sweep (backtest-lab pack)."""
from __future__ import annotations

from polyagents.kernel.controller import KernelController
from polyagents.kernel.capabilities import backtest_matrix_capability
from polyagents.kernel.packs import PACKS, kernel_capability_names


class FakeLLM:
    def __init__(self, *replies):
        self.replies = list(replies)

    def invoke(self, messages):
        text = self.replies.pop(0) if self.replies else '{"action":"final","answer":"(end)"}'
        return type("R", (), {"content": text})()


def test_matrix_in_backtest_lab_pack():
    assert "backtest_matrix" in PACKS["backtest-lab"]["capabilities"]
    assert "backtest_matrix" not in kernel_capability_names([])
    assert "backtest_matrix" in kernel_capability_names(["backtest-lab"])


def test_matrix_reports_cells_and_winners():
    def fn(q):
        return {"query": q, "signals": ["naive", "momentum"], "winners": [("sports", "momentum")],
                "matrix": {
                    "sports": {"n": 20, "signals": {
                        "naive": {"brier_delta": 0.0, "beats_market": False},
                        "momentum": {"brier_delta": 0.006, "beats_market": True}}},
                    "crypto": {"n": 12, "signals": {
                        "naive": {"brier_delta": 0.0, "beats_market": False},
                        "momentum": {"brier_delta": -0.001, "beats_market": False}}}}}
    llm = FakeLLM('{"action":"call","capability":"backtest_matrix"}',
                  '{"action":"final","answer":"momentum@sports 跑赢"}')
    res = KernelController([backtest_matrix_capability(fn)], llm).run("which strategy works where")
    m = res.facts["backtest_matrix"]
    assert ("sports", "momentum") in m["winners"]
    assert m["matrix"]["sports"]["signals"]["momentum"]["beats_market"] is True
