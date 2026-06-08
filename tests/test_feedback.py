"""Tests for the Layer 4 feedback loop: memory, settlement, reflection, report."""
from __future__ import annotations

from pytest import approx

from polyagents.feedback.memory import MemoryStore
from polyagents.feedback.reflection import reflect_on_outcome
from polyagents.feedback.report import pnl_report
from polyagents.feedback.settlement import resolve_winner, resolve_winning_token, settlement_pnl


# --- memory store ------------------------------------------------------------

def test_memory_record_update_and_lessons(tmp_path):
    store = MemoryStore(tmp_path / "trades.jsonl")
    store.record({"record_id": "a", "status": "pending", "question": "Q1", "lesson": None})
    store.record({"record_id": "b", "status": "pending", "question": "Q2", "lesson": None})
    assert len(store.pending()) == 2

    store.update("a", status="resolved", lesson="buy flow worked")
    assert len(store.pending()) == 1
    assert store.recent_lessons() == ["buy flow worked"]
    # same-question lessons come first
    store.update("b", status="resolved", lesson="news lagged")
    assert store.recent_lessons(question="Q1")[0] == "buy flow worked"


# --- settlement --------------------------------------------------------------

def test_resolve_winner_reads_closed_market():
    yes_won = {"closed": True, "outcomes": '["Yes","No"]', "outcomePrices": '["1","0"]'}
    no_won = {"closed": True, "outcomes": '["Yes","No"]', "outcomePrices": '["0","1"]'}
    open_mkt = {"closed": False, "outcomes": '["Yes","No"]', "outcomePrices": '["0.6","0.4"]'}
    assert resolve_winner(yes_won) == "YES"
    assert resolve_winner(no_won) == "NO"
    assert resolve_winner(open_mkt) is None


def test_resolve_winning_token_is_label_agnostic():
    # custom (non Yes/No) labels — settle must key on the token, not the label
    mkt = {"closed": True, "outcomes": '["Cobolli","Zverev"]',
           "outcomePrices": '["0","1"]', "clobTokenIds": '["tokA","tokB"]'}
    assert resolve_winning_token(mkt) == "tokB"     # Zverev side won
    assert resolve_winning_token({"closed": False}) is None


def test_settlement_pnl_payout():
    assert settlement_pnl(won=True, shares=100, avg_price=0.40) == approx(60.0)   # (1-0.4)*100
    assert settlement_pnl(won=False, shares=100, avg_price=0.40) == approx(-40.0)  # (0-0.4)*100


# --- reflection (fake LLM) ---------------------------------------------------

def test_reflect_on_outcome_returns_lesson(fake_llm):
    rec = {"question": "Q", "side": "YES", "resolved_winner": "YES", "won": True,
           "action": "buy", "p_true": 0.7, "market_price": 0.5, "edge": 0.2,
           "signal_rationale": "flow", "realized_pnl": 60.0, "realized_return": 1.2}
    lesson = reflect_on_outcome(fake_llm, rec)
    assert lesson.summary
    assert lesson.what_to_change


# --- report ------------------------------------------------------------------

def test_pnl_report_aggregates():
    records = [
        {"status": "resolved", "action": "buy", "won": True, "realized_pnl": 60.0, "realized_return": 1.2},
        {"status": "resolved", "action": "buy", "won": False, "realized_pnl": -40.0, "realized_return": -1.0},
        {"status": "pending", "action": "hold"},
    ]
    text = pnl_report(records)
    assert "1/2" in text          # hit rate
    assert "+20.00" in text       # total P&L 60 - 40
    assert "1 pending" in text

    assert "No resolved trades" in pnl_report([{"status": "pending", "action": "hold"}])


# --- memory injection into the signal prompt --------------------------------

def test_signal_agent_injects_recent_lessons(tmp_path):
    from polyagents.agents.schemas import Signal
    from polyagents.agents.signal_agent import create_signal_agent

    store = MemoryStore(tmp_path / "trades.jsonl")
    store.record({"record_id": "a", "status": "resolved", "question": "Q1",
                  "lesson": "watch the ask queue"})

    captured: dict = {}

    class SpyStructured:
        def invoke(self, prompt):
            captured["prompt"] = prompt
            return Signal(direction="yes", p_true=0.6, conviction="low", rationale="r")

    class SpyLLM:
        def with_structured_output(self, schema):
            return SpyStructured()

    node = create_signal_agent(SpyLLM(), memory=store)
    node({"question": "Q1", "raw": {}, "market_price": 0.5})
    assert "watch the ask queue" in captured["prompt"]
    assert "carry-forward" in captured["prompt"]
