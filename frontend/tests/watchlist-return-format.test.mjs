import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import ts from 'typescript';

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = resolve(__dirname, '../src');

async function loadFormatUtils() {
  const source = readFileSync(resolve(root, 'utils/format.ts'), 'utf8');
  const output = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ES2022,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText;
  return import(`data:text/javascript;base64,${Buffer.from(output).toString('base64')}`);
}

test('watchlist return ratios render as real percentages', async () => {
  const { formatReturnPercent } = await loadFormatUtils();

  assert.equal(formatReturnPercent(0.05), '5.00%');
  assert.equal(formatReturnPercent(-0.034), '-3.40%');
  assert.equal(formatReturnPercent(null), '待复盘');
});

test('watchlist table colors every numeric return column', () => {
  const source = readFileSync(resolve(root, 'pages/watchlist/WatchlistPage.tsx'), 'utf8');

  for (const key of ['return_1d', 'return_3d', 'return_5d', 'return_10d', 'return_latest']) {
    assert.match(source, new RegExp(`ReturnCell item=\\{row\\.original\\} field="${key}"`));
  }
  assert.match(source, /watchlist-return-cell/);
  assert.match(source, /returnTone/);
});
