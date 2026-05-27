# Feature-Driven Strategy Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the user-visible signal-mode and interaction-term strategy workflow with a feature-driven strategy engine while preserving low-risk legacy strategy values.

**Architecture:** Keep the database schema compatible for existing reports, but normalize every strategy into a feature-driven configuration before execution. The analysis frame computes all relevant feature families, the strategy engine applies explicit filters/scores/risks, and the frontend presents grouped indicators without signal-mode or combo-multiplier controls.

**Tech Stack:** Python/FastAPI/DuckDB/Pandas backend, pytest backend tests, React/TypeScript/Vite frontend.

---

### Task 1: Lock Migration Behavior

**Files:**
- Modify: `backend/tests/test_strategy_service.py`
- Modify: `backend/app/services/strategy_service.py`

- [x] **Step 1: Write failing tests**

Add tests asserting that old `signal_mode` inputs normalize to `feature_driven`, old `strategy_interactions` are dropped with migration warnings, low-risk numeric fields are preserved, and `analysis_engines` are no longer inferred from interactions.

- [x] **Step 2: Run tests to verify failure**

Run: `pytest backend/tests/test_strategy_service.py -q`

Expected: FAIL because normalization still preserves `signal_mode` and `strategy_interactions`.

- [x] **Step 3: Implement migration normalization**

Update `DEFAULT_STRATEGY_CONFIG`, `normalize_strategy_config`, `_infer_analysis_engines`, `_strategy_summary`, system presets, and config hashing so saved configs are feature-driven and contain migration metadata for dropped fields.

- [x] **Step 4: Run tests to verify pass**

Run: `pytest backend/tests/test_strategy_service.py -q`

Expected: PASS.

### Task 2: Remove Interaction Multipliers From Execution

**Files:**
- Modify: `backend/tests/test_indicators.py`
- Modify: `backend/app/services/analysis_service.py`

- [x] **Step 1: Write failing tests**

Change the interaction test so two otherwise equivalent candidates keep equal scores even if a legacy `strategy_interactions` payload is supplied. Add a signal-mode deletion test showing legacy `signal_mode` values no longer branch execution.

- [x] **Step 2: Run tests to verify failure**

Run: `pytest backend/tests/test_indicators.py::test_strategy_interactions_are_ignored_by_feature_engine backend/tests/test_indicators.py::test_legacy_signal_mode_does_not_select_runtime_branch -q`

Expected: FAIL because interactions still multiply scores and signal modes still select filters.

- [x] **Step 3: Implement feature-driven filtering/scoring**

Update `apply_strategy_filters`, `_rank_candidates`, `_signal_type`, `_signal_score`, `_score_breakdown`, `_freshness_metrics`, `_candidate_reasons`, and interpretation helpers so runtime branches depend on explicit feature fields and rules, not `signal_mode`. Keep `signal_score` as a persisted column alias for compatibility, but treat it as `strategy_score` in code comments and UI wording.

- [x] **Step 4: Run tests to verify pass**

Run: `pytest backend/tests/test_indicators.py -q`

Expected: PASS.

### Task 3: Make Feature Frame Tushare-Ready

**Files:**
- Modify: `backend/tests/test_analysis_frame.py`
- Modify: `backend/app/services/analysis_service.py`
- Modify: `backend/app/services/indicator_registry.py`

- [x] **Step 1: Write failing tests**

Add analysis-frame tests proving moneyflow, limit events, chips, top-list, and THS concept fields enter candidate rows when source tables contain data.

- [x] **Step 2: Run tests to verify failure**

Run: `pytest backend/tests/test_analysis_frame.py -q`

Expected: FAIL for currently display-only fields.

- [x] **Step 3: Add feature enrichment**

Extend analysis-frame enrichment to add `main_net_amount`, `net_mf_amount`, `limit_event`, `limit_open_times`, `limit_fd_amount`, `top_list_net_amount`, `top_inst_net_buy`, `hot_money_net_amount`, `cyq_winner_rate`, `cost_50pct`, chip-distance fields, and source dates. Mark executable indicators as analysis-ready where frame coverage exists.

- [x] **Step 4: Run tests to verify pass**

Run: `pytest backend/tests/test_analysis_frame.py -q`

Expected: PASS.

### Task 4: Retire Signal Mode APIs From Bootstrap

**Files:**
- Modify: `backend/tests/test_indicator_registry.py`
- Modify: `backend/app/api/routes.py`
- Modify: `backend/app/services/indicator_registry.py`

- [x] **Step 1: Write failing tests**

Assert `indicator_library()` returns no editable signal-mode templates and no interaction counts, while still returning categories and indicators.

- [x] **Step 2: Run tests to verify failure**

Run: `pytest backend/tests/test_indicator_registry.py -q`

Expected: FAIL because signal mode templates and interaction counts still appear.

- [x] **Step 3: Remove signal-mode bootstrap dependency**

Stop creating `SignalModeService` in API startup, stop seeding modes, have `/api/bootstrap` and `/api/indicators` call `indicator_library()` directly, and make legacy `/api/signal-modes` routes return `410 Gone` if kept.

- [x] **Step 4: Run tests to verify pass**

Run: `pytest backend/tests/test_indicator_registry.py -q`

Expected: PASS.

### Task 5: Redesign Strategy Page Surface

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`

- [x] **Step 1: Compile before changes**

Run: `npm --prefix frontend run build`

Expected: current build result captured before UI edits.

- [x] **Step 2: Remove signal-mode and interaction UI**

Delete signal-mode API calls from the frontend API layer, remove `SignalModeManager` props and interaction builder rendering, update strategy readouts to say `策略分数`, update indicator library copy to remove combo-multiplier language, and show migration warnings when present.

- [x] **Step 3: Preserve grouped indicator editor**

Keep `SignalModeFieldForm` as the grouped parameter editor, backed by the strategy-parameter profile built from indicator metadata. Keep the dense dark financial UI and avoid nested cards.

- [x] **Step 4: Build frontend**

Run: `npm --prefix frontend run build`

Expected: PASS.

### Task 6: Full Verification And Commit

**Files:**
- All touched files

- [x] **Step 1: Run backend tests**

Run: `pytest backend/tests/test_strategy_service.py backend/tests/test_indicators.py backend/tests/test_indicator_registry.py backend/tests/test_analysis_frame.py -q`

Expected: PASS.

- [x] **Step 2: Run frontend build**

Run: `npm --prefix frontend run build`

Expected: PASS.

- [x] **Step 3: Inspect git diff**

Run: `git status --short --branch` and `git diff --stat`

Expected: only planned files changed.

- [x] **Step 4: Commit and push**

Run: `git add ...`, `git commit -m "Replace signal modes with feature-driven strategy engine"`, `git push origin main`.

Expected: `main` is pushed to `origin/main`.
