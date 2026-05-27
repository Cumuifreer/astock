# Unified Strategy Rule Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Combine strategy rules and combination resonance into one frontend workspace while preserving backend strategy contracts.

**Architecture:** Keep scoring semantics in the backend. The frontend becomes a single editor surface: rule cards are the source of selectable resonance inputs, and resonance creation is an inline grouping panel that references existing rule ids.

**Tech Stack:** React/TypeScript/Vite frontend, Node built-in test runner for structure regression checks, existing CSS.

---

### Task 1: Lock The Desired UI Shape

**Files:**
- Modify: `frontend/package.json`
- Create: `frontend/tests/strategy-workspace-structure.test.mjs`

- [x] **Step 1: Add a structure test**

Add a Node test that reads `frontend/src/App.tsx` and asserts the editor uses `StrategyRuleWorkspace`, no longer renders separate `<StrategyRuleBuilder>` or `<StrategyResonanceBuilder>` entries, and includes chip-based resonance draft controls.

- [x] **Step 2: Run the test**

Run: `npm --prefix frontend test`

Expected: FAIL before implementation because the current UI still renders separate rule and resonance sections.

### Task 2: Merge The Frontend Workspace

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`

- [x] **Step 1: Replace the two top-level components**

Render a single `StrategyRuleWorkspace` from the strategy editor.

- [x] **Step 2: Move resonance logic into the workspace**

Keep the rule picker and cards, then render an inline resonance panel below the rule cards.

- [x] **Step 3: Replace draft selects with rule chips**

Use enabled `filter` and `score` rules as selectable chips. Creating a resonance requires at least two selected chips.

- [x] **Step 4: Add rule-card resonance badges**

Show whether a rule can participate in resonance and how many enabled resonances currently reference it.

- [x] **Step 5: Preserve legacy recovery**

Keep legacy unmatched resonance cards and their “恢复为补充规则” action.

### Task 3: Verify And Publish

**Files:**
- All touched files

- [x] **Step 1: Run frontend structure test**

Run: `npm --prefix frontend test`

Expected: PASS.

- [x] **Step 2: Run frontend build**

Run: `npm --prefix frontend run build`

Expected: PASS.

- [x] **Step 3: Run backend strategy tests**

Run: `python3 -m pytest backend/tests/test_strategy_service.py backend/tests/test_indicators.py -q`

Expected: PASS, proving the UI-only change did not alter strategy semantics.

- [x] **Step 4: Inspect, commit, and push**

Run `git diff --check`, inspect the diff, commit, and push `main`.
