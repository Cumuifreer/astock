import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import ts from 'typescript';

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = resolve(__dirname, '../src');

function read(path) {
  return readFileSync(resolve(root, path), 'utf8');
}

async function loadFormatUtils() {
  const source = read('utils/format.ts');
  const output = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ES2022,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText;
  return import(`data:text/javascript;base64,${Buffer.from(output).toString('base64')}`);
}

test('ratio percentages multiply decimal ratios before rendering', async () => {
  const { formatRatioPercent } = await loadFormatUtils();

  assert.equal(formatRatioPercent?.(0.08), '8.00%');
  assert.equal(formatRatioPercent?.(-0.034), '-3.40%');
  assert.equal(formatRatioPercent?.(null, 2, '待回测'), '待回测');
});

