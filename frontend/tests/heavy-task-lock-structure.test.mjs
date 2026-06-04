import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import test from 'node:test';

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = resolve(__dirname, '../src');

function src(path) {
  return resolve(root, path);
}

function read(path) {
  return readFileSync(src(path), 'utf8');
}

test('heavy task actions share an active-task lock', () => {
  assert.equal(existsSync(src('hooks/useHeavyTaskLock.ts')), true, 'useHeavyTaskLock hook should exist');

  const hook = read('hooks/useHeavyTaskLock.ts');
  for (const kind of ['update', 'analyze', 'backtest', 'intraday', 'intraday_strategy_tracking']) {
    assert.match(hook, new RegExp(kind));
  }
  assert.match(hook, /queryKeys\.tasks\.active\(\)/);
  assert.match(hook, /getTasks\(\{ status: 'queued,running', limit: 50 \}\)/);

  const shell = read('app/AppShell.tsx');
  const scanner = read('pages/scanner/StrategyPage.tsx');
  const intraday = read('pages/intraday/IntradayPage.tsx');

  for (const source of [shell, scanner, intraday]) {
    assert.match(source, /useHeavyTaskLock/);
  }
  assert.match(shell, /taskLock\.locked \|\| busy/);
  assert.match(scanner, /taskLock\.locked \|\| runMutation\.isPending/);
  assert.match(intraday, /taskLock\.locked \|\| runTrackingMutation\.isPending/);
});
