import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import test from 'node:test';

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = resolve(__dirname, '../src');

function read(path) {
  return readFileSync(resolve(root, path), 'utf8');
}

test('candidate result actions sit in the results toolbar before the candidate table', () => {
  const results = read('pages/results/ResultsPage.tsx');
  const toolbarIndex = results.indexOf('aria-label="候选操作"');
  const tableIndex = results.indexOf('<CandidateTable');

  assert.ok(toolbarIndex > 0, 'candidate actions should live in the results action row');
  assert.ok(tableIndex > 0, 'candidate table should still render');
  assert.ok(toolbarIndex < tableIndex, 'candidate actions should appear before the candidate table');
  assert.match(results, /打开K线[\s\S]*加入观察池/);
  assert.doesNotMatch(results, /重新运行|导出|rerunMutation|exportCandidates|runStrategy/);
});

test('candidate evidence panel stays focused on explanation content', () => {
  const panel = read('pages/results/CandidateEvidencePanel.tsx');
  const candidateRender = panel.slice(panel.indexOf('const watchPlan'), panel.indexOf('function normalizeAiSummary'));
  const gridIndex = candidateRender.indexOf('className="grid-2 evidence-grid"');

  assert.ok(gridIndex > 0, 'evidence grid should still render');
  assert.doesNotMatch(candidateRender, /aria-label="候选操作"|打开K线|加入观察池|addWatchlistItems/);
  assert.doesNotMatch(candidateRender, /aria-label="可操作动作"/);
});

test('app shell no longer exposes manual daily update controls', () => {
  const shell = read('app/AppShell.tsx');

  assert.doesNotMatch(shell, /syncTodayMutation|forceUpdateMutation/);
  assert.doesNotMatch(shell, /syncToday/);
  assert.doesNotMatch(shell, /同步今日数据|强制全量更新/);
});
