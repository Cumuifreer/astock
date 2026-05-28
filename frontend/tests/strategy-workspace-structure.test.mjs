import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import test from 'node:test';

const __dirname = dirname(fileURLToPath(import.meta.url));
const scannerSource = readFileSync(resolve(__dirname, '../src/pages/scanner/StrategyPage.tsx'), 'utf8');

test('scanner page is organized as a professional rule canvas', () => {
  assert.match(scannerSource, /UniversePanel/);
  assert.match(scannerSource, /RuleCanvas/);
  assert.match(scannerSource, /StrategySummary/);
  for (const label of ['Universe', 'Filters', 'Scores', 'Risks', 'Display', 'Resonance', 'Advanced']) {
    assert.match(scannerSource, new RegExp(label));
  }
  assert.doesNotMatch(scannerSource, /StrategyRuleBuilder/);
  assert.doesNotMatch(scannerSource, /StrategyResonanceBuilder/);
});

test('resonance can only reference filter and score rule chips', () => {
  assert.match(scannerSource, /selectableResonanceRules/);
  assert.match(scannerSource, /rule\.action === 'filter' \|\| rule\.action === 'score'/);
  assert.match(scannerSource, /resonance-chip-grid/);
  assert.doesNotMatch(scannerSource, /risk.*resonance/i);
  assert.doesNotMatch(scannerSource, /display.*resonance/i);
});
