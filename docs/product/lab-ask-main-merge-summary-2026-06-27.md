# AIHF Lab / Ask Merge Summary

> Date: 2026-06-27
> Current main: `f4836ad` (`amber/main`)
> Scope: Lab MVP work, Ask/main integration, final merge into main, and Lab UI/API flow update

## Brief Version

The Lab MVP work has been merged into `main` together with the Ask module work. A follow-up Lab UI/API branch, `codex/lab-ui-flow`, now adds the first actual Lab user flow on top of that foundation:

```text
Create Hypothesis -> Configure/Run Evidence Backtest -> Open EvaluationReport
```

The current `main` already contains both:

- Ask module improvements from the teammate branch: readonly Ask mode, upload support, model selector, workspace/chat UI improvements, and product docs.
- Lab module work from our branch: Lab PRD/design/API contracts, Hypothesis creation, PIT checks, SQLite-backed LabRepository, EvaluationReport gates, Lab API routes, and a BacktestRunner that can produce persisted evidence from stored market collections.

The final integration resolved conflicts between Ask/main and Lab/adapt by preserving both flows:

```text
Ask -> propose / create Hypothesis
Lab -> run backtest -> persist forecasts -> EvaluationReport -> promotion gates
```

Full test suite passed after the merge:

```text
189 passed in 0.70s
```

Full test suite passed after the Lab UI/API flow update:

```text
191 passed in 0.98s
```

The old feature/adapt branches were deleted on GitHub after merge, so future work should start from updated `main`. Direct pushes to `main` are technically possible if the repo allows it, but the safer workflow is still: branch from `main` -> PR -> merge.

## 1. Branch And PR History

### Lab MVP PR

Branch:

```text
codex/lab-module-prd-design-tests
```

Merged via:

```text
PR #5
```

Key commit:

```text
658bc93 feat(lab): add MVP contracts, persistence, and backtest evidence path
```

Purpose:

- Add Lab planning docs.
- Add Lab schemas and API/data contracts.
- Add PIT checks.
- Add SQLite persistence.
- Add EvaluationReport gates.
- Add Lab API routes.
- Add contract and repository tests.

### Main Sync PR

Branch:

```text
codex/sync-main-into-adapt
```

Merged into `main` via:

```text
f4836ad Merge lab/adapt into main
```

Key merge commit before PR:

```text
e7972b7 merge main into adapt for Ask and Lab sync
```

Purpose:

- Bring the Lab MVP work together with the latest Ask module work on `main`.
- Resolve overlapping implementations in runtime, objects, backtest, web server, docs, and skills.
- Remove superseded old skill files after `main` reorganized the skills surface.

## 2. What Changed In Lab

### Product And Design Docs

Added:

- `docs/product/lab-module-PRD.md`
- `docs/design/lab-module-hifi.md`
- `docs/product/lab-module-tests.md`
- `docs/product/lab-module-api-data-contract.md`
- `docs/product/lab-progress-report-2026-06-25.md`

These define:

- Lab product boundaries.
- Lab high-fidelity IA and screen flow.
- API and data contracts.
- Lab test strategy.
- Development progress up to the first PR.

### Lab Python Package

Added or expanded:

- `polyagents/lab/__init__.py`
- `polyagents/lab/schemas.py`
- `polyagents/lab/pit.py`
- `polyagents/lab/repository.py`
- `polyagents/lab/service.py`
- `polyagents/lab/backtest.py`

Lab now supports:

- Creating Hypotheses.
- Validating BacktestRequest inputs.
- Enforcing point-in-time constraints.
- Persisting Hypotheses, forecasts, evaluations, backtest runs, promotion events, and audit events.
- Running a Lab evidence path from Hypothesis to EvaluationReport.
- Reading stored `DataStore.collections` as a first step toward historical replay.

### Evaluation

Added:

- `polyagents/evaluation/report.py`

Implemented:

- `EvalSummary`
- `build_evaluation_summary`
- `promotion_gates`

Key behavior:

- `brier_delta = brier_market - brier_model`
- positive `brier_delta` means the model beats market price
- `beats_market` requires the confidence interval lower bound to be positive
- `sample_adequate` is tracked separately from performance
- paper readiness requires sample adequacy, market-beating CI, ECE pass, and PIT clean

### Lab Persistence

Added:

- `polyagents/lab/repository.py`

SQLite tables:

- `objects`
- `forecasts`
- `evaluations`
- `backtest_runs`
- `promotion_events`
- `audit_events`

Default local DB path:

```text
.polyagents/cache/lab.db
```

Override:

```text
POLYAGENTS_LAB_DB
```

### Lab API Routes

Added to `polyagents/web/server.py`:

- `GET /api/lab/hypotheses`
- `POST /api/lab/hypotheses`
- `GET /api/lab/hypotheses/{id}`
- `POST /api/lab/hypotheses/{id}/backtests`
- `GET /api/lab/backtests/{id}`
- `GET /api/lab/reports/{id}`
- `GET /api/lab/system/status`

These support the first user flow:

```text
Create Hypothesis -> Run Backtest -> Open EvaluationReport
```

## 2.1 Lab UI/API Flow Update

Branch:

```text
codex/lab-ui-flow
```

Purpose:

- Turn the Lab backend chain into a usable browser flow.
- Move the Lab frontend away from the older `/api/objects` hypothesis path.
- Make reports readable from SQLite instead of only from transient in-memory objects.

Files changed:

- `polyagents/web/static/index.html`
- `polyagents/lab/repository.py`
- `tests/test_lab_api_contract.py`
- `tests/test_lab_repository.py`
- `tests/test_web.py`

Implemented user flow:

```text
Lab UI
  -> POST /api/lab/hypotheses
  -> POST /api/lab/hypotheses/{id}/backtests
  -> GET /api/lab/reports/{id}
  -> render report metrics, gates, time window, and market sample
```

Frontend changes:

- Lab list now reads from `GET /api/lab/hypotheses`.
- Selected hypothesis detail now reads from `GET /api/lab/hypotheses/{id}`.
- New hypothesis creation now posts the Lab contract shape:
  - `statement`
  - `category_filter`
  - `feature_set`
  - `prompt_version`
  - `model_version`
  - `lineage`
- Evidence backtest button now posts to `POST /api/lab/hypotheses/{id}/backtests`.
- Report buttons now open `GET /api/lab/reports/{id}`.
- Lab detail panel renders:
  - latest report id
  - Brier model / market
  - Brier delta
  - ECE
  - sample count
  - paper-ready gate
  - PIT warning count
  - first market samples

Persistence changes:

- `evaluations` now stores a full `report_json` column.
- Existing SQLite databases are migrated automatically with:

```text
ALTER TABLE evaluations ADD COLUMN report_json TEXT
```

- `get_report(report_id)` now returns the full persisted EvaluationReport when available.
- Older rows without `report_json` still fall back to the previous summary shape.

Tests added or expanded:

- HTTP contract flow:

```text
POST /api/lab/hypotheses
GET  /api/lab/hypotheses/{id}
POST /api/lab/hypotheses/{id}/backtests
GET  /api/lab/reports/{id}
```

- Repository tests now assert full report persistence:
  - `time_window`
  - `market_sample`
  - `pit_warnings`
- Web tests now assert the Lab UI uses `/api/lab/*` instead of the old alpha-test route.

Validation:

```text
191 passed in 0.98s
```

Browser validation:

- Local FastAPI server opened at `http://127.0.0.1:8000`.
- Lab view loaded.
- Create button was present.
- Lab selected panel rendered.
- No frontend error markers were visible.

## 3. What Changed In Ask / Main

The main branch already contained major Ask work before the Lab sync. The final main keeps those changes.

Ask-related changes include:

- readonly Ask tool surface
- `propose_hypothesis` as a readonly bridge from Ask to Lab
- model selector support
- file upload MVP
- upload parsing/cache utilities
- Ask product PRD and acceptance tests
- high-fidelity Ask prototype/design document
- updated web frontend

Important Ask tests retained:

- `tests/test_ask_module.py`
- `tests/test_uploads.py`
- `tests/test_web.py`

## 4. Merge Conflict Resolutions

### `polyagents/web/server.py`

Conflict reason:

- Lab PR added `/api/lab/*` routes.
- Main added Ask upload, strategy streaming, and model-aware chat changes.

Resolution:

- Preserve both.
- Keep Ask/upload/strategy streaming routes.
- Keep Lab routes.

### `polyagents/lab/backtest.py`

Conflict reason:

- Lab PR introduced `BacktestRunner.run(...)` for Hypothesis evidence persistence.
- Main introduced `BacktestRunner.replay(...)` for historical price replay and alpha testing.

Resolution:

- Keep one `BacktestRunner` with two entrypoints:

```text
replay() -> historical resolved-market alpha replay
run()    -> Lab MVP evidence persistence
```

### `polyagents/runtime/session.py`

Conflict reason:

- Main added `AgentSession`, `PermissionPolicy`, and AuditStore-compatible session logging.
- Lab PR added `PermissionDenied`, `allowed_tools`, and `call_tool` permission enforcement.

Resolution:

- Merge both models.
- Keep readonly/can_trade/can_promote flags.
- Keep allowed tool checks.
- Keep AuditStore compatibility.
- Keep in-memory audit sink for tests.

### `polyagents/objects.py`

Conflict reason:

- Main had a fuller AIHF v0.2 state machine.
- Lab PR had lightweight compatibility helpers and evaluation report helpers.

Resolution:

- Use main's v0.2 object state machine as the primary implementation.
- Preserve compatibility helpers:
  - `FinancialObject`
  - `buildEvaluationReport`
  - `recommendPromotion`

### Skills

Conflict reason:

- Main reorganized and reduced the skills surface.
- Adapt/Lab still had older skill files.

Resolution:

- Follow main's skill reorganization.
- Delete superseded old skill files:
  - `skills/backtest/SKILL.md`
  - `skills/market-data/SKILL.md`
  - `skills/memory/SKILL.md`
  - `skills/report-generation/SKILL.md`
  - `skills/risk-analysis/SKILL.md`

Remaining primary skills:

- `polymarket-trading`
- `market-research`
- `cross-market-arb`

### RAG Store

Conflict / runtime issue:

- Full test suite showed Chroma attempting to write to `~/.cache/chroma`, which is not always writable in sandboxed environments.

Resolution:

- Add in-memory fallback retrieval in `polyagents/rag/store.py`.
- Preserve Chroma when available.
- Fall back to token-overlap search when Chroma writes fail.

## 5. Improvements Compared With Original Main

Compared with the pre-merge main (`0d7bcb0`), current main (`f4836ad`) adds or improves:

### Lab Capability

Original main had Ask and some runtime/object work, but did not have the full Lab MVP foundation.

Current main adds:

- Lab PRD/design/test/API docs.
- Hypothesis schema and creation service.
- Backtest request schema.
- Forecast records.
- LabRepository persistence.
- EvaluationReport generation.
- Lab API routes.
- PIT checks.
- Lab permission tests.

### Evidence-Based Research Flow

Original main supported Ask-side hypothesis proposal, but lacked the full evidence persistence loop.

Current main supports:

```text
Hypothesis -> Backtest -> Forecasts -> EvaluationReport -> Gates
```

This is a meaningful step toward the AIHF v0.2 principle:

> Evaluation before trading.

### Stronger Object / Runtime Integration

Current main now combines:

- v0.2 financial object state machine
- compatibility with earlier Lab object tests
- mode-scoped `AgentSession`
- explicit permission policy
- audit-compatible session logging
- tool-level permission checks

### Better Backtest Architecture

Current main now supports two complementary backtest paths:

- `replay()`: deterministic historical price replay over resolved markets
- `run()`: Lab evidence path that persists forecasts and evaluation reports

This avoids forcing one backtest abstraction to do everything.

### More Robust Local Testing

Current main includes:

- Lab contract tests
- Lab repository tests
- Ask module tests
- upload tests
- object store tests
- runtime audit tests
- alpha/replay tests
- RAG fallback tests

Full suite passed after main merge:

```text
189 passed in 0.70s
```

Full suite passed after Lab UI/API flow update:

```text
191 passed in 0.98s
```

## 6. Current Git State And Recommendation

After PR merge, GitHub deleted the feature/adapt branches:

- `adapt/vibe-trading-skills`
- `codex/lab-module-prd-design-tests`
- `codex/sync-main-into-adapt`
- `raw/vibe-trading-skills`

Only `amber/main` remains as the active remote mainline.

Local `main` has been reset to track:

```text
amber/main
```

Important note:

- `origin/main` still points to the older `wangjasmine528/backtest_skill` repo and should not be used for this project unless intentionally returning to that old repo.
- Use `amber/main` as the project source of truth.

Recommended workflow from now on:

```text
git switch main
git fetch amber --prune
git merge --ff-only amber/main
git switch -c codex/<new-work>
```

Then open a PR back into `main`.

Direct pushes to `main` are possible only if repo permissions allow them, but they are riskier. For product work, backend changes, and UI work, PRs are still the safer default.

## 7. Recommended Next Work

### Product / UI

- Refine Lab UI from prompt-based creation to inline form controls.
- Add Library views for Hypotheses and EvaluationReports.
- Clarify how Ask "Promote to Hypothesis" opens Lab.

### Backend

- Replace heuristic collection scoring with the real signal/calibration pipeline.
- Persisted richer report details are now supported; next step is report filtering/comparison by hypothesis, category, and time window.
- Wire audit events for Lab API calls.

### Data / Evaluation

- Add forward-test ledger for live paper predictions.
- Add bootstrap CI implementation beyond the current normal approximation.
- Add report comparison by category and time window.

### Git Hygiene

- Ignore or clean local-only large directories:
  - `Alpha-devbox/`
  - `MerakkuFund/`
  - `node-v22.21.1-win-x64/`

These are still untracked locally and should not be committed unless intentionally imported.
