import assert from 'node:assert/strict';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join, resolve } from 'node:path';
import test from 'node:test';

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = resolve(__dirname, '../src');

function read(path) {
  return readFileSync(resolve(root, path), 'utf8');
}

function files(dir = root) {
  return readdirSync(dir).flatMap((entry) => {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) return files(path);
    return path.endsWith('.ts') || path.endsWith('.tsx') ? [path] : [];
  });
}

function allSource() {
  return files().map((path) => [path.replace(`${root}/`, ''), readFileSync(path, 'utf8')]);
}

test('v2 forbids browser-native alert confirm and prompt', () => {
  for (const [path, source] of allSource()) {
    assert.doesNotMatch(source, /window\.(alert|confirm|prompt)/, `${path} must use product dialogs instead of browser dialogs`);
  }
});

test('ordinary pages do not expose internal product language', () => {
  const forbidden = /Market Pulse|Rule Canvas|DAG|checkpoint|developer|开发者详情|Tushare 增强|系统策略|默认策略|技术明细|调试/;
  for (const [path, source] of allSource()) {
    if (!/^(app|pages|design)\//.test(path)) continue;
    assert.doesNotMatch(source, forbidden, `${path} exposes v2-forbidden wording`);
  }
});

test('overview removes daily action list and opens brief sources by default', () => {
  const overview = read('pages/overview/OverviewPage.tsx');
  assert.doesNotMatch(overview, /DailyActionList/);
  assert.match(overview, /市场简报/);
  assert.match(overview, /重新生成简报/);
  assert.match(overview, /查看引用来源/);
  assert.match(overview, /<details[^>]+open/);
});

test('strategy page uses a default full indicator matrix instead of factor picker and canvas section card', () => {
  const strategy = read('pages/scanner/StrategyPage.tsx');
  assert.match(strategy, /IndicatorMatrix/);
  assert.doesNotMatch(strategy, /FactorPicker/);
  assert.doesNotMatch(strategy, /画布分区/);

  const matrix = read('pages/scanner/IndicatorMatrix.tsx');
  for (const label of ['基础股票池', '流动性与成交', '相对强弱', '平台与突破', '题材与板块', '资金流向', '涨停与事件', '筹码成本', '风险过滤', '候选展示']) {
    assert.match(matrix, new RegExp(label));
  }
  assert.match(matrix, /Switch/);
  assert.match(matrix, /开关/);
  assert.match(matrix, /点击左侧开启/);
  assert.doesNotMatch(strategy, /RuleCanvas|UniversePanel|保存为默认|系统策略|默认策略/);
  assert.doesNotMatch(matrix, /调整参数|高级参数|规则配置|怎么用|尚未启用|开启后填写|影响|仅展示|移除/);
  assert.match(matrix, /indicator-card-grid/);
  assert.match(matrix, /已启用指标/);
});

test('analysis results display strategy names and auto-load candidate explanation', () => {
  const results = read('pages/results/ResultsPage.tsx');
  assert.match(results, /activeStrategyName|strategyLabel/);
  assert.match(results, /strategy_name/);
  assert.doesNotMatch(results, /slice\(0,\s*12\)/);
  assert.doesNotMatch(results, /analysis-/);

  const panel = read('pages/results/CandidateEvidencePanel.tsx');
  assert.match(panel, /AI 解读/);
  assert.match(panel, /fallback_reason/);
  assert.doesNotMatch(panel, /未配置模型，以下先按规则证据生成解释。/);
  assert.doesNotMatch(panel, /AI 解读 \/ 规则解释/);
  assert.match(panel, /useQuery/);
  assert.match(panel, /getCandidateAiSummary/);
  assert.doesNotMatch(panel, /技术明细|Dialog|AI 解读暂未启用/);
  assert.doesNotMatch(panel, /开发者详情/);
  assert.doesNotMatch(panel, /window\.alert/);
});

test('watchlist uses dialogs and DataTable for management', () => {
  const watchlist = read('pages/watchlist/WatchlistPage.tsx');
  const dataTable = read('design/DataTable.tsx');
  assert.match(watchlist, /ConfirmDialog/);
  assert.match(watchlist, /EditDialog/);
  assert.match(watchlist, /DataTable/);
  assert.match(watchlist, /header:\s*'T\+10'/);
  assert.doesNotMatch(watchlist, /header:\s*'备注'/);
  assert.match(watchlist, /renderSubRow/);
  assert.match(watchlist, /watchlist-note-row/);
  assert.match(watchlist, /watchlist-price-cell/);
  assert.match(watchlist, /currentPriceTone/);
  assert.match(watchlist, /item\.note/);
  assert.match(dataTable, /renderSubRow/);
  assert.doesNotMatch(watchlist, /批量标记有效|批量标记误报|Segmented|失效条件|review_status|观察中|误报|有效/);
  assert.match(watchlist, /批量删除/);
  assert.doesNotMatch(watchlist, /<table/);
  assert.doesNotMatch(watchlist, /value:\s*'归档'/);
  assert.doesNotMatch(watchlist, /已归档|卡片视图|表格视图|HypothesisCard/);
  assert.match(watchlist, /header:\s*'来源'/);
});

test('intraday radar has a real timeline drawer and page-level missing-data notices', () => {
  const board = read('pages/intraday/IntradayBoard.tsx');
  const page = read('pages/intraday/IntradayPage.tsx');
  assert.match(page, /Drawer/);
  assert.match(page, /getIntradayTimeline/);
  assert.match(page, /已完成 1 次采样/);
  assert.match(page, /题材联动数据未同步/);
  assert.doesNotMatch(board, /window\.location\.hash/);
});

test('backtest page exposes strategy selection parameters results and queue tracking', () => {
  const backtest = `${read('pages/backtest/BacktestPage.tsx')}\n${read('pages/backtest/SignalEvaluation.tsx')}\n${read('pages/backtest/PortfolioBacktest.tsx')}`;
  for (const label of ['回测策略', '调仓频率', '候选数量', '持仓数量', '交易成本', '滑点', '资金曲线', '交易明细', '查看任务状态']) {
    assert.match(backtest, new RegExp(label));
  }
  for (const className of ['backtest-header-grid', 'backtest-tabs', 'backtest-panel', 'backtest-form-grid', 'backtest-results-grid', 'backtest-placeholder-grid']) {
    assert.match(backtest, new RegExp(className));
  }
  assert.match(backtest, /回测任务已开始，可在任务状态查看进度/);
  assert.match(backtest, /window\.location\.hash = '#status'/);
});

test('status page defaults to a concise user view with hidden maintenance mode', () => {
  const status = read('pages/status/StatusPage.tsx');
  for (const label of ['系统状态', '任务队列', '定时计划', 'DeepSeek', '查看维护信息', '运行中任务', '可能仍在运行']) {
    assert.match(status, new RegExp(label));
  }
  assert.match(status, /refetchInterval:\s*activeRefreshInterval/);
  assert.match(status, /effectiveActiveRows\.map/);
  assert.doesNotMatch(status, /fallbackTasks\[0\]/);
  assert.match(status, /schedule-status-strip/);
  assert.doesNotMatch(status, /Metric label="最近失败"/);
  assert.doesNotMatch(status, /developer-details/);
  assert.doesNotMatch(status, /开发者详情/);
});
