---
name: memory
description: Maintain reusable research memory for Polymarket decisions. Use after market analysis, paper trades, settlements, or reviews to preserve lessons for future signals.
source: HKUDS/Vibe-Trading persistent memory and MerakkuFund feedback/memory
---

# Memory

Use this skill to preserve durable lessons from research and paper trades. It
adapts Vibe-Trading's persistent-memory discipline to MerakkuFund's
`MemoryStore` and feedback loop.

## Workflow

1. During analysis, note assumptions that affected `p_true`, sizing, or risk
   gates.
2. After `paper_execute`, rely on the framework to log pending trade records.
3. After markets resolve, use `settle_markets()` and `pnl_report()` to inspect
   outcomes.
4. Convert the outcome into a short lesson:
   - what signal worked or failed
   - whether the book/flow read was reliable
   - what should change next time
5. Future signal prompts should carry recent lessons forward before estimating
   a new `p_true`.

## Lesson format

```text
When [market setup], [signal] was/was not reliable because [reason].
Next time, [specific adjustment].
```

## Guardrails

- Memories should be short, falsifiable, and tied to a market or setup.
- Do not store secrets, keys, private user data, or unsupported claims.
- Do not let one lucky win become a broad rule. Prefer patterns confirmed by
  multiple resolved markets.
