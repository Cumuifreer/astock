import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import ts from 'typescript';

const __dirname = dirname(fileURLToPath(import.meta.url));
const dateUtilPath = resolve(__dirname, '../src/utils/date.ts');

async function loadDateUtils() {
  const source = readFileSync(dateUtilPath, 'utf8');
  const output = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ES2022,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText;
  const encoded = Buffer.from(output).toString('base64');
  return import(`data:text/javascript;base64,${encoded}`);
}

test('backend UTC timestamps render as Beijing clock time', async () => {
  const { formatDateTime } = await loadDateUtils();

  assert.equal(formatDateTime('2026-05-28T17:59:52'), '05/29 01:59');
  assert.equal(formatDateTime('2026-05-28T17:59:52Z'), '05/29 01:59');
  assert.equal(formatDateTime('2026-05-29T01:59:52+08:00'), '05/29 01:59');
});

test('intraday timestamps that are already Beijing local time stay on the same clock', async () => {
  const { formatChinaDateTime } = await loadDateUtils();

  assert.equal(formatChinaDateTime('2026-05-29T09:35:00'), '05/29 09:35');
});

test('trading dates are not timezone-shifted and todayISO uses the Beijing calendar', async () => {
  const { formatDate, todayISO } = await loadDateUtils();

  assert.equal(formatDate('2026-05-29'), '2026-05-29');
  assert.equal(todayISO(new Date('2026-01-01T17:00:00Z')), '2026-01-02');
});
