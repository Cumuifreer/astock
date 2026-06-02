import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { test } from 'node:test';

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(__dirname, '../..');
const srcRoot = resolve(__dirname, '../src');
const oldSourceNames = /\b(?:AkShare|Baostock|AData|akshare|baostock|adata)\b/;

function readRepo(path) {
  return readFileSync(resolve(repoRoot, path), 'utf8');
}

function readSrc(path) {
  return readFileSync(resolve(srcRoot, path), 'utf8');
}

test('data-source documentation presents Tushare with local DuckDB cache only', () => {
  for (const path of [
    'README.md',
    'docs/superpowers/specs/2026-05-19-ashare-signal-design.md',
    'docs/superpowers/specs/2026-05-25-intraday-tushare-data-design.md',
  ]) {
    const source = readRepo(path);
    assert.doesNotMatch(source, oldSourceNames, `${path} should not present retired external sources`);
    assert.doesNotMatch(source, /(?:兜底|备用源|回退|fallback)/i, `${path} should not advertise external fallbacks`);
    assert.match(source, /Tushare/, `${path} should name Tushare as the external source`);
    assert.match(source, /DuckDB|本地缓存/, `${path} should describe the local cache`);
  }
  const readme = readRepo('README.md');
  assert.doesNotMatch(readme, /多源资讯|自动抓取|DeepSeek|LLM|自动排队生成第一份/);
});

test('data map status copy uses Tushare and DuckDB labels instead of fallback wording', () => {
  const dataMap = readSrc('pages/data-map/DataMapPage.tsx');
  assert.doesNotMatch(dataMap, oldSourceNames);
  assert.doesNotMatch(dataMap, /fallback:\s*'回退'|数据源切换/);
  assert.match(dataMap, /Tushare/);
  assert.match(dataMap, /DuckDB|本地缓存/);
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
