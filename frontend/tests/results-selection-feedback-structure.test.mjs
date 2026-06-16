import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = resolve(__dirname, '../src');

function read(path) {
  return readFileSync(resolve(root, path), 'utf8');
}

test('analysis result selection is visible in the table and toolbar', () => {
  const results = read('pages/results/ResultsPage.tsx');
  const table = read('pages/results/CandidateTable.tsx');
  const dataTable = read('design/DataTable.tsx');
  const tokens = read('design/tokens.css');

  assert.match(results, /selectedCode=\{selectedCandidate\?\.code\}/);
  assert.match(results, /当前：\{selectedCandidate\.code\} · \{selectedCandidate\.name\}/);
  assert.match(table, /selectedCode\?: string/);
  assert.match(table, /className=\{`chip-button \$\{isSelected \? 'active' : ''\}`\.trim\(\)\}/);
  assert.match(table, /aria-pressed=\{isSelected\}/);
  assert.match(table, /getRowClassName=\{\(candidate\) => candidate\.code === selectedCode \? 'selected-row' : undefined\}/);
  assert.match(table, /onRowClick=\{onSelect\}/);
  assert.match(dataTable, /getRowClassName\?: \(row: TData\) => string \| undefined/);
  assert.match(dataTable, /onRowClick\?: \(row: TData\) => void/);
  assert.match(dataTable, /className=\{getRowClassName\?\.\(row\.original\)\}/);
  assert.match(dataTable, /onClick=\{\(\) => onRowClick\?\.\(row\.original\)\}/);
  assert.match(tokens, /\.data-table tr\.selected-row td/);
});
