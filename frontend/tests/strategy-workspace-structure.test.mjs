import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import test from 'node:test';

const __dirname = dirname(fileURLToPath(import.meta.url));
const scannerSource = readFileSync(resolve(__dirname, '../src/pages/scanner/StrategyPage.tsx'), 'utf8');
const factorPickerSource = readFileSync(resolve(__dirname, '../src/pages/scanner/FactorPicker.tsx'), 'utf8');
const ruleCanvasSource = readFileSync(resolve(__dirname, '../src/pages/scanner/RuleCanvas.tsx'), 'utf8');
const ruleCardSource = readFileSync(resolve(__dirname, '../src/pages/scanner/RuleCard.tsx'), 'utf8');
const shellSource = readFileSync(resolve(__dirname, '../src/app/AppShell.tsx'), 'utf8');

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

test('scanner supports adding editing saving and running current draft', () => {
  assert.match(factorPickerSource, /onAddRule/);
  assert.match(factorPickerSource, /加入规则/);
  assert.match(ruleCardSource, /onPatch/);
  assert.match(ruleCardSource, /operator/);
  assert.match(ruleCardSource, /missing_policy/);
  assert.match(ruleCardSource, /删除规则/);
  assert.match(ruleCanvasSource, /onSetResonances/);
  assert.match(scannerSource, /保存策略/);
  assert.match(scannerSource, /保存为默认/);
  assert.match(scannerSource, /运行当前策略/);
  assert.match(shellSource, /useStrategyDraft\.getState/);
  assert.match(shellSource, /composeStrategyConfig/);
  assert.doesNotMatch(shellSource, /const config = bootstrap\.data\?\.default_strategy/);
});
