import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = resolve(__dirname, '../src');

function read(path) {
  return readFileSync(resolve(root, path), 'utf8');
}

test('strict analysis results show the existing filter funnel without changing candidate logic', () => {
  const panelPath = resolve(root, 'pages/results/StrictFunnelPanel.tsx');
  const results = read('pages/results/ResultsPage.tsx');
  const tokens = read('design/tokens.css');

  assert.ok(existsSync(panelPath), 'strict funnel panel component should exist');

  const panel = read('pages/results/StrictFunnelPanel.tsx');
  const tableIndex = results.indexOf('<CandidateTable');
  const funnelIndex = results.indexOf('<StrictFunnelPanel');
  const candidateBranchIndex = results.indexOf('filteredCandidates.length ?');

  assert.match(results, /import \{ StrictFunnelPanel \} from '\.\/StrictFunnelPanel';/);
  assert.match(results, /const activeFunnel = /);
  assert.match(results, /reportDetail\.data\?\.candidates\?\.funnel/);
  assert.match(results, /bootstrap\.data\?\.candidates\?\.funnel/);
  assert.ok(funnelIndex > 0, 'strict funnel should render in results page');
  assert.ok(tableIndex > funnelIndex, 'strict funnel should appear before the candidate table');
  assert.ok(funnelIndex < candidateBranchIndex, 'strict funnel should still render when strict mode leaves no candidates');
  assert.match(results, /analysisMode=\{activeReport\?\.config\?\.analysis_mode\}/);

  assert.match(panel, /analysisMode !== 'strict'/);
  assert.match(panel, /removed_count\) > 0/);
  assert.match(panel, /step\.step_name !== '候选数量'/);
  assert.match(panel, /严格筛选漏斗/);
  assert.match(panel, /减少/);
  assert.doesNotMatch(panel, /useMutation|fetch|axios|window\.fetch/);
  assert.match(tokens, /\.strict-funnel-panel/);
  assert.match(tokens, /\.strict-funnel-row/);
});
