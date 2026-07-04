"""Outcome reflection — the post-trade learning step.

After a trade resolves we feed the original decision + signal rationale + the
realised result to the LLM and get back a structured :class:`Lesson`. The lesson
is stored in memory and injected into future signal prompts. This is the
"reflect on realised return" half of TradingAgents' loop (the pre-trade
self-critique lives in the Layer 2 reflection agent).

The ``llm`` only needs ``.with_structured_output(Lesson)``, so a fake works.
"""
from __future__ import annotations

from polyagents.agents.schemas import Lesson

_SYSTEM = """You are reviewing a resolved Polymarket trade to extract a lesson. \
Given the original signal, the decision, and the actual outcome, judge whether \
the reasoning held up. Be specific and honest about what the microstructure / \
flow signal got right or wrong. Return a structured lesson."""


def _build_prompt(record: dict) -> str:
    won = record.get("won")
    verdict = "WON" if won else ("LOST" if won is False else "UNRESOLVED")
    return (
        f"{_SYSTEM}\n\n"
        f"Market: {record.get('question', '')}\n"
        f"Analysed side: {record.get('side')}  |  resolved winner: {record.get('resolved_winner')}\n"
        f"Decision: {record.get('action')} at p_true={record.get('p_true')}, "
        f"price={record.get('market_price')}, edge={record.get('edge')}.\n"
        f"Signal rationale was: {record.get('signal_rationale', '')}\n"
        f"Realised: {verdict}, P&L ${record.get('realized_pnl')}, "
        f"return {record.get('realized_return')}.\n"
        f"What is the lesson for next time on similar markets?"
    )


def reflect_on_outcome(llm, record: dict) -> Lesson:
    from polyagents.llm import structured_output
    return structured_output(llm, Lesson).invoke(_build_prompt(record))
