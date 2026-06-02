import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { test } from 'node:test';

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = resolve(__dirname, '../src');

function src(path) {
  return readFileSync(resolve(root, path), 'utf8');
}

test('status page uses live active task rows instead of bootstrap fallbacks', () => {
  const status = src('pages/status/StatusPage.tsx');
  assert.match(status, /getRuntimeHealth/);
  assert.match(status, /const effectiveActiveRows = activeRows/);
  assert.doesNotMatch(status, /useBootstrap/);
  assert.doesNotMatch(status, /bootstrapActiveRows/);
  assert.doesNotMatch(status, /fallbackTasks/);
  assert.doesNotMatch(status, /activeRows\.length\s*\?\s*activeRows\s*:\s*fallbackTasks\.filter/);
});

test('terminal task completion invalidates matching result queries', () => {
  const hook = src('hooks/useTaskTerminalInvalidation.ts');
  const keys = src('api/queryKeys.ts');
  for (const key of ['result-reports', 'result-report', 'backtest-runs', 'signal-evaluation', 'portfolio-backtest', 'intraday-boards', 'candidate-ai-summary']) assert.match(keys, new RegExp(key));
  assert.match(hook, /seenTerminalTaskIds/);
});

test('app shell polls task and result keys while work is active', () => {
  const shell = src('app/AppShell.tsx');
  const keys = src('api/queryKeys.ts');
  assert.match(shell, /useActiveTaskPolling/);
  for (const key of ['tasks', 'result-reports', 'backtest-runs', 'intraday-boards']) assert.match(keys, new RegExp(key));
});

test('frontend task polling and terminal invalidation use shared hooks', () => {
  const shell = src('app/AppShell.tsx');
  const status = src('pages/status/StatusPage.tsx');
  assert.match(shell, /useActiveTaskPolling/);
  assert.match(shell, /useTaskTerminalInvalidation/);
  assert.match(status, /useTaskTerminalInvalidation/);
});

test('backtest task result polling uses shared hook', () => {
  assert.match(src('pages/backtest/SignalEvaluation.tsx'), /useTaskResultQuery/);
  assert.match(src('pages/backtest/PortfolioBacktest.tsx'), /useTaskResultQuery/);
});

test('task result polling stops after terminal result data arrives', () => {
  const hook = src('hooks/useTaskResultQuery.ts');
  assert.match(hook, /const resultStatus = getResultStatus\(data\);/);
  assert.match(hook, /if \(activeTaskStatuses\.has\(String\(resultStatus \|\| ''\)\)\) return intervalMs;/);
  assert.match(hook, /if \(data\) return false;/);
  assert.match(hook, /if \(activeTaskStatuses\.has\(String\(initialStatus \|\| ''\)\)\) return intervalMs;/);
});

test('candidate AI summary mutation updates cache for the requested candidate', () => {
  const panel = src('pages/results/CandidateEvidencePanel.tsx');
  assert.match(panel, /mutationFn: \(\{ runId: targetRunId, code, force \}/);
  assert.match(panel, /onSuccess: \(result, variables\)/);
  assert.match(panel, /result\.run_id \|\| variables\.runId/);
  assert.doesNotMatch(panel, /mutationFn: \(\{ force \}: \{ force: boolean \}\)/);
});

test('backtest result pages resume from persisted run ids instead of mutation-only state', () => {
  const page = src('pages/backtest/BacktestPage.tsx');
  const signal = src('pages/backtest/SignalEvaluation.tsx');
  const portfolio = src('pages/backtest/PortfolioBacktest.tsx');
  assert.match(page, /selectedSignalRunId/);
  assert.match(page, /selectedPortfolioRunId/);
  assert.match(page, /persistRunId\(signalRunStorageKey/);
  assert.match(page, /persistRunId\(portfolioRunStorageKey/);
  assert.match(signal, /selectedRunId/);
  assert.match(portfolio, /selectedRunId/);
  assert.doesNotMatch(signal, /queryKeys\.backtest\.signalEvaluation\(mutation\.data\?\.runId\)/);
  assert.doesNotMatch(portfolio, /queryKeys\.backtest\.portfolio\(mutation\.data\?\.runId\)/);
});

test('results page follows latest run unless historical report is manually selected', () => {
  const results = src('pages/results/ResultsPage.tsx');
  assert.match(results, /manualRunSelection/);
  assert.match(results, /setManualRunSelection\(value !== latestRunId\)/);
  assert.match(results, /selectedIsLatest/);
  assert.match(results, /flattenedReports\[0\]\?\.id\s*\|\|\s*getLatestRunId/);
  assert.doesNotMatch(results, /if \(!selectedRunId && latestRunId\)/);
});

test('results page only uses bootstrap report data when it matches the selected run', () => {
  const results = src('pages/results/ResultsPage.tsx');
  assert.match(results, /bootstrapCandidateRows/);
  assert.match(results, /getLatestRunId\(bootstrap\.data\?\.candidates\)\s*===\s*selectedRunId/);
  assert.match(results, /bootstrapLatestReport/);
  assert.match(results, /bootstrap\.data\?\.latest_analysis\?\.id\s*===\s*selectedRunId/);
});

test('analysis task job type accepts backend snake case and frontend camel case ids', () => {
  const strategy = src('api/strategy.ts');
  for (const field of ['task_id', 'run_id', 'taskId', 'runId']) {
    assert.match(strategy, new RegExp(`${field}\\?:\\s*string`));
  }
});
