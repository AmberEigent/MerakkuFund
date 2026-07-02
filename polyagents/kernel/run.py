"""Unified entry — every mode runs through the ONE kernel loop.

``run_mode(mode, …)`` is the convergence point: Ask, Strategy and Research all
build a per-mode capability registry and run the same :class:`AgentLoop`. ReAct
and the Strategy supervisor are invoked *as capabilities*, not as top-level
orchestrators. (Wiring the web SSE endpoints to this — with a streaming kernel —
is the next step; this is the programmatic entry + convergence.)
"""
from __future__ import annotations

from .core import AgentLoop, Context, Goal
from .intent import recognize
from .modes import registry_for


def _goal_for(mode: str, request: str | None, facts: dict) -> Goal:
    if mode == "strategy":
        return Goal(frozenset({"decision"}), {"market": facts.get("market")}, "strategy")
    if mode in ("research", "lab"):
        return Goal(frozenset({"backtest_report"}),
                    {"event": facts.get("event") or request}, "backtest")
    if mode == "ask":
        return recognize(request or "", event=facts.get("event"))
    return recognize(request or "")


def run_mode(mode: str, *, request: str | None = None, registry: list | None = None,
             max_steps: int = 12, fallback_planner=None, audit=None,
             on_event=None, **facts) -> Context:
    """Run ``mode`` through the kernel. ``registry`` overrides the wiring (tests)."""
    reg = registry if registry is not None else registry_for(mode)
    goal = _goal_for(mode, request, facts)
    loop = AgentLoop(reg, max_steps=max_steps, fallback_planner=fallback_planner,
                     audit=audit, on_event=on_event)
    return loop.run(goal)
