"""hunt_alpha — the top-level opportunity scan (core, always-on). Consolidates crypto
mispricings + microstructure flow into one board. Driven by a scripted fake LLM."""
from __future__ import annotations

from polyagents.kernel.controller import KernelController
from polyagents.kernel.capabilities import hunt_alpha_capability
from polyagents.kernel.packs import CORE, kernel_capability_names


class FakeLLM:
    def __init__(self, *replies):
        self.replies = list(replies)

    def invoke(self, messages):
        text = self.replies.pop(0) if self.replies else '{"action":"final","answer":"(end)"}'
        return type("R", (), {"content": text})()


def test_hunt_alpha_is_core_always_on():
    assert "hunt_alpha" in CORE                          # always loaded, not a pack
    assert "hunt_alpha" in kernel_capability_names([])   # present even with no packs selected


def test_hunt_alpha_consolidates_a_board():
    def fn(query):
        return {"query": query, "n_crypto": 1,
                "crypto": [{"question": "BTC above $200k?", "spot": 65000, "strike": 200000,
                            "p_model": 0.02, "market_price": 0.30, "gap": -0.28}],
                "flow": [{"question": "Market A", "flow_imbalance": 0.4, "book_pressure": 0.3,
                          "volume_spike": 3.0, "price_momentum": 0.01, "spread_bps": 120,
                          "score": 0.51, "tradeable": True, "lean": "YES"}],
                "n_flow_scanned": 1}

    llm = FakeLLM('{"action":"call","capability":"hunt_alpha"}',
                  '{"action":"final","answer":"扫到 1 个 crypto 错价 + 1 个资金流信号"}')
    res = KernelController([hunt_alpha_capability(fn)], llm).run("帮我找 alpha")
    assert [s.capability for s in res.trace] == ["hunt_alpha"]
    board = res.facts["alpha_hunt"]
    assert board["crypto"][0]["gap"] == -0.28
    assert board["flow"][0]["score"] == 0.51
