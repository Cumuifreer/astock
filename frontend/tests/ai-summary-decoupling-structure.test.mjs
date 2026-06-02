import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { test } from 'node:test';

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = resolve(__dirname, '../src');
const src = (path) => readFileSync(resolve(root, path), 'utf8');

test('candidate AI summary query is read-only and frontend has no generation control', () => {
  const api = src('api/strategy.ts');
  const panel = src('pages/results/CandidateEvidencePanel.tsx');

  assert.match(api, /export function getCandidateAiSummary\(runId: string, code: string\): Promise<CandidateAiSummary>/);
  assert.match(api, /request<CandidateAiSummary>/);
  assert.doesNotMatch(api, /export function startCandidateAiSummary/);

  assert.match(panel, /useQuery/);
  assert.match(panel, /getCandidateAiSummary\(runId, candidate\.code\)/);
  assert.doesNotMatch(panel, /startCandidateAiSummary|generateButtonLabel|生成解释|重新生成|重试/);
  const queryBlock = panel.match(/const aiSummary = useQuery\(\{[\s\S]*?\n  \}\);/)?.[0] || '';
  assert.doesNotMatch(queryBlock, /startCandidateAiSummary/);
  assert.doesNotMatch(queryBlock, /matched_rules|risk_items/);
});

test('candidate evidence panel still renders rule evidence before AI is ready', () => {
  const panel = src('pages/results/CandidateEvidencePanel.tsx');
  assert.match(panel, /fallbackExplanation/);
  assert.match(panel, /AI 解读/);
  assert.match(panel, /后台自动生成/);
});
