# Strategy Rule Contract Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make strategy rules honest and explainable by tightening indicator actions, replacing resonance multipliers with rule-referenced bonus scoring, and surfacing display/rule effects in candidate details.

**Architecture:** The backend remains the source of truth for indicator capabilities and strategy normalization. Frontend controls render only supported actions from the indicator library, and candidate details read structured rule/display/resonance results from `metrics_json`. Existing strategy JSON remains compatible through normalization and migration warnings.

**Tech Stack:** Python/FastAPI/Pandas/DuckDB backend, pytest tests, React/TypeScript/Vite frontend, existing CSS.

---

### Task 1: Tighten Indicator Rule Metadata

**Files:**
- Modify: `backend/tests/test_indicator_registry.py`
- Modify: `backend/app/services/indicator_registry.py`
- Modify: `frontend/src/types.ts`

- [x] **Step 1: Write failing registry tests**

Add tests proving analysis-ready indicators do not receive automatic filter actions, `cost_50pct` is display-only, `limit_event` only supports event-state operators, `market_breadth` is not available as an executable stock rule, and rule contract metadata exists.

- [x] **Step 2: Run targeted tests to verify failure**

Run: `python3 -m pytest backend/tests/test_indicator_registry.py -q`

Expected: FAIL because current metadata auto-adds `filter` and event/default metadata is too loose.

- [x] **Step 3: Implement metadata contract**

Remove automatic `filter` insertion in `_rule_builder_meta()`. Add `hard_filter_allowed`, `operator_semantics`, optional coverage/freshness fields, and explicit supported actions/operators for high-risk indicators.

- [x] **Step 4: Update TypeScript metadata types**

Extend `IndicatorDefinition` with `hard_filter_allowed`, `min_coverage_for_filter`, `freshness_required`, `coverage_group`, and `operator_semantics`.

- [x] **Step 5: Run tests**

Run: `python3 -m pytest backend/tests/test_indicator_registry.py -q`

Expected: PASS.

### Task 2: Convert Resonance To Rule-Referenced Bonus

**Files:**
- Modify: `backend/tests/test_strategy_service.py`
- Modify: `backend/tests/test_indicators.py`
- Modify: `backend/app/services/strategy_service.py`
- Modify: `backend/app/services/analysis_service.py`
- Modify: `frontend/src/types.ts`

- [x] **Step 1: Write failing backend tests**

Update strategy normalization tests so `strategy_resonances` use `rule_ids` plus `bonus`, legacy condition/multiplier resonances are converted only when matching existing rules, and unmatched legacy resonances are disabled with migration warnings. Update indicator tests so resonance applies fixed bonus with a cap and no longer multiplies scores.

- [x] **Step 2: Run targeted tests to verify failure**

Run: `python3 -m pytest backend/tests/test_strategy_service.py::test_normalize_preserves_explicit_strategy_resonances backend/tests/test_indicators.py::test_strategy_resonances_apply_visible_score_multiplier -q`

Expected: FAIL because current code still expects `conditions` and `multiplier`.

- [x] **Step 3: Implement normalization**

Change `_normalize_strategy_resonances()` to accept `rule_ids`, `bonus`, `enabled`, and to migrate old condition-based resonances by matching normalized strategy rules. Add `resonance_bonus_cap` to the default config.

- [x] **Step 4: Implement scoring**

Replace `_strategy_resonance_multiplier()` with `_strategy_resonance_bonus()`, apply bonus additively in `_with_strategy_rule_adjustment()`, and update breakdown/reasons from `resonance_multiplier` to `resonance_bonus`.

- [x] **Step 5: Update frontend type**

Change `StrategyResonance` to `rule_ids: string[]` and `bonus: number`.

- [x] **Step 6: Run tests**

Run: `python3 -m pytest backend/tests/test_strategy_service.py backend/tests/test_indicators.py -q`

Expected: PASS.

### Task 3: Surface Rule Results And Display Metrics

**Files:**
- Modify: `backend/tests/test_indicators.py`
- Modify: `backend/app/services/analysis_service.py`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`

- [x] **Step 1: Write failing backend tests**

Add tests proving display rules do not change score but populate `display_metrics`, score/risk rules populate `strategy_rule_results`, and unsupported filters produce a warning/funnel note instead of silently disappearing.

- [x] **Step 2: Run targeted tests to verify failure**

Run: `python3 -m pytest backend/tests/test_indicators.py::test_strategy_display_rules_add_display_metrics_without_changing_score -q`

Expected: FAIL because structured rule/display results do not exist.

- [x] **Step 3: Implement structured rule results**

Add helpers to compute rule results per candidate, display metrics, and unsupported rule warnings. Store these inside candidate dicts so they persist through `metrics_json`.

- [x] **Step 4: Update candidate detail UI**

Render custom rule effects, resonance bonus, display fields, and warnings in `CandidateScoreDetails`. Keep table columns stable.

- [x] **Step 5: Run tests and frontend build**

Run: `python3 -m pytest backend/tests/test_indicators.py -q`

Run: `npm --prefix frontend run build`

Expected: both PASS.

### Task 4: Redesign Strategy Controls Around Honest Actions

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`

- [x] **Step 1: Update rule builder filtering**

Filter out market-context indicators from stock rule picker, show capability chips from `supported_actions`, and prevent display-only indicators from becoming score/filter/risk rules.

- [x] **Step 2: Replace resonance builder UI**

Make `StrategyResonanceBuilder` select existing enabled rules, not raw indicators. Remove default draft indicator selection, multiplier labels, and condition threshold editing. Use fixed bonus options.

- [x] **Step 3: Quiet compatibility parameters**

Make legacy/advanced runtime parameters default closed and update copy from “参数墙” wording toward core/advanced controls without changing the underlying profile builder yet.

- [x] **Step 4: Build frontend**

Run: `npm --prefix frontend run build`

Expected: PASS.

### Task 5: Full Verification And Commit

**Files:**
- All touched files

- [x] **Step 1: Run backend tests**

Run: `python3 -m pytest backend/tests/test_indicator_registry.py backend/tests/test_strategy_service.py backend/tests/test_indicators.py backend/tests/test_analysis_frame.py -q`

Expected: PASS.

- [x] **Step 2: Run frontend build**

Run: `npm --prefix frontend run build`

Expected: PASS.

- [x] **Step 3: Inspect git diff**

Run: `git status --short --branch` and `git diff --stat`

Expected: only planned files changed.

- [x] **Step 4: Commit**

Run: `git add docs/superpowers/plans/2026-05-27-strategy-rule-contract-fixes.md backend/tests/test_indicator_registry.py backend/tests/test_strategy_service.py backend/tests/test_indicators.py backend/app/services/indicator_registry.py backend/app/services/strategy_service.py backend/app/services/analysis_service.py frontend/src/types.ts frontend/src/App.tsx frontend/src/styles.css`

Run: `git commit -m "Fix strategy rule contracts"`

Expected: local `main` has one implementation commit after the spec/plan commits.
