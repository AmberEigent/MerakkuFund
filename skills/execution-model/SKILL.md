---
name: execution-model
description: Paper execution and transaction-cost modeling for Polymarket. Use when the user asks about fills, slippage, order sizing, portfolio exposure, or realistic execution assumptions.
source: HKUDS/Vibe-Trading agent/src/skills/execution-model
---

# Execution model

Use this skill to keep MerakkuFund execution realistic. It adapts
Vibe-Trading's slippage and impact discipline to Polymarket's CLOB and
MerakkuFund's paper-execution tools.

## Workflow

1. Use `market_snapshot(token_id)` to inspect spread, depth, and book pressure.
2. Use `size_position(p_true, token_id)` before any order. It applies
   calibrated edge, fractional Kelly, and hard risk gates.
3. If the decision is buy or sell, use `paper_execute(token_id, side, size_usdc)`.
   The paper client walks the book where available instead of assuming a free
   mid-price fill.
4. Use `portfolio_status()` after execution to confirm cash, exposure, open
   positions, and realized P&L.

## Assumptions

- Default execution is paper only.
- Spread and order-book depth are part of the cost model.
- Large orders should be sized against available liquidity, not just bankroll.
- A `hold` from `size_position` is binding unless the user changes the
  probability estimate and reruns sizing.

## Guardrails

- Never imply a paper fill is a live fill.
- Never bypass the circuit breaker or portfolio exposure checks.
- If live execution is requested, confirm that the user explicitly wants real
  trading and that the live CLOB configuration is present.
