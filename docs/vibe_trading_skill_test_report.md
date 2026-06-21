# Vibe-Trading Skill Migration Test Report

Date: 2026-06-21

## Scope

Source repository: `https://github.com/HKUDS/Vibe-Trading`

Target repository: `https://github.com/AmberEigen/MerakkuFund`

Skills selected from the user-provided checklist:

- Market Data
- Backtest
- Execution Model
- Risk Analysis
- Report Generation
- Memory

## Migration Summary

| Requested skill | Vibe-Trading source | MerakkuFund target | Status |
|---|---|---|---|
| Market Data | `agent/src/skills/market-microstructure/SKILL.md`, `agent/src/market_data.py` | `skills/market-data/SKILL.md` | Adapted |
| Backtest | `agent/src/skills/backtest-diagnose/SKILL.md` | `skills/backtest/SKILL.md` | Adapted |
| Execution Model | `agent/src/skills/execution-model/SKILL.md` | `skills/execution-model/SKILL.md` | Adapted |
| Risk Analysis | `agent/src/skills/risk-analysis/SKILL.md` | `skills/risk-analysis/SKILL.md` | Adapted |
| Report Generation | `agent/src/skills/report-generate/SKILL.md` | `skills/report-generation/SKILL.md` | Adapted |
| Memory | `agent/src/memory/persistent.py`, `agent/SKILL.md` | `skills/memory/SKILL.md` | Adapted |

## Compatibility Notes

Vibe-Trading is a broad cross-market research application. Its code paths depend
on a separate loader registry, broad market coverage, a larger CLI/web runtime,
and many optional providers. MerakkuFund is already specialized around
Polymarket with a deterministic MCP tool surface. Because of that, the migrated
items are skill-level workflow instructions rather than a direct copy of the
Vibe-Trading runtime.

Directly copying Vibe-Trading implementation modules would add duplicated
market loaders and dependencies that do not match MerakkuFund's architecture.
The better fit is to keep MerakkuFund's existing tools and adapt the methodology:
microstructure discipline, backtest diagnosis, realistic execution assumptions,
risk framing, report format, and durable memory.

## Local Test Plan

The migration is considered runnable under the MerakkuFund framework if:

1. Each new skill is discoverable through the existing skills registry.
2. Each skill has valid frontmatter with `name` and `description`.
3. Existing MCP tools needed by the skills remain registered.
4. The no-network test suite for skills, MCP registration, execution, feedback,
   and web registry passes.

Suggested commands:

```bash
python -m pytest tests/test_web.py tests/test_mcp_server.py tests/test_feedback.py tests/test_vibe_trading_skills.py
```

Executed locally with the repository virtual environment:

```bash
.venv/bin/python -m pytest tests/test_web.py tests/test_mcp_server.py tests/test_feedback.py tests/test_vibe_trading_skills.py
```

Result:

```text
21 passed in 1.32s
```

Full repository verification after migration:

```bash
.venv/bin/python -m pytest
```

Result:

```text
111 passed, 4 warnings in 0.64s
```

During full-suite verification, the existing Chroma RAG tests initially failed
because Chroma's default ONNX embedding tried to write model files under the
home cache (`~/.cache/chroma`) in the sandbox. `polyagents.rag.store` now uses a
small deterministic local embedding function by default, keeping RAG tests and
offline local runs free of model downloads and home-directory writes.

## Skill-by-Skill Result

### Market Data

Runnable through existing tools: `scan_markets`, `market_snapshot`, and
`find_similar_markets`.

The Vibe-Trading source is useful as methodology, especially spread, depth,
liquidity, and order-flow interpretation. The direct market-data loader code was
not copied because MerakkuFund already has Polymarket-specific collectors.

### Backtest

Runnable through existing evaluation and backtest surfaces:
`evaluation_report` and the qlib backtest MCP server where configured.

This is a diagnosis and validation workflow, not a new engine. The migrated
skill focuses on avoiding lookahead, checking zero-trade failures, and comparing
signals against the market-price baseline.

### Execution Model

Runnable through `size_position`, `paper_execute`, and `portfolio_status`.

The skill maps Vibe-Trading's slippage/impact concepts onto MerakkuFund's CLOB
paper execution and circuit breaker. No live trading path is enabled by default.

### Risk Analysis

Runnable through `size_position`, `portfolio_status`, `pnl_report`, and
`evaluation_report`.

The migrated skill reframes VaR/drawdown/stress ideas for binary payout markets:
premium-at-risk, concentration, liquidity exit risk, and calibration risk.

### Report Generation

Runnable as a host-agent skill. It uses MerakkuFund tool outputs to produce a
structured Markdown report.

No separate renderer was copied. The existing framework only needs the skill
instructions to guide report composition.

### Memory

Runnable through the existing feedback loop and `MemoryStore`:
trades are logged, settlement can write outcome lessons, and signal prompts can
inject recent lessons.

The Vibe-Trading persistent-memory implementation was not copied because
MerakkuFund already has a simpler trade-memory loop tailored to Polymarket.

## Recommendation

Keep these six skills as adapted MerakkuFund-native workflows. Do not copy the
larger Vibe-Trading runtime unless a future milestone explicitly needs
cross-market equities, futures, forex, or broker-journal tooling.
