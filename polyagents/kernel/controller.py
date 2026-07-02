"""The kernel's LLM controller — the brain that decides, each step, *how* to
answer: call a sub-agent/tool, or answer the user directly.

This is the "complete kernel" the mentor asked for: not a fixed pipeline and not a
keyword router, but an LLM-driven loop over a capability registry. Each turn the
model sees the request, the facts gathered so far, and the capabilities runnable
now, then picks the next action. The deterministic goal-directed planner still
exists as a *shortcut* for known chains (data→backtest); the controller is the
primary driver for open-ended requests.

Injected ``llm`` (``.invoke(messages) -> obj with .content``), so it's unit-
testable with a scripted fake — no network in the core.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from .core import Capability, Context, Goal, Step

_SYS = (
    "You are the controller of an agent loop for a prediction-market research "
    "assistant. Each turn you EITHER call one capability (a sub-agent or tool) to "
    "gather what you still need, OR give the final answer to the user. Prefer the "
    "fewest steps: only call a capability when you actually need its result; if you "
    "can already answer, answer.\n"
    "Reply with ONLY one JSON object, nothing else:\n"
    '  {"action": "call", "capability": "<name from the menu>"}\n'
    '  {"action": "final", "answer": "<the answer to the user>"}'
)


@dataclass
class KernelResult:
    """What the controller loop produced."""
    answer: str
    facts: dict = field(default_factory=dict)
    trace: list = field(default_factory=list)   # Step per capability call
    steps: int = 0


def _text_of(resp: Any) -> str:
    text = getattr(resp, "content", resp)
    if isinstance(text, list):
        text = "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in text)
    return str(text)


def _parse(text: str) -> dict:
    """Pull the first JSON object out of the model's reply (tolerant of prose)."""
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except Exception:
        return {}


def _short(v: Any, n: int = 160) -> str:
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, default=str)
    return s if len(s) <= n else s[:n] + "…"


class KernelController:
    """LLM-driven controller over a capability registry.

    ``run(request, **facts)`` seeds the blackboard, then loops: ask the model for
    the next action, run the chosen capability (feeding its result back), until the
    model answers or the step budget runs out. Emits the same event shapes as
    :class:`~polyagents.kernel.core.AgentLoop` so the web layer can stream it.
    """

    def __init__(self, registry: list[Capability], llm, *, max_steps: int = 8,
                 on_event: Callable[[dict], None] | None = None, audit=None) -> None:
        self.registry = list(registry)
        self.llm = llm
        self.max_steps = max_steps
        self.on_event = on_event
        self.audit = audit

    def _emit(self, event: dict) -> None:
        if self.on_event:
            try:
                self.on_event(event)
            except Exception:
                pass

    def _audit(self, event_type: str, **payload) -> None:
        if self.audit is not None:
            try:
                self.audit.log("kernel", event_type, payload, mode="controller")
            except Exception:
                pass

    def _runnable(self, ctx: Context) -> list[Capability]:
        return [c for c in self.registry
                if c.preconditions <= ctx.known and not (c.effects <= ctx.known)]

    def _decide(self, ctx: Context, request: str, runnable: list[Capability],
                notes: list[str]) -> dict:
        menu = "\n".join(
            f"- {c.name}: {c.description} (produces {sorted(c.effects)})"
            for c in runnable) or "- (none)"
        facts = "\n".join(f"- {k}: {_short(v)}" for k, v in ctx.facts.items()
                          if k != "question") or "- (none)"
        steps = "\n".join(notes) or "- (none yet)"
        user = (f"User request: {request}\n\nFacts gathered so far:\n{facts}\n\n"
                f"Capabilities you can call now:\n{menu}\n\nSteps so far:\n{steps}\n\n"
                "Next action? JSON only.")
        try:
            return _parse(_text_of(self.llm.invoke([("system", _SYS), ("user", user)])))
        except Exception:
            return {}

    def run(self, request: str, **facts) -> KernelResult:
        ctx = Context(Goal(frozenset(), {"question": request, **facts}, "kernel"))
        notes: list[str] = []
        self._emit({"type": "loop.start", "goal": [], "label": "kernel"})
        self._audit("loop.start", label="kernel", request=_short(request))
        for i in range(self.max_steps):
            runnable = self._runnable(ctx)
            decision = self._decide(ctx, request, runnable, notes)
            action = str(decision.get("action", "")).lower()
            if action == "final" or (action != "call" and not runnable):
                answer = str(decision.get("answer", "")).strip()
                if answer:
                    return self._finish(ctx, answer, i)
            if action == "call":
                name = str(decision.get("capability", "")).strip()
                cap = next((c for c in runnable if c.name == name), None)
                if cap is None:
                    notes.append(f"- tried to call '{name}' but it is not available now")
                    continue
                self._emit({"type": "capability.start", "name": cap.name})
                try:
                    produced = cap.run(ctx) or {}
                except Exception as exc:                      # surface, let the model re-plan
                    ctx.trace.append(Step(cap.name, [], ok=False, note=str(exc)))
                    notes.append(f"- {cap.name} failed: {exc}")
                    self._audit("capability.error", capability=cap.name, error=str(exc))
                    self._emit({"type": "capability.error", "name": cap.name, "error": str(exc)})
                    continue
                ctx.facts.update(produced)
                keys = list(produced)
                ctx.trace.append(Step(cap.name, keys, ok=True))
                notes.append(f"- called {cap.name} -> {keys}")
                self._audit("capability.ran", capability=cap.name, produced=keys)
                self._emit({"type": "capability.done", "name": cap.name, "produced": keys})
                continue
            # neither a valid call nor a final answer -> nudge once more, then bail
            notes.append("- (no decision; must call a capability or give final answer)")
        return self._finish(ctx, self._forced_answer(ctx, request), self.max_steps)

    def _forced_answer(self, ctx: Context, request: str) -> str:
        """Budget exhausted — make the model answer from whatever we gathered."""
        facts = "\n".join(f"- {k}: {_short(v)}" for k, v in ctx.facts.items() if k != "question")
        user = (f"User request: {request}\n\nFacts gathered:\n{facts or '- (none)'}\n\n"
                "Give the final answer to the user now (plain text).")
        try:
            return _text_of(self.llm.invoke([("system", _SYS), ("user", user)])).strip() \
                or "(no answer)"
        except Exception:
            return "(no answer)"

    def _finish(self, ctx: Context, answer: str, steps: int) -> KernelResult:
        ctx.facts["answer"] = answer
        self._audit("loop.end", steps=steps, path=[s.capability for s in ctx.trace])
        self._emit({"type": "loop.end", "done": True,
                    "path": [s.capability for s in ctx.trace]})
        return KernelResult(answer=answer, facts=ctx.facts, trace=ctx.trace, steps=steps)
