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

test('frontend is split into app, api, design, pages, hooks, and utils', () => {
  const requiredFiles = [
    'App.tsx',
    'app/App.tsx',
    'app/AppShell.tsx',
    'app/routes.tsx',
    'app/queryClient.ts',
    'api/client.ts',
    'api/market.ts',
    'api/strategy.ts',
    'api/data.ts',
    'api/intraday.ts',
    'api/backtest.ts',
    'api/watchlist.ts',
    'design/tokens.css',
    'design/Button.tsx',
    'design/Card.tsx',
    'design/Select.tsx',
    'design/Segmented.tsx',
    'design/Badge.tsx',
    'design/Progress.tsx',
    'design/DataTable.tsx',
    'design/Drawer.tsx',
    'design/Tabs.tsx',
    'design/Tooltip.tsx',
    'design/CheckTile.tsx',
    'design/EmptyState.tsx',
    'design/LoadingState.tsx',
    'pages/overview/OverviewPage.tsx',
    'pages/overview/MarketHero.tsx',
    'pages/overview/SectorHeatmap.tsx',
    'pages/overview/DailyActionList.tsx',
    'pages/scanner/StrategyPage.tsx',
    'pages/results/ResultsPage.tsx',
    'pages/results/CandidateEvidencePanel.tsx',
    'pages/intraday/IntradayPage.tsx',
    'pages/watchlist/WatchlistPage.tsx',
    'pages/backtest/BacktestPage.tsx',
    'pages/data-map/DataMapPage.tsx',
    'pages/status/StatusPage.tsx',
    'hooks/usePolling.ts',
    'hooks/useBootstrap.ts',
    'hooks/useStrategyDraft.ts',
    'utils/format.ts',
    'utils/date.ts',
    'utils/metrics.ts',
  ];
  for (const file of requiredFiles) {
    assert.equal(existsSync(src(file)), true, `${file} should exist`);
  }
});

test('App.tsx is a small bootstrap instead of a monolith', () => {
  const appSource = read('App.tsx');
  assert.match(appSource, /from ['"]\.\/app\/App['"]/);
  assert.ok(appSource.split('\n').length <= 40, 'src/App.tsx should stay as a tiny entry wrapper');
  assert.doesNotMatch(appSource, /function StrategyRuleWorkspace/);
  assert.doesNotMatch(appSource, /const navItems/);
});

test('required product dependencies are declared', () => {
  const packageJson = JSON.parse(readFileSync(resolve(__dirname, '../package.json'), 'utf8'));
  const deps = packageJson.dependencies || {};
  for (const name of [
    '@tanstack/react-query',
    '@tanstack/react-table',
    '@tanstack/react-virtual',
    'echarts',
    'echarts-for-react',
    'zustand',
    '@radix-ui/react-dialog',
    '@radix-ui/react-popover',
    '@radix-ui/react-select',
    '@radix-ui/react-tooltip',
    '@radix-ui/react-tabs',
    'clsx',
  ]) {
    assert.ok(deps[name], `${name} should be installed`);
  }
});

test('light design tokens and product navigation are present', () => {
  const tokens = read('design/tokens.css');
  assert.match(tokens, /--bg-page:\s*#f5f7fb/);
  assert.match(tokens, /--bg-panel:\s*#ffffff/);
  assert.match(tokens, /--accent:\s*#2563eb/);
  assert.doesNotMatch(tokens, /color-scheme:\s*dark/);

  const shell = read('app/AppShell.tsx');
  for (const label of ['市场总览', '策略选股', '分析结果', '盘中雷达', '观察池', '回测', '数据中心', '任务状态']) {
    assert.match(shell, new RegExp(label));
  }
  assert.match(shell, /syncToday/);
  assert.match(shell, /runStrategy/);
});

test('new API layer exposes market, intraday boards, checkpoints, and backtest endpoints', () => {
  assert.match(read('api/market.ts'), /\/api\/market\/overview/);
  assert.match(read('api/market.ts'), /\/api\/market\/sector-heatmap/);
  assert.match(read('api/data.ts'), /\/api\/tasks\/sync-today/);
  assert.match(read('api/data.ts'), /\/api\/tasks\/.*\/checkpoints/);
  assert.match(read('api/data.ts'), /\/api\/tasks\/.*\/dag/);
  assert.match(read('api/data.ts'), /\/api\/tasks\?/);
  assert.match(read('api/data.ts'), /\/api\/data\/stocks/);
  assert.match(read('api/data.ts'), /\/api\/data\/source-diagnostics/);
  assert.match(read('api/intraday.ts'), /\/api\/intraday\/boards/);
  assert.match(read('api/backtest.ts'), /\/api\/backtest\/signal-evaluation/);
  assert.match(read('api/backtest.ts'), /\/api\/backtest\/portfolio/);
});

test('core pages cover the product-grade workbench requirements', () => {
  assert.match(read('pages/overview/OverviewPage.tsx'), /MarketHero/);
  assert.match(read('pages/overview/OverviewPage.tsx'), /SectorHeatmap/);
  assert.match(read('pages/overview/OverviewPage.tsx'), /DailyActionList/);
  assert.match(read('pages/overview/OverviewPage.tsx'), /市场简报/);
  assert.match(read('pages/results/CandidateEvidencePanel.tsx'), /为什么入选/);
  assert.match(read('pages/results/CandidateEvidencePanel.tsx'), /买点质量/);
  assert.match(read('pages/results/CandidateEvidencePanel.tsx'), /可操作动作/);
  assert.match(read('pages/intraday/IntradayPage.tsx'), /异动榜/);
  assert.match(read('pages/intraday/IntradayPage.tsx'), /低吸榜/);
  assert.match(read('pages/intraday/IntradayPage.tsx'), /风险榜/);
  assert.match(read('pages/watchlist/WatchlistPage.tsx'), /卡片视图/);
  assert.match(read('pages/watchlist/WatchlistPage.tsx'), /表格视图/);
  assert.match(read('pages/watchlist/WatchlistPage.tsx'), /确认删除这个观察项/);
  assert.match(read('pages/backtest/BacktestPage.tsx'), /信号评估/);
  assert.match(read('pages/backtest/BacktestPage.tsx'), /组合回测/);
  assert.match(read('pages/backtest/SignalEvaluation.tsx'), /mutation\.data\?\.run_id/);
  assert.match(read('pages/backtest/SignalEvaluation.tsx'), /run\?\.summary/);
  assert.doesNotMatch(read('pages/backtest/SignalEvaluation.tsx'), /2024-01-01/);
  assert.match(read('pages/data-map/DataMapPage.tsx'), /核心数据/);
  assert.match(read('pages/data-map/DataMapPage.tsx'), /市场上下文/);
  assert.match(read('pages/data-map/DataMapPage.tsx'), /本地股票仓/);
  assert.match(read('pages/data-map/DataMapPage.tsx'), /数据源诊断/);
  assert.match(read('pages/status/StatusPage.tsx'), /开发者详情/);
});

test('task progress and topbar popover avoid false running states', () => {
  const button = read('design/Button.tsx');
  assert.match(button, /forwardRef/);
  assert.match(button, /ref=\{ref\}/);

  const progress = read('design/Progress.tsx');
  assert.match(progress, /state\?:/);
  assert.match(progress, /terminalProgressStates/);
  assert.match(progress, /indeterminateProgressStates/);
  assert.match(progress, /failed/);

  const queue = read('pages/status/TaskQueue.tsx');
  assert.match(queue, /taskProgressValue/);
  assert.match(queue, /state=\{task\.status\}/);

  const statusPage = read('pages/status/StatusPage.tsx');
  assert.match(statusPage, /dagProgress/);
  assert.match(statusPage, /progressByTaskId/);
  assert.match(statusPage, /getTasks/);
  for (const label of ['当前运行', '等待队列', '最近完成', '失败任务']) {
    assert.match(statusPage, new RegExp(label));
  }

  const metrics = read('utils/metrics.ts');
  assert.match(metrics, /isTerminalTaskStatus/);
  assert.match(metrics, /taskProgressValue/);
  assert.match(metrics, /dagProgress/);
});

test('scanner exposes editable universe, built-in indicators, and explicit resonance selection', () => {
  const universe = read('pages/scanner/UniversePanel.tsx');
  assert.match(universe, /onPatchConfig/);
  for (const key of [
    'min_price',
    'min_amount',
    'min_float_market_value',
    'max_float_market_value',
    'min_turnover',
    'max_turnover',
    'min_rps20',
    'min_rps60',
    'min_rps120',
    'candidate_limit',
    'sort_by',
    'include_bj',
    'exclude_star_board',
  ]) {
    assert.match(universe, new RegExp(key));
  }

  const picker = read('pages/scanner/FactorPicker.tsx');
  for (const label of ['补充规则', '内置参数', '全部指标', '显示更多', '会与已有参数叠加生效']) {
    assert.match(picker, new RegExp(label));
  }
  assert.match(picker, /paired_strategy_ids/);
  assert.match(picker, /编辑参数/);
  assert.match(picker, /转为显式规则/);
  assert.doesNotMatch(picker, /slice\(0,\s*24\)/);

  const canvas = read('pages/scanner/RuleCanvas.tsx');
  assert.doesNotMatch(canvas, /slice\(0,\s*2\)/);
  assert.match(canvas, /selectedResonanceRuleIds/);
  assert.match(canvas, /platform_lookback_days/);
  assert.match(canvas, /trend_macd_fast/);
  assert.match(canvas, /onPatchConfig/);

  const strategyUtils = read('utils/strategy.ts');
  assert.match(strategyUtils, /includePaired/);
  assert.match(strategyUtils, /indicatorParameterKeys/);
  assert.match(strategyUtils, /indicatorParameterScope/);
});
