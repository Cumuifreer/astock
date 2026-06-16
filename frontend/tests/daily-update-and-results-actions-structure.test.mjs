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

test('candidate result actions sit above the AI evidence grid', () => {
  const panel = read('pages/results/CandidateEvidencePanel.tsx');
  const candidateRender = panel.slice(panel.indexOf('const watchPlan'), panel.indexOf('function normalizeAiSummary'));
  const actionIndex = candidateRender.indexOf('aria-label="候选操作"');
  const gridIndex = candidateRender.indexOf('className="grid-2 evidence-grid"');

  assert.ok(actionIndex > 0, 'candidate action row should be part of the header area');
  assert.ok(gridIndex > 0, 'evidence grid should still render');
  assert.ok(actionIndex < gridIndex, 'K-line and watchlist actions should appear before evidence blocks');
  assert.match(candidateRender, /打开K线[\s\S]*加入观察池/);
  assert.doesNotMatch(candidateRender, /aria-label="可操作动作"/);
});

test('app shell no longer exposes manual daily update controls', () => {
  const shell = read('app/AppShell.tsx');

  assert.doesNotMatch(shell, /syncTodayMutation|forceUpdateMutation/);
  assert.doesNotMatch(shell, /syncToday/);
  assert.doesNotMatch(shell, /同步今日数据|强制全量更新/);
});
