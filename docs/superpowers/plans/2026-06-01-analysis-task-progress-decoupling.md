# Analysis Task Progress Decoupling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix strategy analysis tasks that appear stuck at 4/7 and make task completion reliably refresh the corresponding results without a browser refresh.

**Architecture:** Treat `task_runs` as the task lifecycle snapshot and each result table as a separate result lifecycle. Frontend task views should subscribe to authoritative task queries by `task_id`, while result pages should refresh from task terminal events and explicit `run_id` references instead of stale `bootstrap` snapshots.

**Tech Stack:** FastAPI, DuckDB, pytest, React, TanStack Query, Node test runner.

## Current Implementation Status

- Completed in branch `codex/analysis-task-progress-decoupling`: backend analysis tasks now pre-assign and return `run_id`, bind `analysis_runs.task_id`, publish authoritative completion summaries, support older test runners through signature-aware invocation, and emit throttled step-4 heartbeats.
- Completed in branch `codex/analysis-task-progress-decoupling`: frontend task/result polling now invalidates result queries on terminal task events, avoids reviving stale `bootstrap` active tasks, and lets the results page follow the newest completed run unless the user explicitly selects history.
- Added regression coverage for the stuck-at-4/7 progress heartbeat, queued analysis completion/result publishing, `run_id` API contract, stale active task fallback, terminal invalidation, result auto-following, and snake/camel response ids.
- Deferred to a follow-up phase: broader AI decoupling for synchronous evidence/explanation POST flows and deeper page-specific refresh extraction into a shared hook. The current fix removes the refresh-required failure path without changing those wider workflows.

---

## Evidence Summary

- Code fact: analysis step 4/7 is `计算技术形态` in `backend/app/services/analysis_service.py`; the expensive per-stock loop runs after this progress event and before step 5.
- Code fact: `StatusPage` can fall back to `bootstrap.*_status` when the active task query returns no rows, which can resurrect a stale running snapshot.
- Code fact: `ResultsPage` only auto-selects `latestRunId` when `selectedRunId` is empty, so an old selected report can hide a newly completed run until refresh.
- Code fact: `task_runs`, `analysis_runs`, `candidate_results`, and `funnel_stats` are separate tables with no hard task/result relationship in the schema.
- Server verification needed: production logs/database may differ from local sample data. Use the commands in Task 7 on the deployed server to confirm whether running `analysis_runs` or stale `task_runs` exist.

## File Structure

- Modify: `backend/app/services/analysis_service.py`
  - Add optional `run_id` and `task_id` support to `AnalysisService.run()`.
  - Add throttled heartbeat text inside the step-4 per-stock loop.
- Modify: `backend/app/services/update_service.py`
  - Pre-generate analysis `run_id`, enqueue it with the task, return it from `start_analysis()`.
  - Finalize task summaries from authoritative result data instead of `limit=1`.
  - Recover stale analysis runs after service restart.
- Modify: `backend/app/schema.py`
  - Add `task_id` to `analysis_runs`.
- Modify: `backend/app/api/routes.py`
  - Return `run_id` from `POST /api/tasks/analyze`.
- Modify: `backend/app/services/data_service.py`
  - Prefer `finished_at` and completed statuses for latest completed result queries where appropriate.
- Modify: `frontend/src/api/strategy.ts`
  - Include optional `run_id` / `runId` in `AnalysisTaskJob`.
- Modify: `frontend/src/pages/status/StatusPage.tsx`
  - Stop showing stale `bootstrap` active fallback after active query succeeds empty.
  - Invalidate result queries once when tasks become terminal.
- Modify: `frontend/src/pages/results/ResultsPage.tsx`
  - Auto-follow newest run unless the user manually selected a historical report.
  - Avoid mixing stale selected report detail with latest bootstrap candidates.
- Modify: `frontend/src/app/AppShell.tsx`
  - Include task/result keys in active-task polling or delegate to a shared completion invalidation hook.
- Modify: `frontend/src/pages/backtest/SignalEvaluation.tsx`
- Modify: `frontend/src/pages/backtest/PortfolioBacktest.tsx`
- Modify: `frontend/src/pages/backtest/BacktestPage.tsx`
- Modify: `frontend/src/pages/intraday/IntradayPage.tsx`
  - Apply the same terminal-event refresh pattern to backtest and intraday results.
- Modify: `frontend/src/pages/results/CandidateEvidencePanel.tsx`
  - Defer full AI decoupling to a second phase, but document the current synchronous POST-in-query risk.
- Test: `backend/tests/test_analysis_progress.py`
- Test: `backend/tests/test_quant_workbench_upgrade.py`
- Test: `frontend/tests/analyze-completion-polling-structure.test.mjs`
- Test: existing `frontend/tests/workbench-upgrade-structure.test.mjs`

---

### Task 1: Backend Regression For Analysis Completion

**Files:**
- Modify: `backend/tests/test_analysis_progress.py`

- [ ] **Step 1: Add imports for deterministic result rows**

Add `from datetime import datetime` near the top:

```python
from datetime import datetime
```

- [ ] **Step 2: Write the failing completion/result consistency test**

Append this test to `backend/tests/test_analysis_progress.py`:

```python
def test_analysis_task_completion_publishes_result_for_polling(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = UpdateService(db)
    task_id = "analyze-completion"
    run_id = "analysis-completion"
    service._write_task(
        task_id,
        kind="analyze",
        status="running",
        stage="准备分析",
        source="本地仓库",
        current_stock=None,
        total=0,
        processed=0,
        success=0,
        failed=0,
        skipped=0,
        warning=None,
        summary={},
        error_message=None,
    )

    class Runner:
        def run(self, config, progress, **_kwargs):
            progress("计算技术形态", 4, 7)
            now = datetime.utcnow()
            db.upsert(
                "analysis_runs",
                [
                    {
                        "id": run_id,
                        "status": "completed_full",
                        "started_at": now,
                        "finished_at": now,
                        "config_json": json.dumps(config, ensure_ascii=False),
                        "summary_json": json.dumps(
                            {"candidate_count": 2, "zero_reason": None, "strategy_name": "完成测试"},
                            ensure_ascii=False,
                        ),
                        "error_message": None,
                    }
                ],
                ["id"],
            )
            db.upsert(
                "candidate_results",
                [
                    {
                        "run_id": run_id,
                        "rank": 1,
                        "code": "000001.SZ",
                        "name": "平安银行",
                        "signal_score": 88.0,
                        "data_sources": "{}",
                        "reasons_json": "[]",
                        "metrics_json": "{}",
                        "created_at": now,
                    },
                    {
                        "run_id": run_id,
                        "rank": 2,
                        "code": "000002.SZ",
                        "name": "万科A",
                        "signal_score": 80.0,
                        "data_sources": "{}",
                        "reasons_json": "[]",
                        "metrics_json": "{}",
                        "created_at": now,
                    },
                ],
                ["run_id", "code"],
            )
            return run_id

    service._run_analysis(task_id, {**DEFAULT_STRATEGY_CONFIG, "strategy_name": "完成测试"}, Runner())

    task = DataService(db).latest_task("analyze")
    report = DataService(db).analysis_report(run_id)
    assert task["status"] == "completed_full"
    assert task["stage"] == "分析完成"
    assert task["processed"] == 7
    assert task["total"] == 7
    assert task["summary"]["analysis_run_id"] == run_id
    assert task["summary"]["candidate_count"] == 2
    assert report["analysis"]["status"] == "completed_full"
    assert len(report["candidates"]["rows"]) == 2
```

- [ ] **Step 3: Run the new test and confirm it fails for the right reason**

Run:

```bash
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 pytest -p no:cacheprovider backend/tests/test_analysis_progress.py::test_analysis_task_completion_publishes_result_for_polling -q
```

Expected before implementation: FAIL because `task["summary"]["candidate_count"]` is `1`, proving `_run_analysis()` currently counts only `limit=1`.

---

### Task 2: Make Analysis Task Finalization Authoritative

**Files:**
- Modify: `backend/app/services/update_service.py`
- Modify: `backend/tests/test_analysis_progress.py`

- [ ] **Step 1: Fix candidate count in `_run_analysis()`**

Replace the finalization count logic in `backend/app/services/update_service.py`:

```python
candidates = self.data_service.candidates(run_id, limit=1)
```

with:

```python
candidates = self.data_service.candidates(run_id, limit=1)
candidate_count = int(
    self.db.scalar("SELECT COUNT(*) FROM candidate_results WHERE run_id = ?", [run_id])
    or 0
)
```

Then replace:

```python
"candidate_count": len(candidates.get("rows", [])),
```

with:

```python
"candidate_count": candidate_count,
```

- [ ] **Step 2: Run the focused backend test**

Run:

```bash
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 pytest -p no:cacheprovider backend/tests/test_analysis_progress.py::test_analysis_task_completion_publishes_result_for_polling -q
```

Expected: PASS.

- [ ] **Step 3: Run the existing analysis progress suite**

Run:

```bash
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 pytest -p no:cacheprovider backend/tests/test_analysis_progress.py -q
```

Expected: all tests pass.

---

### Task 3: Add Analysis Run Identity To The Task Contract

**Files:**
- Modify: `backend/app/schema.py`
- Modify: `backend/app/services/analysis_service.py`
- Modify: `backend/app/services/update_service.py`
- Modify: `backend/app/api/routes.py`
- Modify: `frontend/src/api/strategy.ts`
- Modify: `backend/tests/test_analysis_progress.py`
- Modify: `backend/tests/test_quant_workbench_upgrade.py`

- [ ] **Step 1: Add schema migration for `analysis_runs.task_id`**

In `backend/app/schema.py`, after the `analysis_runs` table creation block, add:

```python
"""
ALTER TABLE analysis_runs ADD COLUMN IF NOT EXISTS task_id TEXT
""",
```

- [ ] **Step 2: Let `AnalysisService.run()` accept externally assigned ids**

Change the function signature in `backend/app/services/analysis_service.py`:

```python
def run(self, config: Dict[str, Any], progress: Optional[AnalysisProgress] = None) -> str:
    run_id = f"analysis-{uuid.uuid4().hex[:12]}"
```

to:

```python
def run(
    self,
    config: Dict[str, Any],
    progress: Optional[AnalysisProgress] = None,
    run_id: Optional[str] = None,
    task_id: Optional[str] = None,
) -> str:
    run_id = run_id or f"analysis-{uuid.uuid4().hex[:12]}"
```

Include `"task_id": task_id` in both `analysis_runs` upserts inside this method.

- [ ] **Step 3: Pre-generate `run_id` in `UpdateService.start_analysis()`**

Change `start_analysis()` to return a tuple and enqueue `run_id`:

```python
def start_analysis(self, config: Dict[str, Any], analysis_runner: Any) -> tuple[str, str]:
    self.analysis_runner = analysis_runner
    frozen_config = json.loads(json.dumps(config, ensure_ascii=False))
    task_id = f"analyze-{uuid.uuid4().hex[:12]}"
    run_id = f"analysis-{uuid.uuid4().hex[:12]}"
    self._enqueue_task(
        task_id,
        kind="analyze",
        stage="准备分析",
        source="本地仓库",
        summary={"analysis_run_id": run_id},
        payload={"config": frozen_config, "run_id": run_id},
    )
    return task_id, run_id
```

- [ ] **Step 4: Pass `run_id` and `task_id` through dispatch**

Change the analyze dispatch path:

```python
self._run_analysis(task_id, payload.get("config") or {}, self.analysis_runner)
```

to:

```python
self._run_analysis(task_id, payload.get("config") or {}, self.analysis_runner, run_id=payload.get("run_id"))
```

Change `_run_analysis()` signature:

```python
def _run_analysis(self, task_id: str, config: Dict[str, Any], analysis_runner: Any, run_id: Optional[str] = None) -> None:
```

Then call:

```python
run_id = analysis_runner.run(config, progress=progress, run_id=run_id, task_id=task_id)
```

- [ ] **Step 5: Return `run_id` from the API**

In `backend/app/api/routes.py`, change:

```python
task_id = update_service.start_analysis(config, analysis_service)
```

to:

```python
task_id, run_id = update_service.start_analysis(config, analysis_service)
```

and return:

```python
return {"task_id": task_id, "run_id": run_id, "status": "queued"}
```

- [ ] **Step 6: Update frontend job type**

In `frontend/src/api/strategy.ts`, change `AnalysisTaskJob` to:

```typescript
export type AnalysisTaskJob = {
  task_id: string;
  run_id?: string;
  taskId?: string;
  runId?: string;
  status: string;
};
```

- [ ] **Step 7: Update affected tests**

In tests that monkeypatch `start_analysis`, return both ids:

```python
monkeypatch.setattr(routes.update_service, "start_analysis", lambda config, runner: ("analyze-test", "analysis-test"))
```

Expected route response:

```python
{"task_id": "analyze-test", "run_id": "analysis-test", "status": "queued"}
```

- [ ] **Step 8: Run route and progress tests**

Run:

```bash
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 pytest -p no:cacheprovider backend/tests/test_analysis_progress.py backend/tests/test_quant_workbench_upgrade.py -q
```

Expected: all tests pass.

---

### Task 4: Add Step-4 Heartbeat Without Inflating Progress

**Files:**
- Modify: `backend/app/services/analysis_service.py`
- Modify: `backend/tests/test_analysis_progress.py`

- [ ] **Step 1: Add throttled stage updates in the per-stock loop**

In `_build_analysis_frame()`, replace:

```python
output = []
analysis_engines = set(strategy.get("analysis_engines") or [])
for code, group in bars.groupby("code"):
```

with:

```python
output = []
analysis_engines = set(strategy.get("analysis_engines") or [])
stock_count = int(bars["code"].nunique()) if "code" in bars else 0
for index, (code, group) in enumerate(bars.groupby("code"), start=1):
    if progress and (index == 1 or index % 250 == 0 or index == stock_count):
        _emit_analysis_progress(progress, f"计算技术形态 {index}/{stock_count}", 4)
```

- [ ] **Step 2: Add a test that proves step 4 emits heartbeats**

In `backend/tests/test_analysis_progress.py`, update `test_analysis_service_reports_fine_grained_progress` to assert at least one `计算技术形态` event:

```python
assert any(stage.startswith("计算技术形态") for stage, _, _ in events)
```

- [ ] **Step 3: Run the analysis progress tests**

Run:

```bash
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 pytest -p no:cacheprovider backend/tests/test_analysis_progress.py -q
```

Expected: all tests pass and progress still ends at `7/7`.

---

### Task 5: Fix Frontend Stale Active Task And Result Refresh

**Files:**
- Modify: `frontend/src/pages/status/StatusPage.tsx`
- Modify: `frontend/src/app/AppShell.tsx`
- Create: `frontend/tests/analyze-completion-polling-structure.test.mjs`

- [ ] **Step 1: Stop using stale bootstrap fallback after active query succeeds**

In `StatusPage.tsx`, replace:

```typescript
const effectiveActiveRows = activeRows.length ? activeRows : fallbackTasks.filter((task) => ['queued', 'running'].includes(task.status));
```

with:

```typescript
const bootstrapActiveRows = fallbackTasks.filter((task) => ['queued', 'running'].includes(task.status));
const effectiveActiveRows = activeTasks.isSuccess ? activeRows : activeRows.length ? activeRows : bootstrapActiveRows;
```

- [ ] **Step 2: Add one-shot terminal invalidation**

Import `useEffect`, `useRef`, and `useQueryClient` in `StatusPage.tsx`:

```typescript
import { useEffect, useMemo, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
```

Add after `recentRows` is computed:

```typescript
const queryClient = useQueryClient();
const seenTerminalTaskIds = useRef(new Set<string>());

useEffect(() => {
  for (const task of recentRows) {
    if (!task.id || seenTerminalTaskIds.current.has(task.id)) continue;
    seenTerminalTaskIds.current.add(task.id);
    void queryClient.invalidateQueries({ queryKey: ['bootstrap'] });
    void queryClient.invalidateQueries({ queryKey: ['tasks'] });
    if (task.kind === 'analyze') {
      void queryClient.invalidateQueries({ queryKey: ['result-reports'] });
      const runId = String(task.summary?.analysis_run_id || '');
      if (runId) void queryClient.invalidateQueries({ queryKey: ['result-report', runId] });
    }
    if (task.kind === 'backtest') {
      void queryClient.invalidateQueries({ queryKey: ['backtest-runs'] });
      const runId = String(task.summary?.backtest_run_id || '');
      if (runId) {
        void queryClient.invalidateQueries({ queryKey: ['signal-evaluation', runId] });
        void queryClient.invalidateQueries({ queryKey: ['portfolio-backtest', runId] });
      }
    }
    if (task.kind === 'intraday') {
      void queryClient.invalidateQueries({ queryKey: ['intraday-boards'] });
    }
  }
}, [queryClient, recentRows]);
```

- [ ] **Step 3: Broaden active polling keys in `AppShell`**

Change:

```typescript
usePolling(taskActive, [['bootstrap'], ['runtime-health'], ['market-overview']], 2600);
```

to:

```typescript
usePolling(taskActive, [['bootstrap'], ['runtime-health'], ['market-overview'], ['tasks'], ['result-reports'], ['backtest-runs'], ['intraday-boards']], 2600);
```

- [ ] **Step 4: Add structure test for stale fallback prevention**

Create `frontend/tests/analyze-completion-polling-structure.test.mjs`:

```javascript
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { resolve } from 'node:path';

const src = (path) => readFileSync(resolve('src', path), 'utf8');

test('status page does not revive stale bootstrap active tasks after live query succeeds', () => {
  const status = src('pages/status/StatusPage.tsx');
  assert.match(status, /bootstrapActiveRows/);
  assert.match(status, /activeTasks\.isSuccess\s*\?\s*activeRows/);
  assert.doesNotMatch(status, /activeRows\.length\s*\?\s*activeRows\s*:\s*fallbackTasks\.filter/);
});

test('terminal task completion invalidates matching result queries', () => {
  const status = src('pages/status/StatusPage.tsx');
  for (const key of ['result-reports', 'result-report', 'backtest-runs', 'signal-evaluation', 'portfolio-backtest', 'intraday-boards']) {
    assert.match(status, new RegExp(key));
  }
  assert.match(status, /seenTerminalTaskIds/);
});

test('app shell polls task and result keys while work is active', () => {
  const shell = src('app/AppShell.tsx');
  for (const key of ['tasks', 'result-reports', 'backtest-runs', 'intraday-boards']) {
    assert.match(shell, new RegExp(key));
  }
});
```

- [ ] **Step 5: Run frontend tests**

Run:

```bash
npm --prefix frontend test
```

Expected: all tests pass.

---

### Task 6: Make Results Page Follow New Runs Safely

**Files:**
- Modify: `frontend/src/pages/results/ResultsPage.tsx`
- Modify: `frontend/tests/analyze-completion-polling-structure.test.mjs`

- [ ] **Step 1: Track manual report selection**

Add state near `selectedRunId`:

```typescript
const [manualRunSelection, setManualRunSelection] = useState(false);
```

Replace the `onChange` handler:

```typescript
onChange={(value) => value !== 'none' && setSelectedRunId(value)}
```

with:

```typescript
onChange={(value) => {
  if (value === 'none') return;
  setManualRunSelection(true);
  setSelectedRunId(value);
}}
```

- [ ] **Step 2: Auto-follow latest run unless user selected history**

Replace:

```typescript
useEffect(() => {
  if (!selectedRunId && latestRunId) setSelectedRunId(latestRunId);
}, [latestRunId, selectedRunId]);
```

with:

```typescript
useEffect(() => {
  if (!latestRunId || manualRunSelection) return;
  setSelectedRunId(latestRunId);
}, [latestRunId, manualRunSelection]);
```

- [ ] **Step 3: Avoid mixing stale selected detail with latest bootstrap candidates**

Replace:

```typescript
const activeCandidates = reportDetail.data?.candidates?.rows || bootstrap.data?.candidates?.rows || [];
const activeReport = reportDetail.data?.analysis || bootstrap.data?.latest_analysis || flattenedReports.find((report) => report.id === selectedRunId) || null;
```

with:

```typescript
const selectedIsLatest = Boolean(selectedRunId && selectedRunId === latestRunId);
const activeCandidates = reportDetail.data?.candidates?.rows || (selectedIsLatest ? bootstrap.data?.candidates?.rows : []) || [];
const activeReport = reportDetail.data?.analysis || (selectedIsLatest ? bootstrap.data?.latest_analysis : null) || flattenedReports.find((report) => report.id === selectedRunId) || null;
```

- [ ] **Step 4: Extend frontend structure test**

Append to `frontend/tests/analyze-completion-polling-structure.test.mjs`:

```javascript
test('results page follows latest run unless historical report is manually selected', () => {
  const results = src('pages/results/ResultsPage.tsx');
  assert.match(results, /manualRunSelection/);
  assert.match(results, /setManualRunSelection\(true\)/);
  assert.match(results, /selectedIsLatest/);
  assert.doesNotMatch(results, /if \(!selectedRunId && latestRunId\)/);
});
```

- [ ] **Step 5: Run frontend tests and build**

Run:

```bash
npm --prefix frontend test
npm --prefix frontend run build
```

Expected: tests and TypeScript build pass.

---

### Task 7: Server-Side Verification Commands

**Files:**
- No code changes.

- [ ] **Step 1: Check task and result consistency on the deployed server**

Run on the server from the project root, adjusting the database path if production uses `ASHARE_DB_PATH`:

```bash
python3 - <<'PY'
import duckdb, json, os
path = os.getenv("ASHARE_DB_PATH", "data/ashare_signal.duckdb")
conn = duckdb.connect(path, read_only=True)
print("--- recent analyze task_runs ---")
for row in conn.execute("""
SELECT id, status, stage, processed, total, updated_at, finished_at, summary_json, error_message
FROM task_runs
WHERE kind = 'analyze'
ORDER BY started_at DESC
LIMIT 10
""").fetchall():
    print(row)
print("--- running analysis_runs ---")
for row in conn.execute("""
SELECT id, status, started_at, finished_at, error_message
FROM analysis_runs
WHERE status = 'running'
ORDER BY started_at DESC
""").fetchall():
    print(row)
conn.close()
PY
```

Expected after fixes: no old `analysis_runs.status='running'` without an active task; recent analyze tasks finish as `completed_full / 7 / 7`.

- [ ] **Step 2: Observe live task transition through HTTP**

While running a strategy in the web UI, run:

```bash
watch -n 1 'curl -s http://127.0.0.1:8000/api/status/analyze | python3 -m json.tool'
```

Expected: stage may stay in a `计算技术形态 250/5211` style stage while the long loop runs, but `updated_at` should keep moving. At completion it must become `completed_full`, `processed: 7`, `total: 7`, with `summary.analysis_run_id`.

- [ ] **Step 3: Confirm result endpoint is ready without browser refresh**

Read the newest completed `analysis_run_id` and query its report:

```bash
RUN_ID=$(python3 - <<'PY'
import duckdb, json, os
path = os.getenv("ASHARE_DB_PATH", "data/ashare_signal.duckdb")
conn = duckdb.connect(path, read_only=True)
row = conn.execute("""
SELECT summary_json
FROM task_runs
WHERE kind = 'analyze' AND status LIKE 'completed%'
ORDER BY finished_at DESC NULLS LAST, started_at DESC
LIMIT 1
""").fetchone()
conn.close()
summary = json.loads(row[0] or "{}") if row else {}
print(summary.get("analysis_run_id", ""))
PY
)
curl -s "http://127.0.0.1:8000/api/analysis/reports/${RUN_ID}?limit=5" | python3 -m json.tool
```

Expected: response contains `analysis.status: completed_full` and `candidates.rows`.

---

### Task 8: Phase 2 AI And Task System Decoupling

**Files:**
- Modify in Phase 2: `backend/app/schema.py`
- Modify in Phase 2: `backend/app/services/update_service.py`
- Modify in Phase 2: `backend/app/services/candidate_summary_service.py`
- Modify in Phase 2: `frontend/src/pages/results/CandidateEvidencePanel.tsx`

- [ ] **Step 1: Add a common task event table**

Add schema:

```sql
CREATE TABLE IF NOT EXISTS task_events (
    id TEXT PRIMARY KEY,
    task_id TEXT,
    seq INTEGER,
    status TEXT,
    stage TEXT,
    processed INTEGER,
    total INTEGER,
    result_kind TEXT,
    result_id TEXT,
    payload_json TEXT,
    created_at TIMESTAMP
)
```

- [ ] **Step 2: Centralize task writes**

Move task snapshot and event writes behind one backend helper:

```python
def publish_task_event(
    self,
    task_id: str,
    *,
    status: str,
    stage: str,
    processed: int,
    total: int,
    result_kind: Optional[str] = None,
    result_id: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> None:
    now = datetime.utcnow()
    seq = int(
        self.db.scalar("SELECT COALESCE(MAX(seq), 0) + 1 FROM task_events WHERE task_id = ?", [task_id])
        or 1
    )
    event = {
        "id": f"{task_id}:{seq}",
        "task_id": task_id,
        "seq": seq,
        "status": status,
        "stage": stage,
        "processed": processed,
        "total": total,
        "result_kind": result_kind,
        "result_id": result_id,
        "payload_json": json.dumps(payload or {}, ensure_ascii=False),
        "created_at": now,
    }
    self.db.upsert("task_events", [event], ["id"])
    summary = {"result_kind": result_kind, "result_id": result_id} if result_id else None
    self._patch_task(
        task_id,
        status=status,
        stage=stage,
        processed=processed,
        total=total,
        summary=summary,
    )
```

Use it from analyze, backtest, intraday, update, brief, and AI summary tasks.

- [ ] **Step 3: Convert candidate AI summaries to independent jobs**

Replace render-triggered `POST /api/analysis/candidates/{run_id}/{code}/ai-summary` with:

```http
POST /api/tasks/candidate-ai-summary
GET /api/analysis/candidates/{run_id}/{code}/ai-summary
```

The cache key must be:

```text
run_id + code + input_hash + prompt_version
```

UI behavior:

```text
ready -> show AI summary
queued/running -> show deterministic rule explanation plus AI status badge
failed -> show deterministic rule explanation plus retry action
missing_api_key -> show deterministic rule explanation only
```

- [ ] **Step 4: Add event-based frontend hook**

Create a frontend hook that maps terminal events to invalidation keys:

```typescript
const resultInvalidationByKind = {
  analyze: ['result-reports'],
  backtest: ['backtest-runs'],
  intraday: ['intraday-boards'],
  brief: ['bootstrap'],
};
```

This replaces page-specific guesses and prevents future task/result refresh drift.

---

## Final Verification

Run:

```bash
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 pytest -p no:cacheprovider backend/tests/test_analysis_progress.py backend/tests/test_analysis_reports.py backend/tests/test_quant_workbench_upgrade.py -q
npm --prefix frontend test
npm --prefix frontend run build
```

Expected:

```text
backend tests pass
frontend node tests pass
frontend TypeScript/Vite build pass
```

Manual acceptance:

```text
1. Start a strategy run.
2. Status page shows step 4 heartbeat instead of a frozen timestamp.
3. When the task finishes, status changes to completed_full 7/7 without refresh.
4. Navigate to analysis results without refresh.
5. The latest report and candidates are visible.
6. Re-run from the results page and repeat the same checks.
```
