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

test('backtest result percentages use ratio percentage formatting', () => {
  const signal = read('pages/backtest/SignalEvaluation.tsx');
  const portfolio = read('pages/backtest/PortfolioBacktest.tsx');

  assert.match(signal, /formatRatioPercent/);
  assert.match(signal, /formatPercentStatus\(value: unknown\)[\s\S]*formatRatioPercent\(value\)/);
  assert.match(portfolio, /formatRatioPercent/);
  assert.match(portfolio, /formatPercentStatus\(value: unknown\)[\s\S]*formatRatioPercent\(value\)/);
});

test('portfolio payload and copy use simplified equity wording', () => {
  const portfolio = read('pages/backtest/PortfolioBacktest.tsx');

  assert.match(portfolio, /initial_equity:\s*Number\(initialEquity\)/);
  assert.match(portfolio, /初始模拟权益/);
  assert.doesNotMatch(portfolio, /initial_capital/);
});

test('portfolio controls and metrics match implemented backend summary fields', () => {
  const portfolio = read('pages/backtest/PortfolioBacktest.tsx');

  for (const unsupported of [
    'rebalance_frequency',
    'position_sizing',
    'max_position_pct',
    'entry_rule',
    'exit_rule',
    'limit_up_model',
    'limit_down_model',
    'limit_up_down_model',
  ]) {
    assert.doesNotMatch(portfolio, new RegExp(unsupported));
  }
  assert.doesNotMatch(portfolio, /summary\.annual_return/);
  assert.doesNotMatch(portfolio, /summary\.profit_factor/);
  assert.doesNotMatch(portfolio, /summary\.turnover[)}]/);
  assert.match(portfolio, /summary\.initial_equity/);
  assert.match(portfolio, /summary\.avg_trade_return/);
  assert.match(portfolio, /summary\.turnover_rate/);
});

test('candidate risk fallback renders ratio risk metrics as percentages', () => {
  const panel = read('pages/results/CandidateEvidencePanel.tsx');

  assert.match(panel, /formatRatioPercent\(candidate\.amplitude\)/);
});
