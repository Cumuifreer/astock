# Candidate AI Summary Decoupling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decouple candidate AI explanation generation from result-page reads so opening or refreshing analysis results never synchronously triggers an LLM request.

**Architecture:** Keep `task_runs` as the task lifecycle table and upgrade `candidate_ai_summaries` into the result lifecycle table for AI summaries. `GET` reads cached/status data only; `POST /api/tasks/candidate-ai-summary` idempotently starts or reuses a generation task. The frontend displays rule evidence immediately and treats AI text as an optional asynchronous enhancement.

**Tech Stack:** FastAPI, DuckDB, pytest, React, TanStack Query, Node test runner.

---

## Evidence Summary

- `frontend/src/pages/results/CandidateEvidencePanel.tsx` currently uses `useQuery()` to call `getCandidateAiSummary()`.
- `frontend/src/api/strategy.ts` names that function like a read, but it performs a `POST` to `/api/analysis/candidates/{run_id}/{code}/ai-summary`.
- `backend/app/api/routes.py` routes that POST directly to `CandidateSummaryService.summarize()`.
- `CandidateSummaryService.summarize()` reads cache and, on miss, synchronously calls the LLM with an 80 second timeout.
- `candidate_ai_summaries` currently stores only successful summaries by `(run_id, code)` and does not track status, task id, input hash, failure reason, or retry boundary.
- `StatusPage` terminal invalidation is page-local; it should become shared/app-level before more task kinds are added.

## File Structure

- Modify: `backend/app/schema.py`
  - Add status/result lifecycle columns to `candidate_ai_summaries`.
- Modify: `backend/app/services/candidate_summary_service.py`
  - Split read/status, evidence building, hash generation, and generation/persistence.
- Modify: `backend/app/services/update_service.py`
  - Add idempotent enqueue and dispatch for `kind="candidate_ai_summary"`.
- Modify: `backend/app/services/data_service.py`
  - Add read-only helper for candidate AI summary status/result.
- Modify: `backend/app/api/routes.py`
  - Add pure GET result endpoint and task POST endpoint; keep the old sync POST only as a compatibility shim or deprecate it after frontend migration.
- Modify: `frontend/src/api/queryKeys.ts`
  - Add central query key registry.
- Modify: `frontend/src/api/strategy.ts`
  - Split read-only `getCandidateAiSummary()` from `startCandidateAiSummary()`.
- Modify: `frontend/src/pages/results/CandidateEvidencePanel.tsx`
  - Replace POST-in-query with GET status query and explicit generate/retry mutation.
- Modify: `frontend/src/hooks/useTaskTerminalInvalidation.ts`
  - Move terminal invalidation out of `StatusPage`.
- Modify: `frontend/src/hooks/useActiveTaskPolling.ts`
  - Move active-task polling key selection out of `AppShell`.
- Modify: `frontend/src/hooks/useTaskResultQuery.ts`
  - Deduplicate queued/running polling for backtest-style task result views.
- Modify: `frontend/src/pages/status/StatusPage.tsx`
  - Use shared terminal invalidation hook while preserving stale-bootstrap guard.
- Modify: `frontend/src/app/AppShell.tsx`
  - Use shared active polling and app-level terminal invalidation.
- Modify: `frontend/src/pages/backtest/SignalEvaluation.tsx`
- Modify: `frontend/src/pages/backtest/PortfolioBacktest.tsx`
  - Use shared result polling hook.
- Test: `backend/tests/test_candidate_summary_service.py`
- Test: `backend/tests/test_analysis_progress.py`
- Test: `backend/tests/test_quant_workbench_upgrade.py`
- Test: `frontend/tests/analyze-completion-polling-structure.test.mjs`
- Test: `frontend/tests/ai-summary-decoupling-structure.test.mjs`

---

### Task 1: Backend AI Summary Result Lifecycle

**Files:**
- Modify: `backend/app/schema.py`
- Modify: `backend/app/services/candidate_summary_service.py`
- Test: `backend/tests/test_candidate_summary_service.py`

- [ ] **Step 1: Write tests for cache identity and fallback persistence**

Add tests proving:

```python
def test_candidate_summary_status_uses_input_hash_and_prompt_version(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = CandidateSummaryService(db, api_key="configured", model="model-a")

    first = service.prepare_summary_identity(
        run_id="run-1",
        code="000001.SZ",
        candidate={"code": "000001.SZ", "name": "平安银行", "reasons": ["RPS 强"], "metrics": {"volume_ratio": 1.8}},
        matched_rules=[{"indicator_id": "rps20", "matched": True}],
        risk_items=[],
    )
    second = service.prepare_summary_identity(
        run_id="run-1",
        code="000001.SZ",
        candidate={"code": "000001.SZ", "name": "平安银行", "reasons": ["RPS 强"], "metrics": {"volume_ratio": 2.2}},
        matched_rules=[{"indicator_id": "rps20", "matched": True}],
        risk_items=[],
    )

    assert first["input_hash"] != second["input_hash"]
    assert first["prompt_version"]
```

```python
def test_candidate_summary_persists_fallback_result(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = CandidateSummaryService(db, api_key="")

    identity = service.prepare_summary_identity(
        run_id="run-1",
        code="000001.SZ",
        candidate={"code": "000001.SZ", "name": "平安银行", "reasons": ["量能确认"], "metrics": {}},
        matched_rules=[],
        risk_items=[],
    )
    result = service.generate_and_store(identity, task_id="ai-summary-test")
    cached = service.read_summary("run-1", "000001.SZ", input_hash=identity["input_hash"])

    assert result["status"] == "completed_partial"
    assert result["summary"]["fallback_reason"] == "missing_api_key"
    assert cached["status"] == "completed_partial"
    assert cached["task_id"] == "ai-summary-test"
```

- [ ] **Step 2: Run tests and confirm they fail**

Run:

```bash
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 pytest -p no:cacheprovider backend/tests/test_candidate_summary_service.py -q
```

Expected before implementation: FAIL because `prepare_summary_identity`, `generate_and_store`, and persisted fallback status do not exist.

- [ ] **Step 3: Add schema columns**

Add migrations after the existing `candidate_ai_summaries` table:

```python
"""
ALTER TABLE candidate_ai_summaries ADD COLUMN IF NOT EXISTS status TEXT
""",
"""
ALTER TABLE candidate_ai_summaries ADD COLUMN IF NOT EXISTS task_id TEXT
""",
"""
ALTER TABLE candidate_ai_summaries ADD COLUMN IF NOT EXISTS input_hash TEXT
""",
"""
ALTER TABLE candidate_ai_summaries ADD COLUMN IF NOT EXISTS prompt_version TEXT
""",
"""
ALTER TABLE candidate_ai_summaries ADD COLUMN IF NOT EXISTS evidence_json TEXT
""",
"""
ALTER TABLE candidate_ai_summaries ADD COLUMN IF NOT EXISTS fallback_reason TEXT
""",
"""
ALTER TABLE candidate_ai_summaries ADD COLUMN IF NOT EXISTS error_message TEXT
""",
"""
ALTER TABLE candidate_ai_summaries ADD COLUMN IF NOT EXISTS requested_at TIMESTAMP
""",
"""
ALTER TABLE candidate_ai_summaries ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP
""",
```

- [ ] **Step 4: Split service methods**

Add these methods to `CandidateSummaryService`:

```python
def prepare_summary_identity(
    self,
    run_id: str,
    code: str,
    candidate: Dict[str, Any],
    matched_rules: Optional[List[Dict[str, Any]]] = None,
    risk_items: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    evidence = {
        "candidate": _compact_candidate(candidate),
        "matched_rules": (matched_rules or [])[:8],
        "risk_items": (risk_items or [])[:8],
        "prompt_version": PROMPT_VERSION,
        "llm_model": self.model,
    }
    input_hash = _stable_hash(evidence)
    return {
        "run_id": run_id,
        "code": code,
        "candidate": evidence["candidate"],
        "matched_rules": evidence["matched_rules"],
        "risk_items": evidence["risk_items"],
        "prompt_version": PROMPT_VERSION,
        "llm_model": self.model,
        "input_hash": input_hash,
        "evidence": evidence,
    }
```

```python
def read_summary(self, run_id: str, code: str, input_hash: Optional[str] = None) -> Dict[str, Any]:
    rows = self.db.query(
        """
        SELECT *
        FROM candidate_ai_summaries
        WHERE run_id = ? AND code = ?
        ORDER BY updated_at DESC NULLS LAST, generated_at DESC NULLS LAST
        LIMIT 1
        """,
        [run_id, code],
    )
    if not rows:
        return {"status": "not_requested", "run_id": run_id, "code": code, "summary": None}
    row = rows[0]
    status = row.get("status") or "completed_full"
    if input_hash and row.get("input_hash") and row.get("input_hash") != input_hash:
        status = "stale"
    return {
        "status": status,
        "task_id": row.get("task_id"),
        "run_id": run_id,
        "code": code,
        "input_hash": row.get("input_hash"),
        "prompt_version": row.get("prompt_version"),
        "llm_model": row.get("llm_model"),
        "fallback_reason": row.get("fallback_reason"),
        "error_message": row.get("error_message"),
        "summary": _loads_json(row.get("summary_json")),
        "generated_at": row.get("generated_at"),
        "updated_at": row.get("updated_at"),
    }
```

```python
def generate_and_store(self, identity: Dict[str, Any], task_id: Optional[str] = None) -> Dict[str, Any]:
    generated_at = datetime.utcnow().isoformat(timespec="seconds")
    candidate = identity["candidate"]
    matched = identity["matched_rules"]
    risks = identity["risk_items"]
    if not self.api_key:
        summary = _fallback_result(candidate, matched, risks, generated_at, "missing_api_key")
        status = "completed_partial"
    else:
        try:
            result = self._call_llm(candidate, matched, risks)
            summary = _normalize_llm_result(result, candidate, matched, risks, generated_at)
            status = "completed_full"
        except ValueError as exc:
            summary = _fallback_result(candidate, matched, risks, generated_at, "invalid_response", str(exc))
            status = "completed_partial"
        except Exception as exc:
            summary = _fallback_result(candidate, matched, risks, generated_at, "llm_error", str(exc))
            status = "completed_partial"
    self.persist_summary(identity, summary, status=status, task_id=task_id)
    return self.read_summary(identity["run_id"], identity["code"], input_hash=identity["input_hash"])
```

- [ ] **Step 5: Keep `summarize()` backward-compatible**

Change `summarize()` to call `prepare_summary_identity()`, `read_summary()`, and `generate_and_store()` so old tests and any old clients still work during the frontend migration.

- [ ] **Step 6: Run service tests**

Run:

```bash
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 pytest -p no:cacheprovider backend/tests/test_candidate_summary_service.py -q
```

Expected: all candidate summary tests pass.

---

### Task 2: Backend Task API For Candidate AI Summary

**Files:**
- Modify: `backend/app/services/update_service.py`
- Modify: `backend/app/services/data_service.py`
- Modify: `backend/app/api/routes.py`
- Test: `backend/tests/test_analysis_progress.py`
- Test: `backend/tests/test_quant_workbench_upgrade.py`

- [ ] **Step 1: Add failing API contract tests**

Add tests proving:

```python
def test_candidate_ai_summary_get_is_read_only(tmp_path, monkeypatch):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = CandidateSummaryService(db, api_key="configured")

    def fail_call(*_args, **_kwargs):
        raise AssertionError("GET must not call LLM")

    monkeypatch.setattr(service, "_call_llm", fail_call)
    result = service.read_summary("run-1", "000001.SZ")

    assert result["status"] == "not_requested"
```

```python
def test_candidate_ai_summary_task_reuses_existing_ready_result(tmp_path):
    db = Database(tmp_path / "ashare_test.duckdb")
    migrate(db)
    service = UpdateService(db)

    task_id, result_key = service.start_candidate_ai_summary(
        {
            "run_id": "run-1",
            "code": "000001.SZ",
            "input_hash": "hash-1",
            "force": False,
        },
        candidate_summary_runner=None,
    )

    assert task_id.startswith("ai-summary-")
    assert result_key["run_id"] == "run-1"
    assert result_key["code"] == "000001.SZ"
```

- [ ] **Step 2: Run tests and confirm they fail**

Run:

```bash
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 pytest -p no:cacheprovider backend/tests/test_candidate_summary_service.py backend/tests/test_analysis_progress.py backend/tests/test_quant_workbench_upgrade.py -q
```

Expected before implementation: FAIL because the task API does not exist.

- [ ] **Step 3: Add `DataService.candidate_ai_summary()`**

Add a read-only helper that returns the latest AI summary row for `run_id/code` and derives `not_requested` or `stale` without calling LLM.

- [ ] **Step 4: Add enqueue method to `UpdateService`**

Add:

```python
def start_candidate_ai_summary(self, payload: Dict[str, Any], candidate_summary_runner: Any) -> tuple[str, Dict[str, Any]]:
    self.candidate_summary_runner = candidate_summary_runner
    run_id = str(payload.get("run_id") or "")
    code = str(payload.get("code") or "")
    if not run_id or not code:
        raise ValueError("run_id 和 code 不能为空。")
    identity = candidate_summary_runner.prepare_from_result(run_id=run_id, code=code)
    existing = candidate_summary_runner.read_summary(run_id, code, input_hash=identity["input_hash"])
    if not payload.get("force") and existing.get("status") in {"queued", "running", "completed_full", "completed_partial"}:
        return str(existing.get("task_id") or ""), identity
    task_id = f"ai-summary-{uuid.uuid4().hex[:12]}"
    candidate_summary_runner.mark_queued(identity, task_id=task_id)
    self._enqueue_task(
        task_id,
        kind="candidate_ai_summary",
        stage="准备生成候选解释",
        source="LLM",
        summary={"run_id": run_id, "code": code, "input_hash": identity["input_hash"]},
        payload={"run_id": run_id, "code": code, "input_hash": identity["input_hash"]},
    )
    return task_id, identity
```

- [ ] **Step 5: Add dispatch branch**

In `_dispatch_queued_task()`, add:

```python
if kind == "candidate_ai_summary":
    if self.candidate_summary_runner is None:
        raise RuntimeError("候选解释服务尚未就绪。")
    self._run_candidate_ai_summary(task_id, payload)
    return
```

- [ ] **Step 6: Add runner method**

Add `_run_candidate_ai_summary()` that:

1. Patches task to `running`, stage `生成候选解释`.
2. Marks the result row `running`.
3. Calls `candidate_summary_runner.generate_and_store(identity, task_id=task_id)`.
4. Patches task to `completed_full` or `completed_partial` with summary pointer.
5. On exception, marks result row `failed` and patches task `failed`.

- [ ] **Step 7: Add routes**

Add:

```python
@router.get("/analysis/candidates/{run_id}/{code}/ai-summary")
def get_candidate_ai_summary(run_id: str, code: str) -> Dict[str, Any]:
    return data_service.candidate_ai_summary(run_id=run_id, code=code)
```

```python
@router.post("/tasks/candidate-ai-summary")
def start_candidate_ai_summary(payload: Dict[str, Any]) -> Dict[str, Any]:
    task_id, identity = update_service.start_candidate_ai_summary(payload, candidate_summary_service)
    return {
        "task_id": task_id,
        "run_id": identity["run_id"],
        "code": identity["code"],
        "input_hash": identity["input_hash"],
        "status": "queued",
    }
```

- [ ] **Step 8: Run backend task/API tests**

Run:

```bash
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 pytest -p no:cacheprovider backend/tests/test_candidate_summary_service.py backend/tests/test_analysis_progress.py backend/tests/test_quant_workbench_upgrade.py -q
```

Expected: all selected backend tests pass.

---

### Task 3: Frontend Query Keys And Task Hooks

**Files:**
- Create: `frontend/src/api/queryKeys.ts`
- Create: `frontend/src/hooks/useTaskTerminalInvalidation.ts`
- Create: `frontend/src/hooks/useActiveTaskPolling.ts`
- Create: `frontend/src/hooks/useTaskResultQuery.ts`
- Modify: `frontend/src/app/AppShell.tsx`
- Modify: `frontend/src/pages/status/StatusPage.tsx`
- Modify: `frontend/src/pages/backtest/SignalEvaluation.tsx`
- Modify: `frontend/src/pages/backtest/PortfolioBacktest.tsx`
- Test: `frontend/tests/analyze-completion-polling-structure.test.mjs`

- [ ] **Step 1: Add structure tests**

Add assertions that:

```javascript
test('frontend task polling and terminal invalidation use shared hooks', () => {
  const shell = src('app/AppShell.tsx');
  const status = src('pages/status/StatusPage.tsx');
  assert.match(shell, /useActiveTaskPolling/);
  assert.match(shell, /useTaskTerminalInvalidation/);
  assert.match(status, /useTaskTerminalInvalidation/);
});
```

```javascript
test('backtest task result polling uses shared hook', () => {
  assert.match(src('pages/backtest/SignalEvaluation.tsx'), /useTaskResultQuery/);
  assert.match(src('pages/backtest/PortfolioBacktest.tsx'), /useTaskResultQuery/);
});
```

- [ ] **Step 2: Run tests and confirm they fail**

Run:

```bash
npm --prefix frontend test -- --test-name-pattern="shared hook|task result polling"
```

Expected before implementation: FAIL because the hooks do not exist.

- [ ] **Step 3: Add `queryKeys` registry**

Create `frontend/src/api/queryKeys.ts`:

```typescript
export const queryKeys = {
  bootstrap: () => ['bootstrap'] as const,
  runtimeHealth: () => ['runtime-health'] as const,
  marketOverview: () => ['market-overview'] as const,
  tasks: {
    all: () => ['tasks'] as const,
    active: () => ['tasks', 'queued,running'] as const,
    recent: () => ['tasks', 'recent'] as const,
    flow: (taskId?: string) => ['task-flow', taskId] as const,
    progressNodes: (taskId?: string) => ['task-progress-nodes', taskId] as const,
  },
  analysis: {
    reports: () => ['result-reports'] as const,
    report: (runId?: string) => ['result-report', runId] as const,
    candidateAiSummary: (runId?: string, code?: string) => ['candidate-ai-summary', runId, code] as const,
  },
  backtest: {
    runs: () => ['backtest-runs'] as const,
    signalEvaluation: (runId?: string) => ['signal-evaluation', runId] as const,
    portfolio: (runId?: string) => ['portfolio-backtest', runId] as const,
  },
  intraday: {
    boards: () => ['intraday-boards'] as const,
    timeline: (code?: string, tradeDate?: string | null) => ['intraday-timeline', code, tradeDate] as const,
  },
};
```

- [ ] **Step 4: Add active polling hook**

Create `useActiveTaskPolling()` around existing `usePolling()` and include `brief_status` in active detection unless deliberately excluded by product decision.

- [ ] **Step 5: Add terminal invalidation hook**

Move the existing `seenTerminalTaskIds` effect out of `StatusPage` into `useTaskTerminalInvalidation(recentRows)`. Keep invalidation for:

```typescript
['bootstrap']
['tasks']
['result-reports']
['result-report', runId]
['backtest-runs']
['signal-evaluation', runId]
['portfolio-backtest', runId]
['intraday-boards']
['candidate-ai-summary', runId, code]
```

- [ ] **Step 6: Add result polling hook**

Create `useTaskResultQuery()` that keeps polling when:

```typescript
initialStatus === 'queued' ||
initialStatus === 'running' ||
resultStatus === 'queued' ||
resultStatus === 'running' ||
!query.state.data
```

This fixes the current backtest edge where the first empty result can stop polling too early.

- [ ] **Step 7: Run frontend tests**

Run:

```bash
npm --prefix frontend test
npm --prefix frontend run build
```

Expected: tests and build pass.

---

### Task 4: Frontend Candidate Evidence Panel Decoupling

**Files:**
- Modify: `frontend/src/api/strategy.ts`
- Modify: `frontend/src/pages/results/CandidateEvidencePanel.tsx`
- Test: `frontend/tests/ai-summary-decoupling-structure.test.mjs`
- Test: `frontend/tests/final-delivery-v2.test.mjs`

- [ ] **Step 1: Add structure tests**

Create `frontend/tests/ai-summary-decoupling-structure.test.mjs`:

```javascript
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { test } from 'node:test';

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = resolve(__dirname, '../src');
const src = (path) => readFileSync(resolve(root, path), 'utf8');

test('candidate AI summary query is read-only and generation is a mutation', () => {
  const api = src('api/strategy.ts');
  const panel = src('pages/results/CandidateEvidencePanel.tsx');
  assert.match(api, /request<.*CandidateAiSummary/);
  assert.match(api, /startCandidateAiSummary/);
  assert.match(panel, /useQuery/);
  assert.match(panel, /useMutation/);
  assert.match(panel, /startCandidateAiSummary/);
  assert.doesNotMatch(panel, /queryFn:[\\s\\S]*startCandidateAiSummary/);
});

test('candidate evidence panel still renders rule evidence before AI is ready', () => {
  const panel = src('pages/results/CandidateEvidencePanel.tsx');
  assert.match(panel, /fallbackExplanation/);
  assert.match(panel, /AI 解读/);
  assert.match(panel, /生成解释|重新生成|重试/);
});
```

- [ ] **Step 2: Run tests and confirm they fail**

Run:

```bash
npm --prefix frontend test -- --test-name-pattern="candidate AI summary"
```

Expected before implementation: FAIL because the panel still uses POST inside query.

- [ ] **Step 3: Split API functions**

Change `frontend/src/api/strategy.ts`:

```typescript
export type CandidateAiSummaryStatus = 'not_requested' | 'queued' | 'running' | 'completed_full' | 'completed_partial' | 'failed' | 'stale';

export type CandidateAiSummary = {
  status?: CandidateAiSummaryStatus;
  task_id?: string | null;
  run_id?: string;
  code?: string;
  input_hash?: string | null;
  enabled?: boolean;
  summary?: string | null;
  opportunities?: string[];
  risks?: string[];
  watch_plan?: string[];
  generated_at?: string | null;
  prompt_version?: string | null;
  fallback_reason?: 'missing_api_key' | 'llm_error' | 'invalid_response' | null;
  error_message?: string | null;
};

export function getCandidateAiSummary(runId: string, code: string): Promise<CandidateAiSummary> {
  return request<CandidateAiSummary>(`/api/analysis/candidates/${encodeURIComponent(runId)}/${encodeURIComponent(code)}/ai-summary`);
}

export function startCandidateAiSummary(runId: string, code: string, force = false): Promise<{ task_id: string; run_id: string; code: string; status: string }> {
  return post('/api/tasks/candidate-ai-summary', { run_id: runId, code, force });
}
```

- [ ] **Step 4: Update panel behavior**

In `CandidateEvidencePanel`:

1. Query only calls `getCandidateAiSummary(runId, candidate.code)`.
2. Generate button calls `startCandidateAiSummary(runId, candidate.code)`.
3. Query `refetchInterval` polls while status is `queued` or `running`.
4. Rule explanation renders immediately for `not_requested`, `queued`, `running`, `failed`, or `stale`.
5. AI badge shows `自然语言解释` only when status is `completed_full` and summary exists.

- [ ] **Step 5: Adjust legacy structure test**

Update `frontend/tests/final-delivery-v2.test.mjs` so the result panel still requires AI explanation UI but no longer requires POST-in-query.

- [ ] **Step 6: Run frontend tests and build**

Run:

```bash
npm --prefix frontend test
npm --prefix frontend run build
```

Expected: tests and build pass.

---

### Task 5: Full Verification And Server Rollout Checks

**Files:**
- Modify: `docs/superpowers/plans/2026-06-01-candidate-ai-summary-decoupling.md`

- [ ] **Step 1: Run local backend verification**

Run:

```bash
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 pytest -p no:cacheprovider backend/tests/test_candidate_summary_service.py backend/tests/test_analysis_progress.py backend/tests/test_analysis_reports.py backend/tests/test_quant_workbench_upgrade.py -q
```

Expected: all selected backend tests pass.

- [ ] **Step 2: Run local frontend verification**

Run:

```bash
npm --prefix frontend test
npm --prefix frontend run build
```

Expected: all frontend tests pass and production build succeeds. Existing Vite chunk-size warning is acceptable unless new chunking changes made it worse.

- [ ] **Step 3: Server database sanity check after deployment**

Run on the server after migrating:

```sql
DESCRIBE candidate_ai_summaries;
SELECT status, COUNT(*) FROM candidate_ai_summaries GROUP BY status ORDER BY status;
SELECT kind, status, COUNT(*) FROM task_runs WHERE kind = 'candidate_ai_summary' GROUP BY kind, status ORDER BY status;
```

Expected: new columns exist; AI summary rows move through `queued/running/completed_full/completed_partial/failed`; no large backlog of `running` rows.

- [ ] **Step 4: Server behavior check**

On the deployed page:

1. Open an analysis result. Expected: rule evidence displays immediately and no LLM request starts until the generate action is clicked.
2. Click generate for one candidate. Expected: task appears as `candidate_ai_summary`, panel shows queued/running, then AI text appears.
3. Refresh while queued/running. Expected: panel resumes from server status and does not create a duplicate task.
4. Disable or invalidate the LLM key in staging. Expected: fallback result is persisted as `completed_partial`; repeated refreshes do not spam the model endpoint.

---

## Recommended Execution Order

1. Backend result lifecycle first, because frontend must have a read-only GET endpoint before removing POST-in-query.
2. Backend task API second, because it creates the explicit generation boundary.
3. Frontend shared hooks third, because it reduces polling duplication before adding `candidate_ai_summary` task invalidation.
4. Candidate evidence panel fourth, because this is the user-visible behavior change.
5. Full verification and server rollout checks last.

## Deferred Work

- Do not batch-generate AI summaries for all candidates in this phase.
- Do not replace the in-process queue with Celery/RQ or another external queue in this phase.
- Do not generalize `update_checkpoints` into an AI DAG.
- Do not change analysis, backtest, intraday algorithms.
- Consider adding AbortSignal support to `frontend/src/api/client.ts` later; it is useful but not required once generation is no longer query-triggered.
