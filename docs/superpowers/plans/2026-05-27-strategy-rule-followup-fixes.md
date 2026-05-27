# Strategy Rule Follow-up Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the strategy rule follow-up issues from GPT Pro and the user report: disappearing resonance rules, missing-value score/risk semantics, risk rules in positive resonance, display-only ambiguity, event-state UX, and remaining inactive-stock data口径 gaps.

**Architecture:** Keep the backend as the source of truth for executable rule semantics and migration. The frontend renders only rule choices that the backend will execute, while giving old unmatched resonances a visible recovery path. Data warehouse and market-environment口径 use the same active-stock definition already introduced in `DataService`.

**Tech Stack:** Python/FastAPI/Pandas/DuckDB backend, pytest tests, React/TypeScript/Vite frontend, existing CSS.

---

### Task 1: Preserve Legacy Resonances And Tighten Positive Resonance Semantics

**Files:**
- Modify: `backend/tests/test_strategy_service.py`
- Modify: `backend/app/services/strategy_service.py`
- Modify: `backend/tests/test_indicators.py`
- Modify: `backend/app/services/analysis_service.py`

- [x] **Step 1: Write failing normalization tests**

Add tests in `backend/tests/test_strategy_service.py`:

```python
def test_normalize_keeps_unmatched_legacy_resonance_disabled_for_recovery():
    normalized = normalize_strategy_config(
        {
            "signal_mode": "feature_driven",
            "strategy_rules": [
                {"id": "theme-hot", "indicator_id": "topic_heat", "action": "score", "operator": "gte", "value": 70}
            ],
            "strategy_resonances": [
                {
                    "id": "legacy-unmatched",
                    "name": "旧题材放量",
                    "conditions": [
                        {"indicator_id": "topic_heat", "operator": "gte", "value": 70},
                        {"indicator_id": "volume_ratio", "operator": "gte", "value": 2},
                    ],
                    "multiplier": 1.2,
                    "enabled": True,
                }
            ],
        }
    )

    assert normalized["strategy_resonances"][0]["enabled"] is False
    assert normalized["strategy_resonances"][0]["source"] == "legacy_unmatched"
    assert normalized["strategy_resonances"][0]["legacy_conditions"][1]["indicator_id"] == "volume_ratio"
    assert "旧题材放量" in normalized["strategy_resonances"][0]["migration_warning"]
```

Also add a test that a resonance referencing a `risk` rule is kept disabled with a warning and no executable `rule_ids`.

- [x] **Step 2: Run targeted tests to verify failure**

Run: `python3 -m pytest backend/tests/test_strategy_service.py::test_normalize_keeps_unmatched_legacy_resonance_disabled_for_recovery -q`

Expected: FAIL because current normalization drops unmatched legacy resonances.

- [x] **Step 3: Implement resonance normalization changes**

Update `_normalize_strategy_resonances()` to:

- Accept only `filter` and `score` rule ids for executable positive resonance.
- Migrate matching legacy conditions to eligible rule ids.
- Preserve unmatched or ineligible legacy/user resonances as:

```python
{
    "id": resonance_id,
    "name": str(raw.get("name") or "组合共振"),
    "rule_ids": [],
    "bonus": round(bonus, 2),
    "enabled": False,
    "source": "legacy_unmatched",
    "migration_warning": f"组合共振「{name}」无法匹配至少两个筛选/加分规则，已停用；可恢复为补充规则后重新启用。",
    "legacy_conditions": conditions,
}
```

- [x] **Step 4: Write failing analysis tests for missing policy and risk resonance**

Add tests in `backend/tests/test_indicators.py` proving:

- A score rule on a missing field with `missing_policy="neutral"` does not add score.
- A risk rule on a missing field with `missing_policy="neutral"` does not deduct score.
- A resonance does not fire when one referenced score rule is missing.
- A filter rule with missing field and `missing_policy="neutral"` still keeps the candidate.
- A resonance referencing a risk rule does not add bonus.

- [x] **Step 5: Run targeted tests to verify failure**

Run the new tests with `python3 -m pytest backend/tests/test_indicators.py::<test_name> -q`.

Expected: FAIL because current row matching treats neutral missing values as matched for score/risk/resonance.

- [x] **Step 6: Implement action-aware missing behavior**

Add a `_value_missing()` helper and change `_strategy_rule_mask()` to accept `missing_matches=True`. Use `missing_matches=True` for DataFrame filtering, but use action-aware missing behavior in `_strategy_rule_matches_row()`:

- `filter`: missing can keep the row for `keep/allow/neutral`.
- `score` and `risk`: missing is not matched.
- `display`: handled by display helpers, not scoring.

Change `_matching_strategy_resonances()` so all referenced rules must exist and each rule action must be `filter` or `score`.

- [x] **Step 7: Add rule result missing fields**

Extend `_strategy_rule_results()` with `missing` and `reason` fields. Missing score/risk rows should return `matched=False`, `adjustment=0`, and reason `字段缺失，未加分` or `字段缺失，未扣风险`.

- [x] **Step 8: Run backend strategy tests**

Run: `python3 -m pytest backend/tests/test_strategy_service.py backend/tests/test_indicators.py -q`

Expected: PASS.

### Task 2: Repair Resonance Builder UX

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`

- [x] **Step 1: Update frontend types**

Extend `StrategyResonance` with:

```ts
source?: 'rule_ids' | 'legacy_unmatched' | string;
migration_warning?: string;
legacy_conditions?: StrategyRuleCondition[];
```

Extend `CandidateRuleResult` in `App.tsx` with `missing?: boolean` and `reason?: string | null`.

- [x] **Step 2: Implement resonance eligible rules**

Replace `activeRules` in `StrategyResonanceBuilder` with `resonanceEligibleRules`:

```ts
const resonanceEligibleRules = strategy.strategy_rules
  .filter((rule) => rule.enabled !== false)
  .filter((rule) => rule.action === 'filter' || rule.action === 'score')
  .filter((rule) => Boolean(indicatorById[rule.indicator_id]));
```

Use this list for all resonance select options and existing resonance cards.

- [x] **Step 3: Implement no-rules empty state**

When `resonanceEligibleRules.length < 2`, do not render draft selects. Render an empty state explaining that at least two filter/score rules are needed. If legacy resonances exist, mention that they can be recovered below.

- [x] **Step 4: Implement legacy resonance recovery UI**

In `StrategyResonanceCard`, detect `resonance.source === 'legacy_unmatched'`. Render disabled legacy card with old condition summaries and a `恢复为补充规则` button.

When clicked, create zero-weight score rules from `legacy_conditions`, append them to `strategy.strategy_rules`, and update the resonance to reference those created rules with `enabled=true`, `source='rule_ids'`.

- [x] **Step 5: Show missing rule result reasons**

In `CandidateScoreDetails`, render `item.reason` when present and show `缺失` state for rule results with `missing=true`.

- [x] **Step 6: Style resonance recovery and missing states**

Add CSS for legacy resonance warning/readout and rule-result missing state without adding nested cards or decorative noise.

- [x] **Step 7: Build frontend**

Run: `npm --prefix frontend run build`

Expected: PASS.

### Task 3: Add Candidate Display Scope And Event-State Choices

**Files:**
- Modify: `backend/tests/test_indicator_registry.py`
- Modify: `backend/app/services/indicator_registry.py`
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/App.tsx`

- [x] **Step 1: Write failing registry tests**

Add tests asserting:

- `limit_event.choice_options` contains `U/Z/D`.
- `limit_event.recommended_rules` contains 今日涨停, 今日炸板风险, 今日跌停风险.
- `macd_state` and `overheat_risk` are not candidate display scope.
- candidate-visible display indicators have `display_scope="candidate"`.

- [x] **Step 2: Run targeted registry tests**

Run: `python3 -m pytest backend/tests/test_indicator_registry.py -q`

Expected: FAIL for new fields.

- [x] **Step 3: Implement metadata**

Add `choice_options` and `display_scope` to `_rule_builder_meta()`, `RULE_META_BY_ID`, and `IndicatorDefinition`.

Set first pass scopes:

- `top_list_net_amount`, `top_inst_net_buy`, `hot_money_net_amount`, `cost_50pct`: `candidate`.
- `macd_state`, `overheat_risk`: `planned`.

- [x] **Step 4: Filter frontend display rule candidates**

Change rule builder `usableIndicators` so `display_only` indicators are shown only when `display_scope === 'candidate'`.

- [x] **Step 5: Render event-state values as select**

In `StrategyRuleCard`, if `indicator.operator_semantics === 'event_state'` and `choice_options` exist, render a select for `value` instead of a text/number input.

- [x] **Step 6: Run registry tests and frontend build**

Run: `python3 -m pytest backend/tests/test_indicator_registry.py -q`

Run: `npm --prefix frontend run build`

Expected: both PASS.

### Task 4: Finish Inactive Stock Coverage Follow-ups

**Files:**
- Modify: `backend/tests/test_daily_light_update.py`
- Modify: `backend/tests/test_market_environment.py`
- Modify: `backend/tests/test_data_warehouse.py`
- Modify: `backend/app/services/update_service.py`
- Modify: `backend/app/services/data_service.py`

- [x] **Step 1: Write failing update and market tests**

Add tests proving:

- `_history_stocks_for_update()` full mode excludes `suspended=True`.
- `_history_stocks_for_update()` daily-light mode excludes `suspended=True`.
- `_build_market_environment_row()` and `_market_turnover_score()` ignore suspended historical bars.

- [x] **Step 2: Write failing data warehouse tests**

Add tests proving:

- `list_stocks(search="000003")` falls back to inactive exact match when active results are empty.
- Every capability definition has explicit `coverage_kind`.

- [x] **Step 3: Run targeted tests to verify failure**

Run: `python3 -m pytest backend/tests/test_daily_light_update.py backend/tests/test_market_environment.py backend/tests/test_data_warehouse.py -q`

Expected: FAIL for new expectations.

- [x] **Step 4: Implement active-stock filters**

Update `_history_stocks_for_update()` full and light branches to use `b.suspended IS DISTINCT FROM TRUE`.

Update market environment SQL to join `stock_basic b` and exclude suspended rows for current-day breadth and 20-day turnover baseline.

- [x] **Step 5: Implement exact 6-digit fallback and explicit coverage kind**

Change `exact_code_search` to accept six digits with optional exchange suffix:

```py
re.fullmatch(r"\d{6}(\.(SH|SZ|BJ))?", text.upper())
```

If active exact search has no rows, rerun with `status="all"`.

Ensure each `CAPABILITY_DEFINITIONS` entry has a `coverage_kind`.

- [x] **Step 6: Run targeted tests**

Run: `python3 -m pytest backend/tests/test_daily_light_update.py backend/tests/test_market_environment.py backend/tests/test_data_warehouse.py -q`

Expected: PASS.

### Task 5: Full Verification, Commit, Push

**Files:**
- All touched files

- [x] **Step 1: Run full backend tests**

Run: `python3 -m pytest backend/tests -q`

Expected: PASS.

- [x] **Step 2: Run frontend build**

Run: `npm --prefix frontend run build`

Expected: PASS.

- [x] **Step 3: Inspect diff**

Run: `git status --short --branch`, `git diff --stat`, and `git diff --check`.

Expected: only planned files changed and whitespace check passes.

- [x] **Step 4: Commit and push**

Run:

```bash
git add docs/superpowers/plans/2026-05-27-strategy-rule-followup-fixes.md backend frontend
git commit -m "Fix strategy rule followups"
git push origin main
```

Expected: `main` and `origin/main` are synchronized.
