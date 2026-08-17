import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { test } from 'node:test';

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(__dirname, '../..');
const srcRoot = resolve(__dirname, '../src');
function readRepo(path) {
  return readFileSync(resolve(repoRoot, path), 'utf8');
}

function readSrc(path) {
  return readFileSync(resolve(srcRoot, path), 'utf8');
}

test('data-source documentation presents guarded free sources and optional Tushare', () => {
  const readme = readRepo('README.md');
  assert.match(readme, /Baostock/);
  assert.match(readme, /AkShare 新浪/);
  assert.match(readme, /ASHARE_TUSHARE_ENABLED=0/);
  assert.match(readme, /DuckDB|本地缓存/);
  assert.match(readme, /不会使用东财或腾讯备用源/);
});

test('data map status copy exposes free mode and source contracts', () => {
  const dataMap = readSrc('pages/data-map/DataMapPage.tsx');
  assert.match(dataMap, /免费模式/);
  assert.match(dataMap, /Baostock 行业\/估值/);
  assert.match(dataMap, /expected_source|actual_source/);
});

test('data map and candidate risk copy avoid misleading states', () => {
  const dataMap = readSrc('pages/data-map/DataMapPage.tsx');
  const table = readSrc('pages/results/CandidateTable.tsx');

  assert.match(dataMap, /状态\/交易约束/);
  assert.match(dataMap, /ST \/ 停牌状态/);
  assert.match(dataMap, /onError:\s*\(error\)\s*=>\s*showToast/);
  assert.match(table, /Number\(candidate\.amplitude \|\| 0\) >= 0\.08/);
  assert.doesNotMatch(table, /candidate\.amplitude \|\| 0\) >= 8/);
});

test('daily brief UI is read-only and does not expose generation controls', () => {
  const overview = readSrc('pages/overview/OverviewPage.tsx');
  const marketApi = readSrc('api/market.ts');

  assert.doesNotMatch(overview, /重新生成简报|useMutation|regenerateMarketBrief/);
  assert.doesNotMatch(marketApi, /daily-brief\/regenerate|regenerateMarketBrief/);
  assert.match(overview, /市场简报/);
});
