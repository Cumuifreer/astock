# Indicator Rule Builder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Replace the ambiguous signal-mode role dropdown with a practical indicator rule builder where each chosen metric has clear operators, values, units, missing-data behavior, and runtime effects.

**Architecture:** Keep existing strategy presets and legacy parameters compatible, but add a new `strategy_rules` layer that can filter, score, risk-adjust, or display metrics by indicator id. The frontend reads richer indicator metadata to present TradingView-like rule chips; the backend normalizes and executes enabled rules against the analysis frame.

**Tech Stack:** FastAPI service layer, DuckDB-backed analysis pipeline, React + TypeScript frontend, existing CSS design system.

---

### Task 1: Indicator Metadata Contract

**Files:**
- Modify: `backend/app/services/indicator_registry.py`
- Modify: `frontend/src/types.ts`
- Test: `backend/tests/test_indicator_registry.py`

- [x] **Step 1: Write failing registry assertions**

Add a test that verifies executable indicators expose `value_type`, `unit`, `supported_actions`, `supported_operators`, `default_operator`, `analysis_field`, and recommendation metadata. It should also verify display-only Tushare event indicators cannot be added as filters until analysis-frame support exists.

- [x] **Step 2: Run the targeted test**

Run: `pytest backend/tests/test_indicator_registry.py -q`

Expected: failure because those metadata fields are missing.

- [x] **Step 3: Implement metadata defaults**

Extend `data_indicator()` and `strategy_param()` with optional rule-builder metadata. Use conservative defaults: executable data fields can filter/score/display according to their usage, non-analysis-ready fields are display-only, and strategy parameters remain editable legacy controls.

- [x] **Step 4: Update TypeScript types**

Add `StrategyRule`, `RuleAction`, `RuleOperator`, `IndicatorRecommendation`, and optional metadata fields on `IndicatorDefinition`.

- [x] **Step 5: Re-run the registry test**

Run: `pytest backend/tests/test_indicator_registry.py -q`

Expected: pass.

### Task 2: Backend Rule Normalization And Execution

**Files:**
- Modify: `backend/app/services/strategy_service.py`
- Modify: `backend/app/services/analysis_service.py`
- Test: `backend/tests/test_indicators.py`

- [x] **Step 1: Write failing rule execution tests**

Add tests for `strategy_rules`: one `filter` rule should remove rows below a threshold, one `score` rule should increase `signal_score`, one `risk` rule should reduce it, and unsupported/display-only fields should be ignored safely.

- [x] **Step 2: Run the targeted tests**

Run: `pytest backend/tests/test_indicators.py::test_strategy_rules_filter_score_and_risk_candidates -q`

Expected: failure because `strategy_rules` is not normalized or executed.

- [x] **Step 3: Normalize `strategy_rules`**

Add `strategy_rules: []` to `DEFAULT_STRATEGY_CONFIG` and sanitize incoming rules: stable ids, supported actions/operators, numeric coercion, missing policies, enabled flag, optional score/risk weight.

- [x] **Step 4: Execute rules**

Apply enabled filter rules inside `apply_strategy_filters()`, add score/risk adjustments inside `_signal_score()`, and include a `custom_rules` component in `_score_breakdown()`.

- [x] **Step 5: Re-run targeted and existing backend tests**

Run: `pytest backend/tests/test_indicator_registry.py backend/tests/test_indicators.py -q`

Expected: pass.

### Task 3: Strategy Editor Rule Builder

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`

- [x] **Step 1: Add a rule-builder model layer**

Create frontend helpers for default rules, operator labels, action labels, supported action filtering, unit formatting, recommendation chips, and strategy updates to `strategy.strategy_rules`.

- [x] **Step 2: Replace the strategy-page parameter wall**

In `StrategyPanel`, keep the signal-mode and analysis-mode selectors, but render a “规则构建器” section. Show active rules as compact rows: indicator, action chip, operator chip, value inputs, missing policy, recommendation chips, and remove/toggle controls.

- [x] **Step 3: Make indicator addition clear**

Add a searchable indicator picker grouped by the indicator library categories. Only executable indicators can become filter/score/risk rules; observation-only indicators can be added as display rules with explanatory copy.

- [x] **Step 4: Keep legacy compatibility visible but quiet**

Keep existing `SignalModeFieldForm` as a compact compatibility section for old strategy parameters, but make the new rule builder the primary workflow. Avoid naked role dropdowns in the strategy page.

- [x] **Step 5: Build frontend**

Run: `npm run build`

Expected: TypeScript and Vite build pass.

### Task 4: Visual Polish And Verification

**Files:**
- Modify: `frontend/src/styles.css`

- [x] **Step 1: Polish the layout**

Use dense, scan-friendly operator chips, fixed-width value controls, and responsive wrapping so Chinese labels never collide on desktop or mobile.

- [x] **Step 2: Run app locally**

Run: `ASHARE_INTRADAY_SCHEDULER=0 ASHARE_DAILY_BRIEF_SCHEDULER=0 python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000`

Expected: server starts.

- [x] **Step 3: Browser check**

Open the local app, inspect the strategy page, and verify the rule builder is readable, interactive, and does not require horizontal scrolling.

- [x] **Step 4: Final verification**

Run: `pytest backend/tests/test_indicator_registry.py backend/tests/test_indicators.py -q` and `npm run build`.

Expected: both pass.
