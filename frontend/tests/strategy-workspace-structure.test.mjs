import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import test from 'node:test';

const __dirname = dirname(fileURLToPath(import.meta.url));
const scannerSource = readFileSync(resolve(__dirname, '../src/pages/scanner/StrategyPage.tsx'), 'utf8');
const indicatorMatrixSource = readFileSync(resolve(__dirname, '../src/pages/scanner/IndicatorMatrix.tsx'), 'utf8');
const ruleCanvasSource = readFileSync(resolve(__dirname, '../src/pages/scanner/RuleCanvas.tsx'), 'utf8');
const ruleCardSource = readFileSync(resolve(__dirname, '../src/pages/scanner/RuleCard.tsx'), 'utf8');
const universeSource = readFileSync(resolve(__dirname, '../src/pages/scanner/UniversePanel.tsx'), 'utf8');
const draftSource = readFileSync(resolve(__dirname, '../src/hooks/useStrategyDraft.ts'), 'utf8');
const dataMapSource = readFileSync(resolve(__dirname, '../src/pages/data-map/DataMapPage.tsx'), 'utf8');
const capabilityCardSource = readFileSync(resolve(__dirname, '../src/pages/data-map/CapabilityCard.tsx'), 'utf8');
const marketFlowSource = readFileSync(resolve(__dirname, '../src/pages/overview/MarketFlowPanel.tsx'), 'utf8');
const shellSource = readFileSync(resolve(__dirname, '../src/app/AppShell.tsx'), 'utf8');

test('scanner page is organized as a professional rule canvas', () => {
  assert.match(scannerSource, /UniversePanel/);
  assert.match(scannerSource, /IndicatorMatrix/);
  assert.match(scannerSource, /RuleCanvas/);
  assert.match(scannerSource, /StrategySummary/);
  const combined = `${scannerSource}\n${indicatorMatrixSource}\n${ruleCanvasSource}`;
  for (const label of ['股票池', '硬性筛选', '评分因子', '风险控制', '展示字段', '组合加分', '高级参数']) {
    assert.match(combined, new RegExp(label));
  }
  assert.doesNotMatch(scannerSource, /StrategyRuleBuilder/);
  assert.doesNotMatch(scannerSource, /StrategyResonanceBuilder/);
});

test('resonance can only reference filter and score rule chips', () => {
  assert.match(scannerSource, /selectableResonanceRules/);
  assert.match(scannerSource, /rule\.action === 'filter' \|\| rule\.action === 'score'/);
  assert.match(ruleCanvasSource, /resonance-chip-grid/);
  assert.doesNotMatch(scannerSource, /risk.*resonance/i);
  assert.doesNotMatch(scannerSource, /display.*resonance/i);
});

test('scanner supports adding editing saving and running current draft', () => {
  assert.match(indicatorMatrixSource, /onAddRule/);
  assert.match(indicatorMatrixSource, /onPatchRule/);
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

test('scanner has explicit preset management instead of only saving a single strategy name', () => {
  for (const label of ['新建', '复制', '保存', '另存为', '保存为默认', '删除']) {
    assert.match(scannerSource, new RegExp(label));
  }
  assert.match(scannerSource, /duplicateStrategy/);
  assert.match(scannerSource, /deleteStrategy/);
  assert.match(scannerSource, /presetId/);
  assert.match(scannerSource, /isSystem/);
  assert.match(scannerSource, /isDefault/);
  assert.match(draftSource, /presetId/);
  assert.match(draftSource, /isSystem/);
  assert.match(draftSource, /isDefault/);
  assert.match(draftSource, /未命名策略/);
});

test('top actions and data health use precise update semantics', () => {
  assert.match(shellSource, /打开数据中心/);
  assert.doesNotMatch(shellSource, /补齐数据类别/);
  assert.match(dataMapSource, /mode:\s*'capability_backfill'/);
  assert.match(dataMapSource, /capability:\s*capability\.capability/);
  assert.match(capabilityCardSource, /补齐/);
  assert.match(capabilityCardSource, /onBackfill/);
});

test('market overview reads the backend field names actually returned today', () => {
  assert.doesNotMatch(marketFlowSource, /risk_score/);
  assert.match(marketFlowSource, /latest_date/);
  assert.match(marketFlowSource, /status === 'fresh'/);
});

test('checkbox UI uses polished check tiles without native browser checkboxes', () => {
  assert.match(universeSource, /CheckTile/);
  assert.doesNotMatch(universeSource, /type="checkbox"/);
  assert.match(indicatorMatrixSource, /Switch/);
  assert.doesNotMatch(indicatorMatrixSource, /type="checkbox"/);
  assert.match(ruleCanvasSource, /CheckTile/);
  assert.doesNotMatch(ruleCanvasSource, /type="checkbox"/);
  assert.match(ruleCardSource, /CheckTile/);
  assert.doesNotMatch(ruleCardSource, /type="checkbox"/);
});
