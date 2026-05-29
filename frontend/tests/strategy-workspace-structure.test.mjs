import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import test from 'node:test';

const __dirname = dirname(fileURLToPath(import.meta.url));
const scannerSource = readFileSync(resolve(__dirname, '../src/pages/scanner/StrategyPage.tsx'), 'utf8');
const indicatorMatrixSource = readFileSync(resolve(__dirname, '../src/pages/scanner/IndicatorMatrix.tsx'), 'utf8');
const combinationSource = readFileSync(resolve(__dirname, '../src/pages/scanner/CombinationBonusPanel.tsx'), 'utf8');
const ruleCardSource = readFileSync(resolve(__dirname, '../src/pages/scanner/RuleCard.tsx'), 'utf8');
const universeSource = readFileSync(resolve(__dirname, '../src/pages/scanner/UniversePanel.tsx'), 'utf8');
const draftSource = readFileSync(resolve(__dirname, '../src/hooks/useStrategyDraft.ts'), 'utf8');
const dataMapSource = readFileSync(resolve(__dirname, '../src/pages/data-map/DataMapPage.tsx'), 'utf8');
const capabilityCardSource = readFileSync(resolve(__dirname, '../src/pages/data-map/CapabilityCard.tsx'), 'utf8');
const marketFlowSource = readFileSync(resolve(__dirname, '../src/pages/overview/MarketFlowPanel.tsx'), 'utf8');
const shellSource = readFileSync(resolve(__dirname, '../src/app/AppShell.tsx'), 'utf8');
const indicatorRegistrySource = readFileSync(resolve(__dirname, '../../backend/app/services/indicator_registry.py'), 'utf8');

test('scanner page is organized as one indicator matrix plus combination panel', () => {
  assert.match(scannerSource, /IndicatorMatrix/);
  assert.match(scannerSource, /CombinationBonusPanel/);
  assert.doesNotMatch(scannerSource, /StrategySummary/);
  assert.doesNotMatch(scannerSource, /grid-aside/);
  assert.match(scannerSource, /scanner-workspace-full/);
  assert.doesNotMatch(scannerSource, /UniversePanel|RuleCanvas/);
  const combined = `${scannerSource}\n${indicatorMatrixSource}\n${combinationSource}`;
  for (const label of ['基础股票池', '流动性与成交', '相对强弱', '平台与突破', '组合加分']) {
    assert.match(combined, new RegExp(label));
  }
  assert.match(indicatorMatrixSource, /点击左侧开启/);
  assert.match(indicatorMatrixSource, /expandedGroups/);
  assert.match(indicatorMatrixSource, /indicator-group-toggle/);
  assert.match(indicatorMatrixSource, /formatChineseMoneyUnit/);
  assert.match(indicatorMatrixSource, /money-unit-hint/);
  assert.doesNotMatch(combined, /高级参数|规则配置|调整参数|怎么用|尚未启用|开启后填写|仅展示|移除|影响/);
  assert.doesNotMatch(scannerSource, /StrategyRuleBuilder/);
  assert.doesNotMatch(scannerSource, /StrategyResonanceBuilder/);
});

test('RPS indicators do not expose the global RPS period inside individual RPS cards', () => {
  assert.match(indicatorRegistrySource, /data_indicator\("rps20"[\s\S]*?paired_strategy_ids=\["min_rps20"\]/);
  assert.match(indicatorRegistrySource, /data_indicator\("rps60"[\s\S]*?paired_strategy_ids=\["min_rps60"\]/);
  assert.match(indicatorRegistrySource, /data_indicator\("rps120"[\s\S]*?paired_strategy_ids=\["min_rps120"\]/);
  assert.doesNotMatch(indicatorRegistrySource, /data_indicator\("rps20"[\s\S]*?paired_strategy_ids=\[[^\]]*"rps_window"[^\]]*\]/);
  assert.doesNotMatch(indicatorRegistrySource, /data_indicator\("rps60"[\s\S]*?paired_strategy_ids=\[[^\]]*"rps_window"[^\]]*\]/);
});

test('combination bonus can only reference enabled filter and score indicators', () => {
  assert.match(scannerSource, /selectableResonanceRules/);
  assert.match(scannerSource, /rule\.enabled/);
  assert.match(scannerSource, /rule\.action === 'filter' \|\| rule\.action === 'score'/);
  assert.match(combinationSource, /添加组合加分/);
  assert.match(combinationSource, /combo-choice-grid/);
  assert.match(combinationSource, /combo-selected-chip/);
  assert.match(combinationSource, /至少选择两个指标/);
  assert.doesNotMatch(scannerSource, /risk.*resonance/i);
  assert.doesNotMatch(scannerSource, /display.*resonance/i);
});

test('scanner supports adding editing saving and running current draft', () => {
  assert.match(indicatorMatrixSource, /onAddRule/);
  assert.match(indicatorMatrixSource, /onPatchRule/);
  assert.doesNotMatch(indicatorMatrixSource, /onRemoveRule|removeRule/);
  assert.match(combinationSource, /onSetResonances/);
  assert.match(scannerSource, /严格筛选/);
  assert.match(scannerSource, /评分排序/);
  assert.match(scannerSource, /analysis_mode/);
  assert.match(scannerSource, /保存/);
  assert.doesNotMatch(scannerSource, /保存为默认|系统策略|默认策略/);
  assert.match(scannerSource, /运行当前策略/);
  assert.match(scannerSource, /分析任务已开始，可在任务状态查看进度/);
  assert.match(scannerSource, /window\.location\.hash = '#status'/);
  assert.match(scannerSource, /strategy_name/);
  assert.doesNotMatch(shellSource, /运行策略/);
  assert.doesNotMatch(shellSource, /runStrategy/);
  assert.doesNotMatch(shellSource, /useStrategyDraft\.getState/);
  assert.doesNotMatch(shellSource, /const config = bootstrap\.data\?\.default_strategy/);
});

test('scanner has explicit preset management instead of only saving a single strategy name', () => {
  for (const label of ['新建', '复制', '保存', '另存为', '删除']) {
    assert.match(scannerSource, new RegExp(label));
  }
  assert.match(scannerSource, /新建未保存策略/);
  assert.match(scannerSource, /当前是未保存草稿，无需删除/);
  assert.match(scannerSource, /系统模板可复制后编辑/);
  assert.match(scannerSource, /showToast/);
  assert.match(scannerSource, /patchBootstrapStrategies/);
  assert.doesNotMatch(scannerSource, /duplicateStrategy|保存为默认|系统策略|默认策略/);
  assert.doesNotMatch(scannerSource, /label:\s*'未命名策略'/);
  assert.match(scannerSource, /deleteStrategy/);
  assert.match(scannerSource, /presetId/);
  assert.match(draftSource, /presetId/);
  assert.match(scannerSource, /nextUnnamedName/);
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
  assert.match(marketFlowSource, /status === 'normal'/);
});

test('checkbox UI uses polished check tiles without native browser checkboxes', () => {
  assert.match(universeSource, /CheckTile/);
  assert.doesNotMatch(universeSource, /type="checkbox"/);
  assert.match(indicatorMatrixSource, /Switch/);
  assert.doesNotMatch(indicatorMatrixSource, /type="checkbox"/);
  assert.match(combinationSource, /CheckTile/);
  assert.doesNotMatch(combinationSource, /type="checkbox"/);
  assert.match(ruleCardSource, /CheckTile/);
  assert.doesNotMatch(ruleCardSource, /type="checkbox"/);
});
