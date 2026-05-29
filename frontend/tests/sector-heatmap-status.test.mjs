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

test('status page avoids zero denominator progress copy', () => {
  const status = read('pages/status/StatusPage.tsx');

  assert.match(status, /taskProgressCopy/);
  assert.match(status, /进度待返回/);
  assert.doesNotMatch(status, /已完成 \{task\.processed\} \/ 共 \{task\.total \|\| 0\}/);
});

test('sector heatmap renders mode-specific fields only', () => {
  const heatmap = read('pages/overview/SectorHeatmap.tsx');

  assert.match(heatmap, /tooltipLines\(raw,\s*mode\)/);
  assert.match(heatmap, /tileDetail\(sector,\s*mode\)/);
  assert.match(heatmap, /hasDisplayableData\(sector,\s*mode\)/);
  assert.match(heatmap, /if \(mode === 'money'\)/);
  assert.match(heatmap, /if \(mode === 'limit'\)/);
  assert.match(heatmap, /成交额：\$\{formatMoney\(raw\.amount\)\}/);
  assert.doesNotMatch(heatmap, /formatter:[\s\S]{0,450}主力净流入/);
});
