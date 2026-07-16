"""prediction-journal pack — log_prediction + prediction_journal (personal calibration).
Selectable, not core. PredictionStore on an in-memory engine; no network."""
from __future__ import annotations

from polyagents.kernel.controller import KernelController
from polyagents.kernel.capabilities import (log_prediction_capability,
                                            prediction_journal_capability)
from polyagents.kernel.packs import CORE, PACKS, kernel_capability_names
from polyagents.storage.predictions import PredictionStore


class FakeLLM:
    def __init__(self, *replies):
        self.replies = list(replies)

    def invoke(self, messages):
        text = self.replies.pop(0) if self.replies else '{"action":"final","answer":"(end)"}'
        return type("R", (), {"content": text})()


def test_prediction_journal_pack_selectable():
    assert "prediction-journal" in PACKS
    assert PACKS["prediction-journal"]["capabilities"] == ["log_prediction", "prediction_journal"]
    for cap in ("log_prediction", "prediction_journal"):
        assert cap not in CORE
        assert cap not in kernel_capability_names([])
        assert cap in kernel_capability_names(["prediction-journal"])


def test_prediction_store_roundtrip_and_scoring():
    store = PredictionStore(":memory:")
    store.log(token_id="t1", condition_id="c1", question="Will A win?", category="sports",
              user_p=0.30, market_p=0.42, note="")
    store.log(token_id="t2", condition_id="c2", question="Will B win?", category="crypto",
              user_p=0.80, market_p=0.60, note="")
    assert len(store.open()) == 2
    # settle t1 as a loss (outcome 0): user 0.30 vs market 0.42 → user Brier lower (closer to 0)
    p = store.open()[0]
    store.mark_resolved(p["id"], 0, round(p["user_p"] ** 2, 4), round(p["market_p"] ** 2, 4))
    allp = store.all()
    resolved = [x for x in allp if x["resolved"]]
    assert len(resolved) == 1 and len(store.open()) == 1
    assert resolved[0]["brier_user"] < resolved[0]["brier_market"]   # user beat the market on this call


def test_log_prediction_routes():
    def fn(query):
        return {"logged": {"question": "Will Spain win?", "user_p": 0.25, "market_p": 0.58,
                           "edge_vs_market": -0.33, "matched_by": "keywords(4)"}}

    llm = FakeLLM('{"action":"call","capability":"log_prediction"}',
                  '{"action":"final","answer":"已记录"}')
    res = KernelController([log_prediction_capability(fn)], llm).run("记录我对西班牙夺冠的预测:25%")
    assert res.facts["prediction_logged"]["logged"]["user_p"] == 0.25
