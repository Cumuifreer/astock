import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import test from 'node:test';

const __dirname = dirname(fileURLToPath(import.meta.url));
const appSource = readFileSync(resolve(__dirname, '../src/App.tsx'), 'utf8');

test('strategy editor uses one unified rule workspace', () => {
  assert.match(appSource, /<StrategyRuleWorkspace\b/);
  assert.match(appSource, /function StrategyRuleWorkspace\b/);
  assert.doesNotMatch(appSource, /<StrategyRuleBuilder\b/);
  assert.doesNotMatch(appSource, /<StrategyResonanceBuilder\b/);
});

test('resonance draft is selected from existing rule chips', () => {
  assert.match(appSource, /toggleDraftRuleId/);
  assert.match(appSource, /rule-resonance-chip-grid/);
  assert.doesNotMatch(appSource, /resonance-draft-selects/);
});
