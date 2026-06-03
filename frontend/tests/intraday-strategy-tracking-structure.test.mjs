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

test('intraday page renders strategy tracking before the three market boards', () => {
  const page = read('pages/intraday/IntradayPage.tsx');
  const trackingIndex = page.indexOf("value: 'strategy-tracking'");
  const anomalyIndex = page.indexOf("value: 'anomaly'");

  assert.ok(trackingIndex > 0);
  assert.ok(anomalyIndex > trackingIndex);
  assert.match(page, /StrategyTrackingPanel/);
  assert.match(page, /getIntradayStrategyTracking/);
  assert.match(page, /runIntradayStrategyTracking/);
  assert.match(page, /saveIntradayStrategyTrackingConfig/);
  assert.match(page, /saveIntradayConfig/);
  assert.match(page, /Switch/);
  assert.match(page, /boardSwitches/);
  assert.match(page, /actions=\{/);
  assert.match(page, /<Button[\s\S]*运行策略追踪[\s\S]*<\/Button>/);
  assert.match(page, /label:\s*preset\.name/);
  const panelBlock = page.slice(page.indexOf('function StrategyTrackingPanel'), page.indexOf('function StrategyTrackingCard'));
  assert.doesNotMatch(panelBlock, /运行策略追踪/);
  assert.doesNotMatch(panelBlock, /onRun/);
  assert.doesNotMatch(page, /strategyOptionLabel|未发布/);
  assert.doesNotMatch(page, /disabled=\{isPending/);
  assert.doesNotMatch(page, /<select\b/i);
  assert.doesNotMatch(page, /<input[^>]+type=["']checkbox["']/i);
});

test('tabs component supports a right aligned action slot', () => {
  const tabs = read('design/Tabs.tsx');

  assert.match(tabs, /actions\?: ReactNode/);
  assert.match(tabs, /tabs-actions/);
});

test('intraday API exposes read and update endpoints for strategy tracking', () => {
  const api = read('api/intraday.ts');

  assert.match(api, /getIntradayStrategyTracking/);
  assert.match(api, /saveIntradayStrategyTrackingConfig/);
  assert.match(api, /runIntradayStrategyTracking/);
  assert.match(api, /saveIntradayConfig/);
  assert.match(api, /\/api\/intraday\/strategy-tracking/);
  assert.match(api, /\/api\/intraday\/strategy-tracking\/config/);
  assert.match(api, /\/api\/intraday\/strategy-tracking\/run/);
  assert.match(api, /\/api\/intraday\/config/);
});
