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
  for (const label of ['市场总览', 'Scanner', '分析结果', '盘中雷达', '观察池', '回测实验室', '数据中心', '任务状态']) {
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
  assert.match(read('api/intraday.ts'), /\/api\/intraday\/boards/);
  assert.match(read('api/backtest.ts'), /\/api\/backtest\/signal-evaluation/);
  assert.match(read('api/backtest.ts'), /\/api\/backtest\/portfolio/);
});

test('core pages cover the product-grade workbench requirements', () => {
  assert.match(read('pages/overview/OverviewPage.tsx'), /MarketHero/);
  assert.match(read('pages/overview/OverviewPage.tsx'), /SectorHeatmap/);
  assert.match(read('pages/overview/OverviewPage.tsx'), /DailyActionList/);
  assert.match(read('pages/results/CandidateEvidencePanel.tsx'), /为什么入选/);
  assert.match(read('pages/results/CandidateEvidencePanel.tsx'), /买点质量/);
  assert.match(read('pages/results/CandidateEvidencePanel.tsx'), /可操作动作/);
  assert.match(read('pages/intraday/IntradayPage.tsx'), /异动榜/);
  assert.match(read('pages/intraday/IntradayPage.tsx'), /低吸榜/);
  assert.match(read('pages/intraday/IntradayPage.tsx'), /风险榜/);
  assert.match(read('pages/watchlist/WatchlistPage.tsx'), /hypothesis/);
  assert.match(read('pages/watchlist/WatchlistPage.tsx'), /invalidation_rule/);
  assert.match(read('pages/backtest/BacktestPage.tsx'), /信号评估/);
  assert.match(read('pages/backtest/BacktestPage.tsx'), /组合回测/);
  assert.match(read('pages/data-map/DataMapPage.tsx'), /核心数据/);
  assert.match(read('pages/data-map/DataMapPage.tsx'), /市场上下文/);
  assert.match(read('pages/status/StatusPage.tsx'), /checkpoint/i);
});
