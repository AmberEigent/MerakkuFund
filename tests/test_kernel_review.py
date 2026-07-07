"""evaluate_skill & portfolio_review — core review capabilities (always-on)."""
from __future__ import annotations

from polyagents.kernel.controller import KernelController
from polyagents.kernel.capabilities import (evaluate_skill_capability,
                                             portfolio_review_capability)
from polyagents.kernel.packs import CORE, kernel_capability_names


class FakeLLM:
    def __init__(self, *replies):
        self.replies = list(replies)

    def invoke(self, messages):
        text = self.replies.pop(0) if self.replies else '{"action":"final","answer":"(end)"}'
        return type("R", (), {"content": text})()


def test_review_caps_are_core():
    assert "evaluate_skill" in CORE and "portfolio_review" in CORE
    names = kernel_capability_names([])                  # present with no packs
    assert "evaluate_skill" in names and "portfolio_review" in names


def test_evaluate_skill():
    llm = FakeLLM('{"action":"call","capability":"evaluate_skill"}',
                  '{"action":"final","answer":"未跑赢市场"}')
    res = KernelController([evaluate_skill_capability(lambda q: {"report": "model does NOT beat market"})],
                           llm).run("我们有 alpha 吗")
    assert "beat market" in res.facts["skill_report"]["report"]


def test_portfolio_review():
    llm = FakeLLM('{"action":"call","capability":"portfolio_review"}',
                  '{"action":"final","answer":"空仓"}')
    fn = lambda q: {"portfolio": {"cash": 1000.0, "exposure": 0.0, "realized_pnl": 0.0,
                                  "open_positions": []}, "pnl": "no trades"}
    res = KernelController([portfolio_review_capability(fn)], llm).run("看下我的组合")
    assert res.facts["portfolio_review"]["portfolio"]["cash"] == 1000.0
