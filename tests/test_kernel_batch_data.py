"""Batch-data acceptance — the mentor's requirement: an Ask/kernel request like
"批量跑数据" must run the loop end to end, auto-selecting the scan → batch_collect
(and batch_backtest) capabilities and producing a real result. Driven by a
scripted fake LLM (no network); the capabilities use injected fakes."""
from __future__ import annotations

from polyagents.kernel.controller import KernelController
from polyagents.kernel.capabilities import (batch_backtest_capability,
                                             batch_collect_capability,
                                             scan_capability)


class FakeLLM:
    """Returns the next scripted reply per .invoke(); records the prompts it saw."""
    def __init__(self, *replies: str):
        self.replies = list(replies)
        self.prompts: list[str] = []

    def invoke(self, messages):
        self.prompts.append(messages[-1][1])
        text = self.replies.pop(0) if self.replies else '{"action":"final","answer":"(end)"}'
        return type("R", (), {"content": text})()


def _registry(collected):
    def scan(query):
        return {"query": query, "count": 2,
                "markets": [{"token_id": "t1"}, {"token_id": "t2"}]}

    def batch_collect(batch, cap=5):
        for row in batch["markets"]:
            collected.append(row["token_id"])
        return {"n_markets": len(batch["markets"]), "store_counts": {"markets": 2}}

    def batch_backtest(query):
        return {"event": query, "n_markets": 2, "brier_delta": 0.0, "beats_market": False}

    return [scan_capability(scan), batch_collect_capability(batch_collect),
            batch_backtest_capability(batch_backtest)]


def test_batch_run_data_scans_then_collects():
    collected: list[str] = []
    llm = FakeLLM('{"action":"call","capability":"scan_markets"}',
                  '{"action":"call","capability":"batch_collect"}',
                  '{"action":"final","answer":"批量采集完成:2 个市场"}')
    res = KernelController(_registry(collected), llm).run("批量跑数据 crypto")
    assert [s.capability for s in res.trace] == ["scan_markets", "batch_collect"]
    assert collected == ["t1", "t2"]                 # every scanned market was collected
    assert res.facts["collections"]["n_markets"] == 2
    assert "批量采集完成" in res.answer


def test_batch_collect_hidden_until_scan_ran():
    # batch_collect needs `market_batch`; the menu must not offer it before scan
    collected: list[str] = []
    llm = FakeLLM('{"action":"call","capability":"scan_markets"}',
                  '{"action":"final","answer":"ok"}')
    KernelController(_registry(collected), llm).run("批量跑数据", question="批量跑数据")
    assert "scan_markets" in llm.prompts[0] and "batch_collect" not in llm.prompts[0]
    assert "batch_collect" in llm.prompts[1]          # appears only after the batch exists


def test_batch_backtest_reachable_from_the_request():
    collected: list[str] = []
    llm = FakeLLM('{"action":"call","capability":"batch_backtest"}',
                  '{"action":"final","answer":"回测:2 个市场,无 edge"}')
    res = KernelController(_registry(collected), llm).run("批量回测 crypto")
    assert [s.capability for s in res.trace] == ["batch_backtest"]
    assert res.facts["backtest_report"]["n_markets"] == 2
