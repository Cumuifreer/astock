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
  assert.doesNotMatch(shell, /runStrategy/);
  assert.doesNotMatch(shell, /运行策略/);
  assert.match(shell, /showToast/);
  assert.match(shell, /任务已开始，可在任务状态查看进度/);
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
  assert.doesNotMatch(read('pages/overview/OverviewPage.tsx'), /DailyActionList/);
  assert.match(read('pages/overview/OverviewPage.tsx'), /市场简报/);
  assert.match(read('pages/results/CandidateEvidencePanel.tsx'), /AI 解读/);
  assert.doesNotMatch(read('pages/results/CandidateEvidencePanel.tsx'), /AI 解读 \/ 规则解释/);
  assert.match(read('pages/results/CandidateEvidencePanel.tsx'), /fallback_reason/);
  assert.doesNotMatch(read('pages/results/CandidateEvidencePanel.tsx'), /未配置模型，以下先按规则证据生成解释。/);
  assert.match(read('pages/results/CandidateEvidencePanel.tsx'), /入选理由/);
  assert.match(read('pages/results/CandidateEvidencePanel.tsx'), /风险提示/);
  assert.match(read('pages/results/CandidateEvidencePanel.tsx'), /可操作动作/);
  assert.match(read('pages/intraday/IntradayPage.tsx'), /异动榜/);
  assert.match(read('pages/intraday/IntradayPage.tsx'), /低吸榜/);
  assert.match(read('pages/intraday/IntradayPage.tsx'), /风险榜/);
  assert.doesNotMatch(read('pages/watchlist/WatchlistPage.tsx'), /卡片视图|表格视图/);
  assert.match(read('pages/watchlist/WatchlistPage.tsx'), /DataTable/);
  assert.match(read('pages/watchlist/WatchlistPage.tsx'), /删除观察项/);
  assert.match(read('pages/watchlist/WatchlistPage.tsx'), /T\+10/);
  assert.match(read('pages/watchlist/WatchlistPage.tsx'), /备注/);
  assert.doesNotMatch(read('pages/watchlist/WatchlistPage.tsx'), /Segmented|失效条件|review_status|观察中|误报|有效/);
  assert.match(read('pages/backtest/BacktestPage.tsx'), /信号评估/);
  assert.match(`${read('pages/backtest/BacktestPage.tsx')}\n${read('pages/backtest/PortfolioBacktest.tsx')}`, /组合回测|简化组合模拟/);
  assert.match(read('pages/backtest/SignalEvaluation.tsx'), /selectedRunId/);
  assert.match(read('pages/backtest/SignalEvaluation.tsx'), /run\?\.summary/);
  assert.doesNotMatch(read('pages/backtest/SignalEvaluation.tsx'), /2024-01-01/);
  assert.match(read('pages/data-map/DataMapPage.tsx'), /核心数据/);
  assert.match(read('pages/data-map/DataMapPage.tsx'), /市场上下文/);
  assert.match(read('pages/data-map/DataMapPage.tsx'), /本地股票仓/);
  assert.match(read('pages/data-map/DataMapPage.tsx'), /维护诊断/);
  assert.match(read('pages/status/StatusPage.tsx'), /查看维护信息/);
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
  assert.match(statusPage, /flowProgress/);
  assert.match(statusPage, /progressByTaskId/);
  assert.match(statusPage, /getTasks/);
  assert.match(statusPage, /effectiveActiveRows\.map/);
  assert.match(statusPage, /refetchInterval:\s*activeRefreshInterval/);
  assert.match(statusPage, /可能仍在运行/);
  assert.doesNotMatch(statusPage, /fallbackTasks\[0\]/);
  for (const label of ['系统状态', '任务队列', '定时计划', 'DeepSeek']) {
    assert.match(statusPage, new RegExp(label));
  }
  assert.match(statusPage, /schedule-status-strip/);
  assert.doesNotMatch(statusPage, /Metric label="最近失败"/);

  const metrics = read('utils/metrics.ts');
  assert.match(metrics, /isTerminalTaskStatus/);
  assert.match(metrics, /taskProgressValue/);
  assert.match(metrics, /dagProgress/);
});

test('scanner exposes a unified indicator matrix and panel-based combination bonus', () => {
  const matrix = read('pages/scanner/IndicatorMatrix.tsx');
  for (const label of ['指标配置矩阵', '基础股票池', '流动性与成交', '相对强弱', '题材与板块', '资金流向', '开关', '点击左侧开启']) {
    assert.match(matrix, new RegExp(label));
  }
  assert.doesNotMatch(matrix, /怎么用|尚未启用|开启后填写|影响|仅展示|移除/);
  assert.match(matrix, /indicator-card-grid/);
  assert.match(matrix, /已启用指标/);
  assert.match(matrix, /expandedGroups/);
  assert.match(matrix, /indicator-group-toggle/);
  assert.match(matrix, /formatChineseMoneyUnit/);
  assert.match(matrix, /money-unit-hint/);
  assert.match(matrix, /indicatorParameterKeys/);
  assert.doesNotMatch(matrix, /调整参数|高级参数|规则配置/);
  assert.match(matrix, /Switch/);

  const combination = read('pages/scanner/CombinationBonusPanel.tsx');
  assert.match(combination, /选择组合指标/);
  assert.match(combination, /添加组合加分/);
  assert.match(combination, /selectableResonanceRules/);
  assert.match(combination, /combo-choice-grid/);
  assert.match(combination, /combo-selected-chip/);
  assert.match(combination, /至少选择两个指标/);

  const strategyUtils = read('utils/strategy.ts');
  assert.match(strategyUtils, /includePaired/);
  assert.match(strategyUtils, /indicatorParameterKeys/);
  assert.match(strategyUtils, /indicatorParameterScope/);
});
