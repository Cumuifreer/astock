import { Fragment, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { createRoot } from 'react-dom/client';
import {
  Activity,
  BarChart3,
  CandlestickChart,
  Copy,
  Database,
  Gauge,
  History,
  Layers3,
  LineChart,
  Play,
  Plus,
  RefreshCw,
  RotateCcw,
  Save,
  Settings2,
  ShieldAlert,
  SlidersHorizontal,
  Star,
  Trash2,
  Workflow,
  X,
} from 'lucide-react';

import { api } from './api';
import type {
  Bootstrap,
  BacktestResult,
  BacktestRun,
  BacktestSignal,
  BriefArticle,
  Candidate,
  CandidateBundle,
  Capability,
  BriefItem,
  DailyBrief,
  IndicatorDefinition,
  IndicatorLibrary,
  IndicatorRule,
  IntradayRadarCandidate,
  IntradayRadarConfig,
  IntradayRadarResult,
  IntradayTimeline,
  AnalysisReportGroup,
  AnalysisReportSummary,
  FunnelStep,
  RuntimeHealth,
  RuntimeSlot,
  RuleAction,
  RuleOperator,
  SignalModeField,
  SignalModeTemplate,
  StrategyConfig,
  StrategyInteraction,
  StrategyPreset,
  StrategyRule,
  StrategyRuleCondition,
  StrategyVersion,
  TaskRun,
  WatchlistBatch,
  WatchlistItem,
  WatchlistResult,
} from './types';
import './styles.css';

type Tab = 'overview' | 'warehouse' | 'indicators' | 'strategy' | 'intraday' | 'results' | 'watchlist' | 'backtest' | 'map' | 'status';
type UpdateMode = 'full' | 'daily_light';
type CandidateSortKey =
  | 'none'
  | 'signal_score'
  | 'score_position'
  | 'score_volume'
  | 'score_pattern'
  | 'score_trend'
  | 'score_theme'
  | 'score_freshness'
  | 'score_risk'
  | 'amount'
  | 'rps20'
  | 'pct_chg';

const candidateSortOptions: Array<{ value: CandidateSortKey; label: string }> = [
  { value: 'none', label: '不启用' },
  { value: 'signal_score', label: '总分' },
  { value: 'score_position', label: '位置分' },
  { value: 'score_volume', label: '量能分' },
  { value: 'score_pattern', label: '形态分' },
  { value: 'score_trend', label: '趋势分' },
  { value: 'score_theme', label: '题材分' },
  { value: 'score_freshness', label: '新鲜度' },
  { value: 'score_risk', label: '风险扣分' },
  { value: 'amount', label: '成交额' },
  { value: 'rps20', label: 'RPS20' },
  { value: 'pct_chg', label: '涨跌幅' },
];

const navItems: Array<{ id: Tab; label: string; icon: ReactNode }> = [
  { id: 'overview', label: '总览', icon: <Gauge size={17} /> },
  { id: 'warehouse', label: '数据仓库', icon: <Database size={17} /> },
  { id: 'indicators', label: '指标库', icon: <LineChart size={17} /> },
  { id: 'strategy', label: '策略', icon: <SlidersHorizontal size={17} /> },
  { id: 'intraday', label: '盘中雷达', icon: <Activity size={17} /> },
  { id: 'results', label: '分析结果', icon: <BarChart3 size={17} /> },
  { id: 'watchlist', label: '观察池', icon: <Star size={17} /> },
  { id: 'backtest', label: '回测', icon: <History size={17} /> },
  { id: 'map', label: '数据地图', icon: <Layers3 size={17} /> },
  { id: 'status', label: '运行状态', icon: <Workflow size={17} /> },
];

const signalModes: Array<{ id: string; label: string; sub: string }> = [
  { id: 'breakout_or_pullback', label: '突破回踩', sub: '双形态' },
  { id: 'platform_breakout', label: '平台突破', sub: '压缩放量' },
  { id: 'platform_setup', label: '平台临界', sub: '贴近上沿' },
  { id: 'trend_resonance', label: '趋势共振', sub: 'EMA/MACD/KDJ' },
];

const analysisModes: Array<{ id: string; label: string; sub: string }> = [
  { id: 'strict', label: '严格筛选', sub: '逐层淘汰，条件必须同时满足' },
  { id: 'score', label: '综合评分', sub: '基础合格后按信号强弱排序' },
];

const ruleActionMeta: Record<RuleAction, { label: string; verb: string; note: string }> = {
  filter: { label: '筛选', verb: '不达标剔除', note: '用于硬条件' },
  score: { label: '加权', verb: '达标加权', note: '用于排序强化' },
  risk: { label: '扣风险', verb: '达标扣分', note: '用于过热或异常' },
  display: { label: '只展示', verb: '不参与运算', note: '用于看板观察' },
};

const interactionMultiplierOptions = [
  { value: 1.05, label: '轻微增强 x1.05' },
  { value: 1.1, label: '标准增强 x1.10' },
  { value: 1.2, label: '强确认 x1.20' },
  { value: 1.35, label: '强共振 x1.35' },
  { value: 0.9, label: '轻微降权 x0.90' },
  { value: 0.8, label: '风险降权 x0.80' },
];

const ruleOperatorMeta: Record<RuleOperator, { label: string; summary: string }> = {
  gte: { label: '≥', summary: '高于或等于' },
  lte: { label: '≤', summary: '低于或等于' },
  gt: { label: '>', summary: '高于' },
  lt: { label: '<', summary: '低于' },
  between: { label: '介于', summary: '介于' },
  eq: { label: '=', summary: '等于' },
  neq: { label: '≠', summary: '不等于' },
  is_true: { label: '为真', summary: '为真' },
  recent: { label: '最近', summary: '最近出现' },
};

const missingPolicyOptions = [
  { id: 'neutral', label: '缺失中性' },
  { id: 'keep', label: '缺失保留' },
  { id: 'skip', label: '缺失剔除' },
];

const reviewStatuses = ['观察中', '已验证', '已放弃', '已错过'];
const batchReviewStatuses = ['观察中', '有效', '一般', '误报', '已归档'];

function App() {
  const [tab, setTab] = useState<Tab>('overview');
  const [bootstrap, setBootstrap] = useState<Bootstrap | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [strategyName, setStrategyName] = useState('我的策略');
  const [selectedPresetId, setSelectedPresetId] = useState<string | null>(null);
  const [strategy, setStrategy] = useState<StrategyConfig | null>(null);

  function applyPreset(preset: StrategyPreset) {
    setSelectedPresetId(preset.id);
    setStrategyName(preset.name);
    setStrategy(cleanPlatformBreakoutModes(preset.config));
  }

  async function loadAndSelect(presetId?: string | null) {
    const next = await api.bootstrap();
    setBootstrap(next);
    if (presetId !== undefined) {
      const fallback =
        next.strategies.find((preset) => preset.id === presetId) ||
        next.strategies.find((preset) => preset.is_default && !preset.is_system) ||
        next.strategies.find((preset) => !preset.is_system) ||
        next.strategies.find((preset) => preset.is_default) ||
        next.strategies[0];
      if (fallback) applyPreset(fallback);
    }
  }

  async function load(silent = false) {
    try {
      if (!silent) setLoading(true);
      const next = await api.bootstrap();
      setBootstrap(next);
      if (!strategy) {
        setStrategy(cleanPlatformBreakoutModes(next.default_strategy));
        const defaultPreset = next.strategies.find((preset) => preset.is_default);
        setSelectedPresetId(defaultPreset?.id || null);
        setStrategyName(defaultPreset?.name || '我的策略');
      }
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  const updateRunning = isTaskActive(bootstrap?.update_status);
  const analyzeRunning = isTaskActive(bootstrap?.analyze_status);
  const backtestRunning = isTaskActive(bootstrap?.backtest_status);
  const intradayRunning = isTaskActive(bootstrap?.intraday_status);
  const briefRunning = isTaskActive(bootstrap?.brief_status);

  useEffect(() => {
    if (!updateRunning && !analyzeRunning && !backtestRunning && !intradayRunning && !briefRunning) return;
    const timer = window.setInterval(() => void load(true), 2200);
    return () => window.clearInterval(timer);
  }, [updateRunning, analyzeRunning, backtestRunning, intradayRunning, briefRunning]);

  async function startUpdate(force = false, mode: UpdateMode = 'full') {
    try {
      await api.startUpdate({ force, mode });
      setNotice(mode === 'daily_light' ? '轻量日更已开始' : '数据更新已开始');
      await load(true);
      setTab('status');
    } catch (err) {
      setError(err instanceof Error ? err.message : '无法启动更新');
    }
  }

  async function startCapabilityBackfill(capability: string) {
    try {
      await api.startUpdate({ mode: 'capability_backfill', capability });
      setNotice(`${capability}补齐已开始`);
      await load(true);
      setTab('status');
    } catch (err) {
      setError(err instanceof Error ? err.message : '无法启动补齐');
      throw err;
    }
  }

  async function startAnalyze(current = strategy) {
    if (!current) return;
    try {
      await api.startAnalyze(cleanPlatformBreakoutModes(current));
      setNotice('分析已开始');
      await load(true);
      setTab('status');
    } catch (err) {
      setError(err instanceof Error ? err.message : '无法启动分析');
    }
  }

  async function startBacktest(options: Record<string, unknown>, config = strategy) {
    if (!config) return;
    try {
      await api.startBacktest({ ...options, config: cleanPlatformBreakoutModes(config) });
      setNotice('回测已开始');
      await load(true);
      setTab('backtest');
    } catch (err) {
      setError(err instanceof Error ? err.message : '无法启动回测');
    }
  }

  async function startIntradaySnapshot() {
    try {
      await api.startIntradaySnapshot({});
      setNotice('盘中采样已开始');
      await load(true);
      setTab('intraday');
    } catch (err) {
      setError(err instanceof Error ? err.message : '无法启动盘中采样');
    }
  }

  async function saveIntradayConfig(config: IntradayRadarConfig) {
    try {
      await api.saveIntradayConfig(config);
      setNotice('盘中雷达设置已保存');
      await load(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : '盘中雷达设置保存失败');
    }
  }

  async function addToWatchlist(payload: Record<string, unknown>) {
    try {
      await api.addToWatchlist(payload);
      setNotice('已加入观察池');
      await load(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : '加入观察池失败');
    }
  }

  async function saveStrategy(setDefault = false) {
    if (!strategy) return;
    try {
      const payload = {
        id: selectedPresetId?.startsWith('custom-') ? selectedPresetId : undefined,
        name: strategyName,
        config: cleanPlatformBreakoutModes(strategy),
        set_default: setDefault,
      };
      const result = await api.saveStrategy(payload);
      applyPreset(result.preset);
      setNotice(setDefault ? '策略已保存并设为默认' : '策略已保存');
      await load(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : '保存策略失败');
    }
  }

  async function saveAndRun() {
    await saveStrategy(false);
    await startAnalyze(strategy);
  }

  async function createSignalMode(name: string) {
    try {
      const result = await api.createSignalMode(name);
      setNotice('信号模式已创建');
      await load(true);
      return result.mode;
    } catch (err) {
      setError(err instanceof Error ? err.message : '创建信号模式失败');
      throw err;
    }
  }

  async function saveSignalMode(mode: SignalModeTemplate) {
    try {
      const result = await api.saveSignalMode(mode);
      setNotice('信号模式已保存');
      await load(true);
      return result.mode;
    } catch (err) {
      setError(err instanceof Error ? err.message : '保存信号模式失败');
      throw err;
    }
  }

  async function duplicateSignalMode(id: string) {
    try {
      const result = await api.duplicateSignalMode(id);
      setNotice('信号模式已复制');
      await load(true);
      return result.mode;
    } catch (err) {
      setError(err instanceof Error ? err.message : '复制信号模式失败');
      throw err;
    }
  }

  async function deleteSignalMode(id: string) {
    try {
      await api.deleteSignalMode(id);
      setNotice('信号模式已删除');
      await load(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : '删除信号模式失败');
      throw err;
    }
  }

  const page = useMemo(() => {
    if (!bootstrap || !strategy) return null;
    if (tab === 'overview') {
      return (
        <Overview
          bootstrap={bootstrap}
          startUpdate={startUpdate}
          startAnalyze={() => startAnalyze(strategy)}
        />
      );
    }
    if (tab === 'warehouse') return <Warehouse />;
    if (tab === 'indicators') {
      return (
        <IndicatorLibraryPage
          library={bootstrap.indicator_library}
        />
      );
    }
    if (tab === 'strategy') {
      return (
        <StrategyPanel
          indicatorLibrary={bootstrap.indicator_library}
          presets={bootstrap.strategies}
          selectedPresetId={selectedPresetId}
          strategy={strategy}
          strategyName={strategyName}
          setStrategy={setStrategy}
          setStrategyName={setStrategyName}
          selectPreset={(preset) => {
            applyPreset(preset);
          }}
          saveStrategy={saveStrategy}
          saveAndRun={saveAndRun}
          createMode={createSignalMode}
          saveMode={saveSignalMode}
          duplicateMode={duplicateSignalMode}
          deleteMode={deleteSignalMode}
          duplicate={async () => {
            if (!selectedPresetId) return;
            const result = await api.duplicateStrategy(selectedPresetId);
            applyPreset(result.preset);
            setNotice('策略已复制');
            await load(true);
          }}
          createBlank={async () => {
            const seedConfig =
              bootstrap.strategies.find((preset) => preset.id === 'system-momentum')?.config ||
              bootstrap.default_strategy;
            const result = await api.saveStrategy({
              name: '未命名策略',
              config: seedConfig,
              set_default: false,
            });
            applyPreset(result.preset);
            setNotice('新策略已创建');
            await load(true);
          }}
          remove={async () => {
            if (!selectedPresetId) return;
            await api.deleteStrategy(selectedPresetId);
            setNotice('策略已删除');
            await loadAndSelect(null);
          }}
          reset={async () => {
            await api.resetSystemStrategies();
            setNotice('系统预设已恢复');
            await load(true);
          }}
        />
      );
    }
    if (tab === 'intraday') {
      return (
        <IntradayRadarPage
          result={bootstrap.intraday}
          task={bootstrap.intraday_status}
          runtime={bootstrap.runtime_health}
          startSample={startIntradaySnapshot}
          saveConfig={saveIntradayConfig}
          addToWatchlist={addToWatchlist}
        />
      );
    }
    if (tab === 'results') {
      return (
        <Results
          candidates={bootstrap.candidates.rows}
          funnel={bootstrap.candidates.funnel}
          zeroReason={bootstrap.candidates.zero_reason}
          runId={bootstrap.candidates.run_id}
          addToWatchlist={addToWatchlist}
        />
      );
    }
    if (tab === 'watchlist') {
      return <WatchlistPage result={bootstrap.watchlist} reload={() => load(true)} />;
    }
    if (tab === 'backtest') {
      return (
        <BacktestPage
          result={bootstrap.backtest}
          task={bootstrap.backtest_status}
          strategy={strategy}
          presets={bootstrap.strategies}
          startBacktest={startBacktest}
        />
      );
    }
    if (tab === 'map') {
      return (
        <DataMap
          capabilities={bootstrap.capabilities}
          afterProbe={() => load(true)}
          backfillCapability={startCapabilityBackfill}
          backfillDisabled={updateRunning}
        />
      );
    }
    return <StatusBoard runtime={bootstrap.runtime_health} update={bootstrap.update_status} analyze={bootstrap.analyze_status} backtest={bootstrap.backtest_status} intraday={bootstrap.intraday_status} brief={bootstrap.brief_status} latestAnalysis={bootstrap.latest_analysis} />;
  }, [bootstrap, tab, strategy, strategyName, selectedPresetId, updateRunning]);

  return (
    <main className="shell">
      <aside className="rail">
        <div className="brand">
          <CandlestickChart size={26} />
          <div>
            <strong>A-Share Signal</strong>
            <span>技术信号工作台</span>
          </div>
        </div>
        <nav>
          {navItems.map((item) => (
            <button
              key={item.id}
              className={tab === item.id ? 'active' : ''}
              onClick={() => setTab(item.id)}
              title={item.label}
            >
              {item.icon}
              <span>{item.label}</span>
            </button>
          ))}
        </nav>
        <div className="rail-footer">
          <StatusDot task={bootstrap?.update_status} label="更新" />
          <StatusDot task={bootstrap?.analyze_status} label="分析" />
          <StatusDot task={bootstrap?.backtest_status} label="回测" />
          <StatusDot task={bootstrap?.intraday_status} label="雷达" />
          <StatusDot task={bootstrap?.brief_status} label="简报" />
        </div>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div>
            <span className="eyebrow">PRIVATE A-SHARE LAB</span>
            <h1>{navItems.find((item) => item.id === tab)?.label}</h1>
          </div>
          <div className="quick-actions">
            <button className="icon-button" onClick={() => load(true)} title="刷新状态">
              <RefreshCw size={16} />
            </button>
            <button className="primary" disabled={updateRunning} onClick={() => startUpdate(false, 'daily_light')}>
              <RefreshCw size={16} />
              轻量日更
            </button>
            <button className="ghost" disabled={updateRunning} onClick={() => startUpdate(false)}>
              更新数据
            </button>
            <button className="ghost" disabled={updateRunning || analyzeRunning || backtestRunning || intradayRunning} onClick={startIntradaySnapshot}>
              雷达采样
            </button>
            <button className="primary lime" disabled={analyzeRunning || !strategy} onClick={() => startAnalyze(strategy)}>
              <Play size={16} />
              运行分析
            </button>
          </div>
        </header>

        {error && <Banner tone="danger" text={error} onClose={() => setError(null)} />}
        {notice && <Banner tone="good" text={notice} onClose={() => setNotice(null)} />}
        {loading && !bootstrap ? <InitialLoading /> : page}
      </section>
    </main>
  );
}

function cleanPlatformBreakoutModes(config: StrategyConfig): StrategyConfig {
  const normalized = {
    ...config,
    signal_mode: ['breakout', 'pullback'].includes(config.signal_mode) ? 'breakout_or_pullback' : config.signal_mode,
    breakout_pullback_direction: config.signal_mode === 'breakout'
      ? 'breakout'
      : config.signal_mode === 'pullback'
        ? 'pullback'
        : config.breakout_pullback_direction || 'both',
  };
  if (normalized.signal_mode !== 'platform_breakout') return normalized;
  return {
    ...normalized,
    platform_breakout_clearance_mode: 'must',
    platform_breakout_max_clearance_mode: 'score',
    platform_breakout_first_mode: 'must',
    platform_bullish_ratio_mode: 'must',
    platform_bull_volume_advantage_mode: 'must',
    platform_breakout_volume_ratio_mode: 'must',
    platform_breakout_pct_chg_mode: 'must',
    platform_breakout_bullish_mode: 'must',
    platform_body_strength_mode: 'must',
    platform_ma_bullish_mode: 'score',
    platform_ma_rising_mode: 'score',
    platform_macd_filter_mode: 'score',
  };
}

function Overview({
  bootstrap,
  startUpdate,
  startAnalyze,
}: {
  bootstrap: Bootstrap;
  startUpdate: (force?: boolean, mode?: UpdateMode) => void;
  startAnalyze: () => void;
}) {
  const overview = bootstrap.overview;
  const candidateCount = Number(overview.latest_analysis?.summary?.candidate_count ?? bootstrap.candidates.rows.length ?? 0);
  return (
    <div className="page-stack">
      <section className="metric-grid">
        <MetricCard label="股票池" value={formatInt(overview.stock_count)} sub="真实 A 股" icon={<Database size={18} />} />
        <MetricCard label="历史 K 线" value={formatInt(overview.history_rows)} sub={overview.latest_history_date || '等待更新'} icon={<LineChart size={18} />} />
        <MetricCard label="快照" value={formatInt(overview.snapshot_rows)} sub={overview.latest_snapshot_date || '等待更新'} icon={<Activity size={18} />} />
        <MetricCard label="候选" value={formatInt(candidateCount)} sub={overview.latest_analysis?.finished_at || '尚未分析'} icon={<Star size={18} />} />
      </section>
      <HealthHints bootstrap={bootstrap} />

      <section className="split">
        <div className="panel">
          <PanelTitle icon={<Workflow size={18} />} title="当前节奏" />
          <TaskStrip task={bootstrap.update_status} fallback="数据更新尚未启动" />
          <TaskStrip task={bootstrap.analyze_status} fallback="分析尚未启动" />
          <div className="action-row">
            <button onClick={() => startUpdate(false, 'daily_light')} className="primary">
              <RefreshCw size={16} />
              轻量日更
            </button>
            <button onClick={() => startUpdate(false)} className="ghost">
              更新数据
            </button>
            <button onClick={() => startUpdate(true)} className="ghost">
              强制刷新
            </button>
            <button onClick={startAnalyze} className="primary lime">
              <Play size={16} />
              分析
            </button>
          </div>
        </div>

        <div className="panel">
          <PanelTitle icon={<ShieldAlert size={18} />} title="数据覆盖" />
          <div className="coverage-line">
            <span>换手率</span>
            <strong>{overview.turnover_coverage.percent}%</strong>
          </div>
          <Progress value={overview.turnover_coverage.percent} />
          <div className="capability-list">
            {bootstrap.capabilities.slice(0, 5).map((capability) => (
              <div key={capability.capability} className="capability-row">
                <span>{capability.capability}</span>
                <b>{formatInt(capability.coverage_count)}</b>
              </div>
            ))}
          </div>
        </div>
      </section>

      <DailyBriefPanel brief={bootstrap.daily_brief || overview.latest_brief} task={bootstrap.brief_status} />
    </div>
  );
}

function DailyBriefPanel({ brief, task }: { brief: DailyBrief | null; task: TaskRun | null }) {
  const running = isTaskActive(task);
  const [activeCategory, setActiveCategory] = useState<'tech' | 'finance' | 'politics'>('tech');
  if (!brief) {
    return (
      <section className="panel daily-brief-panel">
        <div className="daily-brief-head">
          <PanelTitle icon={<Layers3 size={18} />} title="今日资讯简报" />
          {running && <span className="pill good">自动生成中</span>}
        </div>
        {running ? <TaskStrip task={task} fallback="资讯简报正在后台生成" /> : <EmptyState text="资讯简报会在后台自动生成。" />}
      </section>
    );
  }
  const categoryTabs: Array<{ id: 'tech' | 'finance' | 'politics'; label: string; items: BriefArticle[] }> = [
    { id: 'tech', label: '技术动态', items: getBriefArticleRows(brief, 'tech') },
    { id: 'finance', label: '财经要点', items: getBriefArticleRows(brief, 'finance') },
    { id: 'politics', label: '时政观察', items: getBriefArticleRows(brief, 'politics') },
  ];
  const activeRows = categoryTabs.find((item) => item.id === activeCategory)?.items || [];
  const totalRows = categoryTabs.reduce((sum, item) => sum + item.items.length, 0);
  return (
    <section className="panel daily-brief-panel">
      <div className="daily-brief-head">
        <div className="brief-masthead">
          <PanelTitle icon={<Layers3 size={18} />} title="今日资讯简报" />
          <strong>{formatDate(brief.brief_date)}</strong>
        </div>
        <div className="brief-meta">
          <span>{brief.status === 'completed_full' ? '精编完成' : '部分完成'}</span>
          <span>{formatShortDateTime(brief.generated_at)}</span>
          <span>{formatInt(totalRows || brief.article_count)} 条</span>
        </div>
      </div>
      {running && <TaskStrip task={task} fallback="资讯简报正在后台生成" />}
      <div className="brief-detail-shell">
        <div className="brief-tabs">
          {categoryTabs.map((item) => (
            <button
              key={item.id}
              className={`brief-tab ${activeCategory === item.id ? 'active' : ''}`}
              type="button"
              onClick={() => setActiveCategory(item.id)}
            >
              <span>{item.label}</span>
              <b>{formatInt(item.items.length)}</b>
            </button>
          ))}
        </div>
        <div className="brief-detail-list">
          {activeRows.length ? (
            activeRows.map((item) => <BriefDetailItem key={`${activeCategory}-${item.url}-${item.title}`} item={item} />)
          ) : (
            <small>暂无可用条目</small>
          )}
        </div>
      </div>
      <div className="brief-footer">
        <span>{brief.editor_note || '后台自动整理，多源失败时会保留降级摘要。'}</span>
        <div>
          {brief.keywords.slice(0, 8).map((keyword) => <b key={keyword}>{keyword}</b>)}
        </div>
      </div>
      {brief.error_message && (
        <div className="brief-warning">
          <ShieldAlert size={16} />
          <span>{brief.error_message}</span>
        </div>
      )}
    </section>
  );
}

function getBriefArticleRows(brief: DailyBrief, category: 'tech' | 'finance' | 'politics'): BriefArticle[] {
  const flowRows = [...(brief.article_flow?.[category] || [])].sort(compareBriefArticlesByTime);
  if (flowRows.length) return flowRows;
  const selectedMap: Record<typeof category, BriefItem[]> = {
    tech: brief.tech_briefs,
    finance: brief.finance_briefs,
    politics: brief.politics_briefs,
  };
  const rows: BriefArticle[] = [];
  for (const item of selectedMap[category] || []) {
    rows.push({
      title: item.title,
      url: item.url,
      source: item.source,
      category,
      summary: item.summary,
      published_at: '',
    });
  }
  return rows.sort(compareBriefArticlesByTime);
}

function compareBriefArticlesByTime(a: BriefArticle, b: BriefArticle) {
  return briefArticleTimeValue(b.published_at) - briefArticleTimeValue(a.published_at);
}

function briefArticleTimeValue(value: string | null | undefined) {
  if (!value) return 0;
  const normalized = value.includes('T') ? value : value.replace(' ', 'T');
  const timestamp = Date.parse(normalized);
  return Number.isNaN(timestamp) ? 0 : timestamp;
}

function BriefDetailItem({ item }: { item: BriefArticle }) {
  return (
    <a className="brief-detail-item" href={item.url} target="_blank" rel="noreferrer">
      <div>
        <strong>{item.title}</strong>
        <span>{item.source}{item.published_at ? ` · ${formatChinaLocalDateTime(item.published_at)}` : ''}</span>
      </div>
      {item.summary && <p>{item.summary}</p>}
    </a>
  );
}

function HealthHints({ bootstrap }: { bootstrap: Bootstrap }) {
  const hints = dataHealthHints(bootstrap);
  if (!hints.length) return null;
  return (
    <section className="health-strip" aria-label="数据状态提示">
      {hints.map((hint) => (
        <span key={hint} className="health-hint">{hint}</span>
      ))}
    </section>
  );
}

function Warehouse() {
  const [rows, setRows] = useState<Array<Record<string, unknown>>>([]);
  const [selectedCode, setSelectedCode] = useState<string | null>(null);
  const [detail, setDetail] = useState<Record<string, unknown> | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [search, setSearch] = useState('');
  const [exchange, setExchange] = useState('');
  const [board, setBoard] = useState('');
  const [view, setView] = useState<'quote' | 'flow' | 'structure'>('quote');
  const [error, setError] = useState<string | null>(null);
  const limit = 40;
  const exchangeOptions = [
    { label: '全部市场', value: '' },
    { label: '上交所', value: 'SH' },
    { label: '深交所', value: 'SZ' },
    { label: '北交所', value: 'BJ' },
  ];
  const boardOptions = [
    { label: '全部板块', value: '' },
    { label: '主板', value: 'main' },
    { label: '创业板', value: 'gem' },
    { label: '科创板', value: 'star' },
  ];
  const viewOptions = [
    { value: 'quote', label: '行情', sub: '价格 / 成交 / 换手' },
    { value: 'flow', label: '资金', sub: '主力 / 龙虎榜 / 量能' },
    { value: 'structure', label: '结构', sub: '题材数 / 筹码 / 异动' },
  ] as const;

  async function load() {
    try {
      const data = (await api.stocks(limit, offset, search, { exchange, board })) as { rows: Array<Record<string, unknown>>; total: number };
      setRows(data.rows);
      setTotal(data.total);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : '数据仓库加载失败');
    }
  }

  useEffect(() => {
    void load();
  }, [offset, search, exchange, board]);

  async function selectStock(code: string) {
    setSelectedCode(code);
    setDetailLoading(true);
    try {
      setDetail((await api.stockDetail(code)) as Record<string, unknown>);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : '个股档案加载失败');
    } finally {
      setDetailLoading(false);
    }
  }

  return (
    <div className="warehouse-layout">
      <section className="panel warehouse-list-panel">
        <div className="table-toolbar">
          <PanelTitle icon={<Database size={18} />} title="本地股票仓" />
          <input className="search" placeholder="代码 / 名称" value={search} onChange={(event) => { setOffset(0); setSearch(event.target.value); }} />
        </div>
        <div className="warehouse-view-tabs" aria-label="仓库视图">
          {viewOptions.map((option) => (
            <button
              key={option.value}
              className={view === option.value ? 'active' : ''}
              onClick={() => setView(option.value)}
            >
              <strong>{option.label}</strong>
              <small>{option.sub}</small>
            </button>
          ))}
        </div>
        <div className="warehouse-filters" aria-label="股票筛选">
          <div className="filter-group">
            {exchangeOptions.map((option) => (
              <button
                key={option.value || 'all-exchange'}
                className={exchange === option.value ? 'filter-chip active' : 'filter-chip'}
                onClick={() => { setOffset(0); setExchange(option.value); }}
              >
                {option.label}
              </button>
            ))}
          </div>
          <div className="filter-group">
            {boardOptions.map((option) => (
              <button
                key={option.value || 'all-board'}
                className={board === option.value ? 'filter-chip active' : 'filter-chip'}
                onClick={() => { setOffset(0); setBoard(option.value); }}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>
        {error && <InlineError text={error} />}
        <div className="table-wrap warehouse-table-wrap">
          <table className="warehouse-table">
            <thead>
              <tr>
                <th>股票</th>
                {view === 'quote' && (
                  <>
                    <th>最新价</th>
                    <th>涨跌幅</th>
                    <th>成交额</th>
                    <th>换手率</th>
                    <th>流通市值</th>
                    <th>量比</th>
                  </>
                )}
                {view === 'flow' && (
                  <>
                    <th>最新价</th>
                    <th>主力净额</th>
                    <th>资金净流</th>
                    <th>成交额</th>
                    <th>量比</th>
                    <th>龙虎榜</th>
                  </>
                )}
                {view === 'structure' && (
                  <>
                    <th>题材数</th>
                    <th>筹码胜率</th>
                    <th>历史天数</th>
                    <th>最新 K 线</th>
                    <th>异动</th>
                  </>
                )}
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 ? (
                <tr><td colSpan={view === 'structure' ? 6 : 7} className="empty-cell">暂无本地股票数据</td></tr>
              ) : rows.map((row) => (
                <tr
                  key={String(row.code)}
                  className={selectedCode === String(row.code) ? 'selected-row' : ''}
                  onClick={() => void selectStock(String(row.code))}
                >
                  <td>
                    <div className="warehouse-stock-cell">
                      <button
                        className="table-action"
                        onClick={(event) => {
                          event.stopPropagation();
                          void selectStock(String(row.code));
                        }}
                        title="打开个股档案"
                      >
                        <Database size={14} />
                      </button>
                      <div>
                        <strong>{String(row.name || '')}</strong>
                        <span className="mono">{String(row.code || '')} · {String(row.exchange || '')} · {boardLabel(row.board)}</span>
                      </div>
                    </div>
                  </td>
                  {view === 'quote' && (
                    <>
                      <td>{formatPrice(row.latest_price)}</td>
                      <td className={toneClass(Number(row.pct_chg || 0))}>{formatPercent(row.pct_chg)}</td>
                      <td>{formatMoney(row.amount)}</td>
                      <td>{formatPercent(row.turnover_rate)}</td>
                      <td>{formatMoney(row.float_market_value)}</td>
                      <td>{formatRatioX(row.volume_ratio)}</td>
                    </>
                  )}
                  {view === 'flow' && (
                    <>
                      <td>{formatPrice(row.latest_price)}</td>
                      <td className={toneClass(Number(row.main_net_amount || 0))}>{formatMoney(row.main_net_amount)}</td>
                      <td className={toneClass(Number(row.net_mf_amount || 0))}>{formatMoney(row.net_mf_amount)}</td>
                      <td>{formatMoney(row.amount)}</td>
                      <td>{formatRatioX(row.volume_ratio)}</td>
                      <td>{nullableNumber(row.latest_top_net_amount) === null ? '-' : formatMoney(row.latest_top_net_amount)}</td>
                    </>
                  )}
                  {view === 'structure' && (
                    <>
                      <td>{formatInt(row.concept_count)}</td>
                      <td>{formatPercentRatio(row.winner_rate)}</td>
                      <td>{formatInt(row.history_days)}</td>
                      <td className="mono">{formatDate(row.latest_history_date)}</td>
                      <td>{warehouseEventLabel(row)}</td>
                    </>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="pager">
          <span>{formatInt(offset + 1)} - {formatInt(Math.min(offset + limit, total))} / {formatInt(total)}</span>
          <button className="ghost" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - limit))}>上一页</button>
          <button className="ghost" disabled={offset + limit >= total} onClick={() => setOffset(offset + limit)}>下一页</button>
        </div>
      </section>
      <aside className="warehouse-detail-rail">
        {(detail || detailLoading) ? (
          <StockDetailPanel detail={detail} loading={detailLoading} onClose={() => { setDetail(null); setSelectedCode(null); }} />
        ) : (
          <section className="panel stock-profile stock-profile-empty">
            <PanelTitle icon={<Database size={18} />} title="个股档案" />
            <p>选择左侧任意股票，行情、资金、技术、题材和事件会固定显示在这里。</p>
          </section>
        )}
      </aside>
    </div>
  );
}

function StockDetailPanel({
  detail,
  loading,
  onClose,
}: {
  detail: Record<string, unknown> | null;
  loading: boolean;
  onClose: () => void;
}) {
  const basic = asRecord(detail?.basic);
  const daily = asRecord(detail?.daily_basic);
  const factor = asRecord(detail?.factor);
  const moneyflow = asRecord(detail?.moneyflow);
  const cyq = asRecord(detail?.cyq_perf);
  const concepts = compactRecords(detail?.concepts);
  const limitEvents = compactRecords(detail?.limit_events);
  const topEvents = compactRecords(detail?.top_events);
  const volumeRatio = daily?.volume_ratio ?? basic?.volume_ratio;
  const volumeRatioSource = String(daily?.volume_ratio_source || basic?.volume_ratio_source || '');
  const volumeRatioSub = ['换手 ' + formatPercent(daily?.turnover_rate ?? basic?.turnover_rate), volumeRatioSource].filter(Boolean).join(' · ');

  return (
    <section className="panel stock-profile">
      <div className="stock-profile-head">
        <div>
          <PanelTitle icon={<Database size={18} />} title={loading ? '读取个股档案' : `${String(basic?.name || '-')} · ${String(basic?.code || '')}`} />
          <p>{String(basic?.exchange || '-')} · {boardLabel(basic?.board)} · 历史 {formatInt(basic?.history_days)} 天</p>
        </div>
        <button className="ghost icon-button" onClick={onClose} aria-label="关闭个股档案">
          <X size={16} />
        </button>
      </div>
      {loading ? (
        <EmptyState text="读取中。" />
      ) : (
        <>
          <div className="profile-metrics">
            <MetricCard label="最新价" value={formatPrice(basic?.latest_price)} sub={formatPercent(basic?.pct_chg)} icon={<CandlestickChart size={18} />} />
            <MetricCard label="量比" value={formatRatioX(volumeRatio)} sub={volumeRatioSub} icon={<Gauge size={18} />} />
            <MetricCard label="主力净额" value={formatMoney(moneyflow?.main_net_amount)} sub={`净流 ${formatMoney(moneyflow?.net_mf_amount)}`} icon={<Activity size={18} />} />
            <MetricCard label="筹码胜率" value={formatPercentRatio(cyq?.winner_rate)} sub={`中位成本 ${formatPrice(cyq?.cost_50pct)}`} icon={<Layers3 size={18} />} />
          </div>
          <div className="profile-grid">
            <ProfileBlock title="技术因子" rows={[
              ['MACD', formatPrice(factor?.macd)],
              ['KDJ', [formatPrice(factor?.kdj_k), formatPrice(factor?.kdj_d), formatPrice(factor?.kdj_j)].join(' / ')],
              ['RSI6', formatPrice(factor?.rsi_6)],
              ['BOLL', [formatPrice(factor?.boll_upper), formatPrice(factor?.boll_mid), formatPrice(factor?.boll_lower)].join(' / ')],
            ]} />
            <ProfileBlock title="题材成分" rows={conceptProfileRows(concepts)} />
            <ProfileBlock title="涨跌停 / 炸板" rows={(limitEvents.length ? limitEvents.slice(0, 5).map((item) => [formatDate(item?.trade_date), `${limitTypeLabel(item?.limit_type)} · ${formatInt(item?.open_times)} 次`]) : [['普通交易日', '无涨跌停/炸板']])} />
            <ProfileBlock title="龙虎榜" rows={(topEvents.length ? topEvents.slice(0, 5).map((item) => [formatDate(item?.trade_date), `${formatMoney(item?.net_amount)} · ${String(item?.reason || '-')}`]) : [['未上榜', '无龙虎榜记录']])} />
          </div>
        </>
      )}
    </section>
  );
}

function ProfileBlock({ title, rows }: { title: string; rows: Array<[ReactNode, ReactNode]> }) {
  return (
    <div className="profile-block">
      <h3>{title}</h3>
      {rows.map(([label, value], index) => (
        <div key={`${title}-${index}`}>
          <span>{label}</span>
          <b>{value}</b>
        </div>
      ))}
    </div>
  );
}

function conceptProfileRows(concepts: Array<Record<string, unknown>>): Array<[ReactNode, ReactNode]> {
  if (!concepts.length) return [['暂无成分', '-']];
  return concepts.slice(0, 8).map((item) => [
    String(item?.con_name || '-'),
    <span className="profile-code">{String(item?.con_code || '板块代码')}</span>,
  ]);
}

function IndicatorLibraryPage({
  library,
}: {
  library: IndicatorLibrary;
}) {
  const [category, setCategory] = useState(library.categories[0]?.id || '');
  const [search, setSearch] = useState('');
  const [selectedId, setSelectedId] = useState(library.indicators[0]?.id || '');
  const categoryMap = useMemo(
    () => Object.fromEntries(library.categories.map((item) => [item.id, item])),
    [library.categories],
  );
  const indicatorById = useMemo(
    () => Object.fromEntries(library.indicators.map((indicator) => [indicator.id, indicator])),
    [library.indicators],
  );
  const indicators = useMemo(() => {
    const query = search.trim().toLowerCase();
    return library.indicators.filter((indicator) => {
      const matchesCategory = !category || indicator.category_id === category;
      const haystack = `${indicator.name} ${indicator.id} ${indicator.description} ${indicator.formula}`.toLowerCase();
      return matchesCategory && (!query || haystack.includes(query));
    });
  }, [category, library.indicators, search]);
  const selected = library.indicators.find((item) => item.id === selectedId) || indicators[0] || library.indicators[0];

  useEffect(() => {
    if (!indicators.some((item) => item.id === selectedId) && indicators[0]) {
      setSelectedId(indicators[0].id);
    }
  }, [indicators, selectedId]);

  return (
    <div className="indicator-page">
      <section className="panel indicator-hero">
        <div>
          <PanelTitle icon={<LineChart size={18} />} title="指标库" />
          <p>把行情、技术、资金、题材、事件和筹码都整理成可解释指标。策略以后引用这些指标，而不是把参数散落在各处。</p>
        </div>
        <div className="indicator-summary">
          <span><b>{formatInt(library.summary.indicator_count)}</b><em>指标</em></span>
          <span><b>{formatInt(library.summary.active_count)}</b><em>分析可用</em></span>
          <span><b>{formatInt(library.summary.interaction_rule_count)}</b><em>可做组合</em></span>
        </div>
      </section>

      <section className="indicator-layout">
        <aside className="panel indicator-sidebar">
          <input
            className="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="搜索指标 / 公式 / 用途"
          />
          <div className="indicator-categories">
            {library.categories.map((item) => {
              const count = library.indicators.filter((indicator) => indicator.category_id === item.id).length;
              return (
                <button
                  key={item.id}
                  className={category === item.id ? 'active' : ''}
                  onClick={() => setCategory(item.id)}
                  type="button"
                >
                  <strong>{item.label}</strong>
                  <small>{count} 个指标</small>
                </button>
              );
            })}
          </div>
        </aside>

        <section className="panel indicator-list-panel">
          <div className="indicator-list-head">
            <div>
              <strong>{categoryMap[category]?.label || '全部指标'}</strong>
              <span>{categoryMap[category]?.description || '按分类浏览指标定义。'}</span>
            </div>
            <b>{formatInt(indicators.length)}</b>
          </div>
          <div className="indicator-card-grid">
            {indicators.map((indicator) => (
              <button
                key={indicator.id}
                className={selected?.id === indicator.id ? 'indicator-card active' : 'indicator-card'}
                onClick={() => setSelectedId(indicator.id)}
                type="button"
              >
                <div>
                  <strong>{indicator.name}</strong>
                  <span>{categoryMap[indicator.category_id]?.label}</span>
                </div>
                <p>{indicator.description}</p>
                <footer>
                  <em className={`status-pill ${indicatorStatusClass(indicator)}`}>{indicatorStatusLabel(indicator)}</em>
                  <small>{indicatorUsageLabel(indicator.usage)}</small>
                </footer>
              </button>
            ))}
          </div>
        </section>

        <aside className="panel indicator-detail">
          {selected ? (
            <>
              <div className="indicator-detail-head">
                <span className={`status-pill ${indicatorStatusClass(selected)}`}>{indicatorStatusLabel(selected)}</span>
                <h2>{selected.name}</h2>
                <p>{selected.description}</p>
              </div>
              <div className="indicator-detail-grid">
                <span><em>类型</em><b>{indicatorKindLabel(selected)}</b></span>
                <span><em>分类</em><b>{categoryMap[selected.category_id]?.label || selected.category_id}</b></span>
                <span><em>用途</em><b>{indicatorUsageLabel(selected.usage)}</b></span>
                <span><em>缺失处理</em><b>{missingPolicyLabel(selected.default_missing_policy)}</b></span>
                <span><em>分析状态</em><b>{indicatorReadinessLabel(selected)}</b></span>
              </div>
              {pairedStrategyIndicators(selected, indicatorById).length > 0 && (
                <div className="indicator-explain paired">
                  <strong>可填写参数</strong>
                  <div className="indicator-pair-list">
                    {pairedStrategyIndicators(selected, indicatorById).map((indicator) => (
                      <span key={indicator.id}>{indicator.name}</span>
                    ))}
                  </div>
                </div>
              )}
              <div className="indicator-explain">
                <strong>怎么算</strong>
                <p>{selected.formula}</p>
              </div>
              <div className="indicator-explain">
                <strong>数据源</strong>
                <p>{selected.source}</p>
              </div>
            </>
          ) : (
            <EmptyState text="暂无指标定义。" />
          )}
        </aside>
      </section>

      <section className="panel indicator-mode-note">
        <PanelTitle icon={<SlidersHorizontal size={18} />} title="策略页直接引用指标" />
        <p>这里保持为指标字典：查字段含义、数据源、计算方法和分析状态。到策略页后可以直接把指标加入筛选、加权、风控、展示或组合倍率。</p>
      </section>
    </div>
  );
}

function SignalModeManager({
  library,
  createMode,
  saveMode,
  duplicateMode,
  deleteMode,
  embedded = false,
}: {
  library: IndicatorLibrary;
  createMode: (name: string) => Promise<SignalModeTemplate>;
  saveMode: (mode: SignalModeTemplate) => Promise<SignalModeTemplate>;
  duplicateMode: (id: string) => Promise<SignalModeTemplate>;
  deleteMode: (id: string) => Promise<void>;
  embedded?: boolean;
}) {
  const indicatorById = useMemo(
    () => Object.fromEntries(library.indicators.map((indicator) => [indicator.id, indicator])),
    [library.indicators],
  );
  const [selectedModeId, setSelectedModeId] = useState(library.signal_modes[0]?.id || '');
  const [draft, setDraft] = useState<SignalModeTemplate | null>(library.signal_modes[0] ? cloneSignalProfile(library.signal_modes[0]) : null);
  const [addIndicatorId, setAddIndicatorId] = useState('');
  const [addRole, setAddRole] = useState('filter');
  const [busy, setBusy] = useState(false);
  const selectedMode = useMemo(
    () => library.signal_modes.find((mode) => mode.id === selectedModeId) || library.signal_modes[0] || null,
    [library.signal_modes, selectedModeId],
  );

  useEffect(() => {
    if (!library.signal_modes.some((mode) => mode.id === selectedModeId) && library.signal_modes[0]) {
      setSelectedModeId(library.signal_modes[0].id);
    }
  }, [library.signal_modes, selectedModeId]);

  useEffect(() => {
    setDraft(selectedMode ? cloneSignalProfile(selectedMode) : null);
  }, [selectedMode]);

  const activeIndicatorIds = useMemo(
    () => new Set((draft?.fields || []).map((field) => field.indicator_id)),
    [draft?.fields],
  );
  const addableIndicators = useMemo(
    () => library.indicators
      .filter((indicator) => indicator.status !== 'planned' || indicator.kind === 'strategy_param')
      .filter((indicator) => !activeIndicatorIds.has(indicator.id))
      .sort((left, right) => `${left.group_label}${left.name}`.localeCompare(`${right.group_label}${right.name}`, 'zh-CN')),
    [activeIndicatorIds, library.indicators],
  );
  const addableStrategyParams = addableIndicators.filter((indicator) => indicator.kind === 'strategy_param');
  const addableObservationIndicators = addableIndicators.filter((indicator) => indicator.kind !== 'strategy_param');
  const selectedAddId = addIndicatorId || addableIndicators[0]?.id || '';
  const selectedAddIndicator = indicatorById[selectedAddId];
  const selectedPairIndicators = pairedStrategyIndicators(selectedAddIndicator, indicatorById)
    .filter((indicator) => !activeIndicatorIds.has(indicator.id));
  const fieldGroups = useMemo(() => {
    const groups = new Map<string, { id: string; label: string; fields: SignalModeField[] }>();
    (draft?.fields || []).forEach((field) => {
      const indicator = indicatorById[field.indicator_id];
      const id = field.group_id || indicator?.group_id || 'other';
      const label = field.group_label || indicator?.group_label || '其他';
      if (!groups.has(id)) groups.set(id, { id, label, fields: [] });
      groups.get(id)?.fields.push(field);
    });
    return Array.from(groups.values());
  }, [draft?.fields, indicatorById]);

  const patchDraft = (patch: Partial<SignalModeTemplate>) => {
    if (!draft) return;
    setDraft({ ...draft, ...patch });
  };
  const patchField = (indicatorId: string, patch: Partial<SignalModeField>) => {
    if (!draft) return;
    setDraft({
      ...draft,
      fields: draft.fields.map((field) => (field.indicator_id === indicatorId ? { ...field, ...patch } : field)),
    });
  };
  const removeField = (indicatorId: string) => {
    if (!draft) return;
    setDraft({
      ...draft,
      fields: draft.fields.filter((field) => field.indicator_id !== indicatorId),
      rule_groups: draft.rule_groups
        .map((group) => ({
          ...group,
          rules: group.rules
            .map((rule) => ({ ...rule, indicator_ids: rule.indicator_ids.filter((id) => id !== indicatorId) }))
            .filter((rule) => rule.indicator_ids.length > 0),
        }))
        .filter((group) => group.rules.length > 0),
    });
  };
  const addFieldById = (indicatorId: string, role = addRole) => {
    if (!draft || !indicatorId || activeIndicatorIds.has(indicatorId)) return;
    const indicator = indicatorById[indicatorId];
    if (!indicator) return;
    setDraft({
      ...draft,
      fields: [
        ...draft.fields,
        {
          indicator_id: indicator.id,
          role,
          group_id: indicator.group_id,
          group_label: indicator.group_label,
        },
      ],
    });
    setAddIndicatorId('');
  };
  const addField = () => addFieldById(selectedAddId, addRole);
  const patchRule = (groupId: string, ruleId: string, patch: Partial<IndicatorRule>) => {
    if (!draft) return;
    setDraft({
      ...draft,
      rule_groups: draft.rule_groups.map((group) => (
        group.id === groupId
          ? { ...group, rules: group.rules.map((rule) => (rule.id === ruleId ? { ...rule, ...patch } : rule)) }
          : group
      )),
    });
  };
  const removeRule = (groupId: string, ruleId: string) => {
    if (!draft) return;
    setDraft({
      ...draft,
      rule_groups: draft.rule_groups
        .map((group) => (
          group.id === groupId
            ? { ...group, rules: group.rules.filter((rule) => rule.id !== ruleId) }
            : group
        ))
        .filter((group) => group.rules.length > 0),
    });
  };
  const addRule = () => {
    if (!draft) return;
    const firstIndicators = draft.fields.slice(0, 2).map((field) => field.indicator_id);
    const rule: IndicatorRule = {
      id: `rule-${Date.now().toString(36)}`,
      name: '新的组合条件',
      kind: 'interaction',
      indicator_ids: firstIndicators,
      expression: '',
      effect: { type: 'score', value: 0 },
      missing_policy: 'neutral',
      editable: true,
    };
    const customGroup = draft.rule_groups.find((group) => group.id === 'custom_conditions');
    const ruleGroups = customGroup
      ? draft.rule_groups.map((group) => (
        group.id === 'custom_conditions' ? { ...group, rules: [...group.rules, rule] } : group
      ))
      : [...draft.rule_groups, { id: 'custom_conditions', label: '组合条件', rules: [rule] }];
    setDraft({ ...draft, rule_groups: ruleGroups });
  };
  const addRuleIndicator = (groupId: string, ruleId: string, indicatorId: string) => {
    if (!draft || !indicatorId) return;
    setDraft({
      ...draft,
      rule_groups: draft.rule_groups.map((group) => (
        group.id === groupId
          ? {
            ...group,
            rules: group.rules.map((rule) => (
              rule.id === ruleId && !rule.indicator_ids.includes(indicatorId)
                ? { ...rule, indicator_ids: [...rule.indicator_ids, indicatorId] }
                : rule
            )),
          }
          : group
      )),
    });
  };
  const removeRuleIndicator = (groupId: string, ruleId: string, indicatorId: string) => {
    if (!draft) return;
    patchRule(groupId, ruleId, {
      indicator_ids: draft.rule_groups
        .find((group) => group.id === groupId)
        ?.rules.find((rule) => rule.id === ruleId)
        ?.indicator_ids.filter((id) => id !== indicatorId) || [],
    });
  };
  const runModeAction = async (action: () => Promise<unknown>) => {
    try {
      setBusy(true);
      await action();
    } finally {
      setBusy(false);
    }
  };

  if (!draft) {
    return null;
  }

  const ruleCount = draft.rule_groups.reduce((sum, group) => sum + group.rules.length, 0);

  return (
    <section className={embedded ? 'signal-mode-manager embedded' : 'panel signal-mode-manager'}>
      <div className="signal-manager-head">
        <div>
          <PanelTitle icon={<SlidersHorizontal size={18} />} title="信号模式" />
          <p>模式只定义“有哪些指标和组合条件”，具体阈值和运行方式在当前策略里填写。</p>
        </div>
        <div className="signal-manager-actions">
          <button className="ghost compact" disabled={busy} type="button" onClick={() => void runModeAction(async () => {
            const mode = await createMode('新信号模式');
            setSelectedModeId(mode.id);
          })}>
            <Plus size={14} />
            新建
          </button>
          <button className="ghost compact" disabled={busy} type="button" onClick={() => void runModeAction(async () => {
            const mode = await duplicateMode(draft.id);
            setSelectedModeId(mode.id);
          })}>
            <Copy size={14} />
            复制
          </button>
          <button className="ghost compact danger" disabled={busy || library.signal_modes.length <= 1} type="button" onClick={() => void runModeAction(async () => {
            if (!window.confirm(`删除“${draft.name}”？`)) return;
            await deleteMode(draft.id);
            setSelectedModeId(library.signal_modes.find((mode) => mode.id !== draft.id)?.id || '');
          })}>
            <Trash2 size={14} />
            删除
          </button>
          <button className="primary compact" disabled={busy} type="button" onClick={() => void runModeAction(async () => {
            const mode = await saveMode(draft);
            setSelectedModeId(mode.id);
          })}>
            <Save size={14} />
            保存
          </button>
        </div>
      </div>

      <div className="signal-manager-layout">
        <aside className="signal-mode-list">
          {library.signal_modes.map((mode) => {
            const count = mode.fields?.length || 0;
            const combinations = mode.rule_groups.reduce((sum, group) => sum + group.rules.length, 0);
            const active = mode.id === draft.id;
            return (
              <button
                key={mode.id}
                type="button"
                className={active ? 'active' : ''}
                onClick={() => setSelectedModeId(mode.id)}
              >
                <strong>{mode.name}</strong>
                <span>{formatInt(count)} 个指标 · {formatInt(combinations)} 条组合条件</span>
              </button>
            );
          })}
        </aside>

        <div className="signal-mode-editor">
          <div className="profile-editor-grid">
            <label className="field">
              <span>模式名称</span>
              <input
                value={draft.name}
                onChange={(event) => patchDraft({ name: event.target.value })}
              />
            </label>
            <label className="field">
              <span>说明</span>
              <input
                value={draft.description}
                onChange={(event) => patchDraft({ description: event.target.value })}
              />
            </label>
            <label className="field wide">
              <span>备注</span>
              <textarea
                value={draft.note}
                onChange={(event) => patchDraft({ note: event.target.value })}
                rows={2}
              />
            </label>
          </div>

          <div className="signal-editor-section">
            <div className="signal-section-head">
              <div>
                <strong>模式指标</strong>
                <span>{formatInt(draft.fields.length)} 个</span>
              </div>
              <div className="indicator-add-stack">
                <div className="indicator-add-controls">
                  <select value={selectedAddId} onChange={(event) => setAddIndicatorId(event.target.value)}>
                    {addableStrategyParams.length > 0 && (
                      <optgroup label="可填写参数">
                        {addableStrategyParams.map((indicator) => (
                          <option key={indicator.id} value={indicator.id}>
                            {indicator.group_label} / {indicator.name}
                          </option>
                        ))}
                      </optgroup>
                    )}
                    {addableObservationIndicators.length > 0 && (
                      <optgroup label="观察指标">
                        {addableObservationIndicators.map((indicator) => (
                          <option key={indicator.id} value={indicator.id}>
                            {indicator.group_label} / {indicator.name}
                          </option>
                        ))}
                      </optgroup>
                    )}
                  </select>
                  <SignalRoleChips value={addRole} onChange={setAddRole} />
                  <button className="ghost compact" type="button" disabled={!selectedAddId} onClick={addField}>
                    <Plus size={13} />
                    加入
                  </button>
                </div>
                {selectedAddIndicator && selectedAddIndicator.kind !== 'strategy_param' && (
                  <div className="indicator-pair-hint">
                    <span>
                      <strong>{selectedAddIndicator.name}</strong>
                      观察值
                    </span>
                    {selectedPairIndicators.length > 0 ? (
                      <div>
                        {selectedPairIndicators.map((indicator) => (
                          <button key={indicator.id} className="tiny-action" type="button" onClick={() => addFieldById(indicator.id, addRole)}>
                            <Plus size={12} />
                            {indicator.name}
                          </button>
                        ))}
                      </div>
                    ) : (
                      <em>无需填写参数</em>
                    )}
                  </div>
                )}
              </div>
            </div>
            <div className="mode-field-groups">
              {fieldGroups.map((group) => (
                <div key={group.id} className="mode-field-group">
                  <header>
                    <strong>{group.label}</strong>
                    <span>{formatInt(group.fields.length)}</span>
                  </header>
                  <div>
                    {group.fields.map((field) => {
                      const indicator = indicatorById[field.indicator_id];
                      if (!indicator) return null;
                      const pairNames = pairedStrategyIndicators(indicator, indicatorById)
                        .filter((item) => !activeIndicatorIds.has(item.id))
                        .map((item) => item.name);
                      return (
                        <article key={field.indicator_id} className="mode-field-item">
                          <div>
                            <strong>{indicator.name}</strong>
                            <span>{indicator.kind === 'strategy_param' ? '可填写参数' : indicator.source}</span>
                            {pairNames.length > 0 && <small>可配：{pairNames.join('、')}</small>}
                          </div>
                          <SignalRoleChips value={field.role || 'filter'} onChange={(role) => patchField(field.indicator_id, { role })} compact />
                          <button className="table-action" type="button" onClick={() => removeField(field.indicator_id)} title="移除指标">
                            <X size={13} />
                          </button>
                        </article>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="signal-editor-section">
            <div className="signal-section-head">
              <div>
                <strong>组合条件</strong>
                <span>{formatInt(ruleCount)} 条</span>
              </div>
              <button className="ghost compact" type="button" onClick={addRule}>
                <Plus size={13} />
                新增条件
              </button>
            </div>
            <div className="signal-rule-board compact">
              {draft.rule_groups.length === 0 && <EmptyState text="暂无组合条件。可以先保存这个简单模式，也可以新增条件。" />}
              {draft.rule_groups.map((group) => (
                <article key={group.id} className="signal-rule-group">
                  <header>
                    <strong>{group.label}</strong>
                    <span>{formatInt(group.rules.length)} 条</span>
                  </header>
                  <div className="signal-rule-list">
                    {group.rules.map((rule) => {
                      const unusedIndicators = draft.fields
                        .map((field) => indicatorById[field.indicator_id])
                        .filter(Boolean)
                        .filter((indicator) => !rule.indicator_ids.includes(indicator.id));
                      return (
                        <div key={rule.id} className={`signal-rule-card ${rule.kind}`}>
                          <div className="rule-edit-grid">
                            <label className="field">
                              <span>条件名称</span>
                              <input value={rule.name} onChange={(event) => patchRule(group.id, rule.id, { name: event.target.value })} />
                            </label>
                            <label className="field">
                              <span>用途</span>
                              <select value={rule.kind} onChange={(event) => patchRule(group.id, rule.id, { kind: event.target.value as IndicatorRule['kind'] })}>
                                <option value="filter">过滤</option>
                                <option value="score">加分</option>
                                <option value="risk">风控</option>
                                <option value="interaction">组合条件</option>
                              </select>
                            </label>
                          </div>
                          <div className="rule-indicator-chips editable">
                            {rule.indicator_ids.map((indicatorId) => (
                              <button key={indicatorId} type="button" onClick={() => removeRuleIndicator(group.id, rule.id, indicatorId)}>
                                {indicatorById[indicatorId]?.name || indicatorId}
                                <X size={12} />
                              </button>
                            ))}
                            {unusedIndicators.length > 0 && (
                              <select value="" onChange={(event) => addRuleIndicator(group.id, rule.id, event.target.value)}>
                                <option value="">加入指标</option>
                                {unusedIndicators.map((indicator) => <option key={indicator.id} value={indicator.id}>{indicator.name}</option>)}
                              </select>
                            )}
                          </div>
                          <label className="field wide">
                            <span>条件表达</span>
                            <textarea
                              value={rule.expression}
                              onChange={(event) => patchRule(group.id, rule.id, { expression: event.target.value })}
                              rows={3}
                              placeholder="例如：突破上沿达标，并且量比达到设定阈值"
                            />
                          </label>
                          <div className="rule-edit-grid">
                            <label className="field">
                              <span>效果</span>
                              <select
                                value={rule.effect?.type || 'score'}
                                onChange={(event) => patchRule(group.id, rule.id, { effect: { ...rule.effect, type: event.target.value } })}
                              >
                                <option value="gate">门槛</option>
                                <option value="score">评分</option>
                                <option value="risk">风险扣分</option>
                              </select>
                            </label>
                            <label className="field">
                              <span>数值</span>
                              <input
                                value={String(rule.effect?.value ?? '')}
                                onChange={(event) => patchRule(group.id, rule.id, { effect: { ...rule.effect, value: event.target.value } })}
                              />
                            </label>
                            <label className="field">
                              <span>缺失处理</span>
                              <select value={rule.missing_policy} onChange={(event) => patchRule(group.id, rule.id, { missing_policy: event.target.value })}>
                                <option value="allow">允许缺失</option>
                                <option value="neutral">缺失中性</option>
                                <option value="skip">缺失跳过</option>
                              </select>
                            </label>
                          </div>
                          <button className="table-action remove-rule" type="button" onClick={() => removeRule(group.id, rule.id)} title="移除条件">
                            <Trash2 size={14} />
                          </button>
                        </div>
                      );
                    })}
                  </div>
                </article>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function StrategyPanel(props: {
  indicatorLibrary: IndicatorLibrary;
  presets: StrategyPreset[];
  selectedPresetId: string | null;
  strategy: StrategyConfig;
  strategyName: string;
  setStrategy: (config: StrategyConfig) => void;
  setStrategyName: (name: string) => void;
  selectPreset: (preset: StrategyPreset) => void;
  saveStrategy: (setDefault?: boolean) => Promise<void>;
  saveAndRun: () => Promise<void>;
  createMode: (name: string) => Promise<SignalModeTemplate>;
  saveMode: (mode: SignalModeTemplate) => Promise<SignalModeTemplate>;
  duplicateMode: (id: string) => Promise<SignalModeTemplate>;
  deleteMode: (id: string) => Promise<void>;
  duplicate: () => Promise<void>;
  createBlank: () => Promise<void>;
  remove: () => Promise<void>;
  reset: () => Promise<void>;
}) {
  const selected = props.presets.find((preset) => preset.id === props.selectedPresetId);
  const customPresets = props.presets.filter((preset) => !preset.is_system);
  const selectedIsTemplate = Boolean(selected?.is_system);
  const [versions, setVersions] = useState<StrategyVersion[]>([]);
  const update = (key: keyof StrategyConfig, value: unknown) => {
    props.setStrategy({ ...props.strategy, [key]: value });
  };
  const activeAnalysisMode = analysisModes.find((mode) => mode.id === (props.strategy.analysis_mode || 'strict')) || analysisModes[0];
  const suggestedName = suggestStrategyName(props.strategy);
  const nameLooksGeneric = !props.strategyName.trim() || /^未命名策略/.test(props.strategyName.trim());
  const strategyProfile = strategyParameterProfile(props.indicatorLibrary);

  useEffect(() => {
    let alive = true;
    async function loadVersions() {
      if (!selected || selected.is_system) {
        setVersions([]);
        return;
      }
      try {
        const result = await api.strategyVersions(selected.id);
        if (alive) setVersions(result.rows || []);
      } catch {
        if (alive) setVersions([]);
      }
    }
    void loadVersions();
    return () => {
      alive = false;
    };
  }, [selected?.id, selected?.is_system, selected?.latest_version_number, selected?.updated_at]);

  return (
    <div className="strategy-layout">
      <section className="panel preset-panel">
        <div className="preset-head">
          <PanelTitle icon={<Settings2 size={18} />} title="策略库" />
          <button className="primary new-strategy" onClick={props.createBlank} type="button">
            <Plus size={15} />
            新增
          </button>
        </div>
        <div className="preset-section-title">
          <span>我的策略</span>
          <small>{customPresets.length} 个</small>
        </div>
        <div className="preset-list">
          {customPresets.length === 0 && <div className="preset-empty">点击新增创建第一个策略。</div>}
          {customPresets.map((preset) => (
            <button
              key={preset.id}
              className={preset.id === props.selectedPresetId ? 'preset active' : 'preset'}
              onClick={() => props.selectPreset(preset)}
            >
              <span className="preset-main">
                <strong>{preset.name}</strong>
                <em>{strategySummary(preset.config)}</em>
                <i>{preset.latest_version_number ? `v${preset.latest_version_number}` : '未记录版本'} · {formatShortDateTime(preset.updated_at)}</i>
              </span>
              <small>{preset.is_default ? '默认' : '自定义'}</small>
            </button>
          ))}
        </div>
        <button className="text-action restore-action" onClick={props.reset} type="button">
          <RotateCcw size={14} />
          恢复系统默认策略
        </button>
      </section>

      <section className="panel editor-panel">
        <div className="table-toolbar">
          <PanelTitle icon={<SlidersHorizontal size={18} />} title="策略编辑" />
          <div className="quick-actions">
            <button className="ghost" onClick={() => props.saveStrategy(false)}>
              <Save size={16} />
              保存
            </button>
            <button className="ghost" onClick={() => props.saveStrategy(true)}>
              <Star size={16} />
              保存为默认
            </button>
            <button className="primary lime" onClick={props.saveAndRun}>
              <Play size={16} />
              保存并运行
            </button>
          </div>
        </div>
        <div className="editor-action-strip">
          <span>{selectedIsTemplate ? '基础参数' : selected?.is_default ? '当前默认策略' : '当前策略'}</span>
          <div>
            <button className="ghost compact" disabled={!selected || selectedIsTemplate} onClick={props.duplicate}>
              <Copy size={14} />
              复制
            </button>
            <button className="ghost compact danger" disabled={!selected || selectedIsTemplate} onClick={props.remove}>
              <Trash2 size={14} />
              删除
            </button>
          </div>
        </div>
        <div className="strategy-readout">
          <span>{activeAnalysisMode.label}</span>
          <b>{strategySummary(props.strategy)}</b>
        </div>
        {versions.length > 0 && (
          <div className="version-strip">
            {versions.slice(0, 4).map((version) => (
              <span key={version.id}>
                <strong>v{version.version_number}</strong>
                <em>{version.summary}</em>
                <small>{formatShortDateTime(version.created_at)}</small>
              </span>
            ))}
          </div>
        )}
        {selectedIsTemplate && (
          <div className="template-banner">
            保存后会进入“我的策略”。
          </div>
        )}

        <div className="form-grid">
          <div className="field wide strategy-name-field">
            <span>策略名称</span>
            <input value={props.strategyName} onChange={(event) => props.setStrategyName(event.target.value)} />
            <small className="field-hint">
              {nameLooksGeneric ? '可以保留未命名，也可以采用下方建议。' : `建议名：${suggestedName}`}
            </small>
            {nameLooksGeneric && (
              <button className="suggest-name" type="button" onClick={() => props.setStrategyName(suggestedName)}>
                采用建议：{suggestedName}
              </button>
            )}
          </div>
          <div className="strategy-mode-selectors wide single">
            <label>
              <span>运行方式</span>
              <select value={props.strategy.analysis_mode || 'strict'} onChange={(event) => update('analysis_mode', event.target.value)}>
                {analysisModes.map((mode) => (
                  <option key={mode.id} value={mode.id}>{mode.label}</option>
                ))}
              </select>
            </label>
            <span className="strategy-mode-note">策略由运行参数和可选组合倍率共同决定；需要的形态/趋势计算会自动启用。</span>
          </div>
          <details className="legacy-strategy-controls wide" open>
            <summary>
              <span>运行参数</span>
              <small>基础股票池、形态窗口、趋势参数和输出设置统一在这里填写。</small>
            </summary>
            <div className="legacy-strategy-body">
              <SignalModeFieldForm
                profile={strategyProfile}
                library={props.indicatorLibrary}
                strategy={props.strategy}
                update={update}
              />
            </div>
          </details>
          <StrategyInteractionBuilder
            library={props.indicatorLibrary}
            strategy={props.strategy}
            setStrategy={props.setStrategy}
          />
        </div>
      </section>
    </div>
  );
}

function StrategyInteractionBuilder({
  library,
  strategy,
  setStrategy,
}: {
  library: IndicatorLibrary;
  strategy: StrategyConfig;
  setStrategy: (config: StrategyConfig) => void;
}) {
  const usableIndicators = library.indicators.filter((indicator) => (
    indicator.data_status === 'executable' && (indicator.usage || []).includes('interaction')
  ));
  const indicatorById = useMemo(
    () => Object.fromEntries(library.indicators.map((indicator) => [indicator.id, indicator])),
    [library.indicators],
  );
  const [firstId, setFirstId] = useState(usableIndicators[0]?.id || '');
  const [secondId, setSecondId] = useState(usableIndicators[1]?.id || usableIndicators[0]?.id || '');
  const interactions = Array.isArray(strategy.strategy_interactions) ? strategy.strategy_interactions : [];
  const patchInteractions = (next: StrategyInteraction[]) => {
    setStrategy({ ...strategy, strategy_interactions: next });
  };
  const addInteraction = () => {
    const ids = Array.from(new Set([firstId, secondId].filter(Boolean)));
    if (ids.length < 2) return;
    const conditions = ids
      .map((id) => indicatorById[id])
      .filter((indicator): indicator is IndicatorDefinition => Boolean(indicator))
      .map((indicator) => defaultRuleCondition(indicator));
    patchInteractions([
      ...interactions,
      {
        id: createInteractionId(),
        name: conditions.map((condition) => indicatorById[condition.indicator_id]?.name || condition.indicator_id).join(' + '),
        conditions,
        multiplier: 1.1,
        enabled: true,
      },
    ]);
  };
  const patchInteraction = (id: string, patch: Partial<StrategyInteraction>) => {
    patchInteractions(interactions.map((item) => (item.id === id ? { ...item, ...patch } : item)));
  };
  const removeInteraction = (id: string) => {
    patchInteractions(interactions.filter((item) => item.id !== id));
  };

  return (
    <section className="interaction-builder">
      <div className="interaction-head">
        <div>
          <span className="section-kicker">可选高级项</span>
          <h3>组合倍率</h3>
          <p>当两个确认条件同时命中时，调整最终信号强度。平时可以不填。</p>
        </div>
        <div className="interaction-create">
          <label>
            <span>条件一</span>
            <select value={firstId} onChange={(event) => setFirstId(event.target.value)}>
              {usableIndicators.map((indicator) => (
                <option key={indicator.id} value={indicator.id}>{indicator.name}</option>
              ))}
            </select>
          </label>
          <label>
            <span>条件二</span>
            <select value={secondId} onChange={(event) => setSecondId(event.target.value)}>
              {usableIndicators.map((indicator) => (
                <option key={indicator.id} value={indicator.id}>{indicator.name}</option>
              ))}
            </select>
          </label>
          <button className="primary compact" type="button" disabled={!firstId || !secondId || firstId === secondId} onClick={addInteraction}>
            <Plus size={14} />
            新增组合
          </button>
        </div>
      </div>
      {interactions.length === 0 ? (
        <div className="rule-empty-state compact">
          <strong>还没有组合条件</strong>
          <span>例如：突破上沿距离达标 + 量比放大 + 题材热度高，信号强度 x1.20。</span>
        </div>
      ) : (
        <div className="interaction-list">
          {interactions.map((interaction) => (
            <StrategyInteractionCard
              key={interaction.id}
              interaction={interaction}
              usableIndicators={usableIndicators}
              indicatorById={indicatorById}
              patch={(patch) => patchInteraction(interaction.id, patch)}
              remove={() => removeInteraction(interaction.id)}
            />
          ))}
        </div>
      )}
    </section>
  );
}

function StrategyInteractionCard({
  interaction,
  usableIndicators,
  indicatorById,
  patch,
  remove,
}: {
  interaction: StrategyInteraction;
  usableIndicators: IndicatorDefinition[];
  indicatorById: Record<string, IndicatorDefinition>;
  patch: (patch: Partial<StrategyInteraction>) => void;
  remove: () => void;
}) {
  const updateCondition = (index: number, condition: StrategyRuleCondition) => {
    patch({ conditions: interaction.conditions.map((item, itemIndex) => (itemIndex === index ? condition : item)) });
  };
  const addCondition = () => {
    const nextIndicator = usableIndicators.find((indicator) => !interaction.conditions.some((condition) => condition.indicator_id === indicator.id));
    if (!nextIndicator) return;
    patch({ conditions: [...interaction.conditions, defaultRuleCondition(nextIndicator)] });
  };
  const removeCondition = (index: number) => {
    if (interaction.conditions.length <= 2) return;
    patch({ conditions: interaction.conditions.filter((_, itemIndex) => itemIndex !== index) });
  };
  return (
    <article className={`interaction-card ${interaction.enabled === false ? 'disabled' : ''}`}>
      <header>
        <label>
          <span>名称</span>
          <input value={interaction.name} onChange={(event) => patch({ name: event.target.value })} />
        </label>
        <label>
          <span>效果</span>
          <select value={String(interaction.multiplier || 1.1)} onChange={(event) => patch({ multiplier: Number(event.target.value) })}>
            {interactionMultiplierOptions.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
        </label>
        <label className="rule-enabled-toggle">
          <input type="checkbox" checked={interaction.enabled !== false} onChange={(event) => patch({ enabled: event.target.checked })} />
          启用
        </label>
        <button className="table-action" type="button" onClick={remove} title="移除组合">
          <X size={14} />
        </button>
      </header>
      <div className="interaction-conditions">
        {interaction.conditions.map((condition, index) => {
          const indicator = indicatorById[condition.indicator_id] || usableIndicators[0];
          return (
            <InteractionConditionEditor
              key={`${interaction.id}-${index}-${condition.indicator_id}`}
              condition={condition}
              indicator={indicator}
              indicators={usableIndicators}
              patch={(next) => updateCondition(index, next)}
              remove={() => removeCondition(index)}
              canRemove={interaction.conditions.length > 2}
            />
          );
        })}
      </div>
      <button className="ghost compact add-condition-button" type="button" onClick={addCondition}>
        <Plus size={14} />
        添加指标
      </button>
    </article>
  );
}

function InteractionConditionEditor({
  condition,
  indicator,
  indicators,
  patch,
  remove,
  canRemove,
}: {
  condition: StrategyRuleCondition;
  indicator: IndicatorDefinition;
  indicators: IndicatorDefinition[];
  patch: (condition: StrategyRuleCondition) => void;
  remove: () => void;
  canRemove: boolean;
}) {
  const operators = supportedRuleOperators(indicator, 'filter');
  const operator = operators.includes(condition.operator) ? condition.operator : operators[0] || 'gte';
  const numeric = isNumericIndicator(indicator);
  const setIndicator = (indicatorId: string) => {
    const nextIndicator = indicators.find((item) => item.id === indicatorId) || indicator;
    patch(defaultRuleCondition(nextIndicator));
  };
  const setValue = (key: 'value' | 'value2', value: string) => {
    patch({ ...condition, [key]: value === '' ? null : numeric ? Number(value) : value });
  };
  return (
    <div className="interaction-condition">
      <select value={condition.indicator_id} onChange={(event) => setIndicator(event.target.value)}>
        {indicators.map((item) => (
          <option key={item.id} value={item.id}>{item.name}</option>
        ))}
      </select>
      <select value={operator} onChange={(event) => patch({ ...condition, operator: event.target.value as RuleOperator })}>
        {operators.map((item) => (
          <option key={item} value={item}>{ruleOperatorMeta[item]?.label || item}</option>
        ))}
      </select>
      {operator !== 'is_true' && (
        <div className="rule-value-input">
          <input
            type={numeric ? 'number' : 'text'}
            step={numeric ? ruleInputStep(indicator) : undefined}
            value={String(condition.value ?? '')}
            onChange={(event) => setValue('value', event.target.value)}
            placeholder={ruleValuePlaceholder(indicator)}
          />
          {indicator.unit && <em>{indicator.unit}</em>}
        </div>
      )}
      {operator === 'between' && (
        <div className="rule-value-input">
          <input
            type={numeric ? 'number' : 'text'}
            step={numeric ? ruleInputStep(indicator) : undefined}
            value={String(condition.value2 ?? '')}
            onChange={(event) => setValue('value2', event.target.value)}
          />
          {indicator.unit && <em>{indicator.unit}</em>}
        </div>
      )}
      <button className="table-action" type="button" disabled={!canRemove} onClick={remove} title="移除指标">
        <X size={14} />
      </button>
    </div>
  );
}

function StrategyRuleCard({
  rule,
  indicator,
  patch,
  remove,
}: {
  rule: StrategyRule;
  indicator: IndicatorDefinition;
  patch: (patch: Partial<StrategyRule>) => void;
  remove: () => void;
}) {
  const actions = supportedRuleActions(indicator);
  const action = actions.includes(rule.action) ? rule.action : actions[0] || 'display';
  const operators = supportedRuleOperators(indicator, action);
  const operator = operators.includes(rule.operator) ? rule.operator : operators[0] || 'gte';
  const numeric = isNumericIndicator(indicator);
  const unit = indicator.unit || '';
  const displayOnly = action === 'display';
  const applyAction = (nextAction: RuleAction) => {
    patch({
      action: nextAction,
      operator: nextAction === 'display' ? operator : defaultOperatorForIndicator(indicator),
      value: nextAction === 'display' ? rule.value : defaultValueForIndicator(indicator),
      value2: undefined,
    });
  };
  const setValue = (key: 'value' | 'value2', value: string) => {
    patch({ [key]: value === '' ? null : numeric ? Number(value) : value } as Partial<StrategyRule>);
  };
  const applyRecommendation = (recommendation: NonNullable<IndicatorDefinition['recommended_rules']>[number]) => {
    patch({
      action: recommendation.action,
      operator: recommendation.operator,
      value: recommendation.value ?? rule.value ?? defaultValueForIndicator(indicator),
      value2: recommendation.value2 ?? rule.value2,
      weight: recommendation.weight ?? rule.weight ?? null,
      window_days: recommendation.window_days ?? rule.window_days,
      enabled: true,
    });
  };

  return (
    <article className={`strategy-rule-card ${action} ${rule.enabled === false ? 'disabled' : ''}`}>
      <header>
        <div>
          <strong>{indicator.name}</strong>
          <span>{ruleSummary(rule, indicator)}</span>
        </div>
        <div className="rule-card-actions">
          <label className="rule-enabled-toggle">
            <input type="checkbox" checked={rule.enabled !== false} onChange={(event) => patch({ enabled: event.target.checked })} />
            启用
          </label>
          <button className="table-action" type="button" onClick={remove} title="移除规则">
            <X size={14} />
          </button>
        </div>
      </header>

      <div className="rule-action-row">
        {actions.map((item) => (
          <button key={item} type="button" className={action === item ? 'active' : ''} onClick={() => applyAction(item)}>
            <strong>{ruleActionMeta[item].label}</strong>
            <span>{ruleActionMeta[item].note}</span>
          </button>
        ))}
      </div>

      {!displayOnly ? (
        <>
          <div className="rule-operator-row">
            {operators.map((item) => (
              <button key={item} type="button" className={operator === item ? 'active' : ''} onClick={() => patch({ operator: item })}>
                {ruleOperatorMeta[item]?.label || item}
              </button>
            ))}
          </div>
          <div className="rule-value-grid">
            {operator !== 'is_true' && (
              <label>
                <span>{operator === 'between' ? '下限' : '数值'}</span>
                <div className="rule-value-input">
                  <input
                    type={numeric ? 'number' : 'text'}
                    step={numeric ? ruleInputStep(indicator) : undefined}
                    value={String(rule.value ?? '')}
                    onChange={(event) => setValue('value', event.target.value)}
                    placeholder={ruleValuePlaceholder(indicator)}
                  />
                  {unit && <em>{unit}</em>}
                </div>
              </label>
            )}
            {operator === 'between' && (
              <label>
                <span>上限</span>
                <div className="rule-value-input">
                  <input
                    type={numeric ? 'number' : 'text'}
                    step={numeric ? ruleInputStep(indicator) : undefined}
                    value={String(rule.value2 ?? '')}
                    onChange={(event) => setValue('value2', event.target.value)}
                    placeholder={indicator.range_hint?.max !== undefined ? String(indicator.range_hint.max) : ''}
                  />
                  {unit && <em>{unit}</em>}
                </div>
              </label>
            )}
            {(action === 'score' || action === 'risk') && (
              <label>
                <span>{action === 'risk' ? '扣分' : '权重'}</span>
                <div className="rule-value-input">
                  <input
                    type="number"
                    step="1"
                    value={rule.weight ?? ''}
                    onChange={(event) => patch({ weight: event.target.value === '' ? null : Number(event.target.value) })}
                    placeholder="5"
                  />
                  <em>分</em>
                </div>
              </label>
            )}
          </div>
          <div className="missing-policy-row">
            {missingPolicyOptions.map((option) => (
              <button
                key={option.id}
                type="button"
                className={(rule.missing_policy || 'neutral') === option.id ? 'active' : ''}
                onClick={() => patch({ missing_policy: option.id })}
              >
                {option.label}
              </button>
            ))}
          </div>
        </>
      ) : (
        <div className="display-rule-note">
          <span>{indicator.data_status === 'display_only' ? '已接入数据仓库，尚未进入分析过滤。' : '保存后随候选指标展示，不改变筛选结果。'}</span>
        </div>
      )}

      {(indicator.recommended_rules || []).length > 0 && (
        <div className="rule-recommendations">
          {(indicator.recommended_rules || []).map((recommendation) => (
            <button key={`${recommendation.label}-${recommendation.action}`} type="button" onClick={() => applyRecommendation(recommendation)}>
              {recommendation.label}
            </button>
          ))}
        </div>
      )}
    </article>
  );
}

function SignalRoleChips({
  value,
  onChange,
  compact = false,
}: {
  value: string;
  onChange: (value: string) => void;
  compact?: boolean;
}) {
  return (
    <div className={compact ? 'signal-role-chips compact' : 'signal-role-chips'}>
      {(Object.keys(ruleActionMeta) as RuleAction[]).map((action) => (
        <button
          key={action}
          type="button"
          className={value === action ? 'active' : ''}
          onClick={() => onChange(action)}
          title={ruleActionMeta[action].verb}
        >
          {ruleActionMeta[action].label}
        </button>
      ))}
    </div>
  );
}

function SignalModeFieldForm({
  profile,
  library,
  strategy,
  update,
}: {
  profile: SignalModeTemplate;
  library: IndicatorLibrary;
  strategy: StrategyConfig;
  update: (key: keyof StrategyConfig, value: unknown) => void;
}) {
  const indicatorById = useMemo(
    () => Object.fromEntries(library.indicators.map((indicator) => [indicator.id, indicator])),
    [library.indicators],
  );
  const categoryLabelById = useMemo(
    () => Object.fromEntries(library.categories.map((category) => [category.id, category.label])),
    [library.categories],
  );
  const groups = useMemo(() => {
    const next = new Map<string, { id: string; label: string; fields: Array<{ field: SignalModeField; indicator: IndicatorDefinition }> }>();
    (profile.fields || []).forEach((field) => {
      const indicator = indicatorById[field.indicator_id];
      if (!indicator || indicator.kind !== 'strategy_param' || !indicator.strategy_key) return;
      const id = field.group_id || indicator.group_id || 'other';
      const label = field.group_label || indicator.group_label || '其他';
      if (!next.has(id)) next.set(id, { id, label, fields: [] });
      next.get(id)?.fields.push({ field, indicator });
    });
    return Array.from(next.values());
  }, [indicatorById, profile.fields]);
  const pairedEditableGroups = useMemo(() => {
    const explicitIds = new Set((profile.fields || []).map((field) => field.indicator_id));
    const seen = new Set(explicitIds);
    const next = new Map<string, { id: string; label: string; fields: Array<{ indicator: IndicatorDefinition; source: IndicatorDefinition }> }>();

    (profile.fields || []).forEach((field) => {
      const source = indicatorById[field.indicator_id];
      if (!source || source.kind === 'strategy_param') return;
      pairedStrategyIndicators(source, indicatorById).forEach((indicator) => {
        if (!indicator.strategy_key || seen.has(indicator.id)) return;
        seen.add(indicator.id);
        const id = indicator.category_id || 'paired';
        const label = categoryLabelById[indicator.category_id] || indicator.category_id || '其他';
        if (!next.has(id)) next.set(id, { id, label, fields: [] });
        next.get(id)?.fields.push({ indicator, source });
      });
    });

    return Array.from(next.values());
  }, [categoryLabelById, indicatorById, profile.fields]);
  const rules = profile.rule_groups.flatMap((group) => group.rules.map((rule) => ({ ...rule, groupLabel: group.label })));

  return (
    <>
      <div className="strategy-profile-note wide">
        <strong>{profile.name}</strong>
        <span>{profile.description || profile.note || '按当前策略填写下方运行参数。'}</span>
      </div>
      {groups.length === 0 && pairedEditableGroups.length === 0 && <div className="field-note wide">当前策略只有基础股票池，暂时没有需要填写的运行参数。</div>}
      {groups.map((group) => (
        <Fragment key={group.id}>
          <div className="form-section wide">
            <span>{group.label}</span>
            <small>{formatInt(group.fields.length)} 项</small>
          </div>
          {group.fields.map(({ field, indicator }) => (
            <StrategyIndicatorField
              key={`${profile.id}-${field.indicator_id}`}
              indicator={indicator}
              strategy={strategy}
              update={update}
            />
          ))}
        </Fragment>
      ))}
      {pairedEditableGroups.map((group) => (
        <Fragment key={`paired-${group.id}`}>
          <div className="form-section wide paired-param-section">
            <span>{group.label}</span>
          </div>
          {group.fields.map(({ indicator, source }) => (
            <StrategyIndicatorField
              key={`${profile.id}-${source.id}-${indicator.id}`}
              indicator={indicator}
              strategy={strategy}
              update={update}
            />
          ))}
        </Fragment>
      ))}
      {rules.length > 0 && (
        <div className="strategy-signal-context wide">
          <div>
            <strong>组合条件</strong>
            <div className="context-rule-list">
              {rules.map((rule) => (
                <span key={`${rule.groupLabel}-${rule.id}`}>
                  <em>{signalRuleKindLabel(rule.kind)}</em>
                  {rule.name}
                </span>
              ))}
            </div>
          </div>
        </div>
      )}
    </>
  );
}

function StrategyIndicatorField({
  indicator,
  strategy,
  update,
}: {
  indicator: IndicatorDefinition;
  strategy: StrategyConfig;
  update: (key: keyof StrategyConfig, value: unknown) => void;
}) {
  const key = indicator.strategy_key as keyof StrategyConfig;
  const control = indicator.control || { type: 'readonly' };
  const value = strategy[key] as unknown;
  if (!key) return null;
  if (control.type === 'money') {
    return (
      <MoneyField
        label={indicator.name}
        value={nullableNumber(value)}
        onChange={(next) => update(key, next)}
        allowBlank={Boolean(control.allow_blank)}
      />
    );
  }
  if (control.type === 'number') {
    return (
      <NumberField
        label={indicator.name}
        value={nullableNumber(value)}
        onChange={(next) => update(key, next)}
        allowBlank={Boolean(control.allow_blank)}
        description={indicator.description}
      />
    );
  }
  if (control.type === 'select') {
    const rawOptions = control.options || [];
    const current = value === null || value === undefined ? '' : String(value);
    return (
      <SelectField
        label={indicator.name}
        value={current}
        onChange={(next) => update(key, typeof value === 'number' ? Number(next) : next)}
        options={rawOptions.map((option) => [String(option.value), option.label])}
        description={indicator.description}
      />
    );
  }
  if (control.type === 'boolean') {
    return (
      <label className="toggle strategy-toggle">
        <input
          type="checkbox"
          checked={Boolean(value)}
          onChange={(event) => update(key, event.target.checked)}
        />
        <span>{indicator.name}</span>
      </label>
    );
  }
  return (
    <div className="field-note">
      <strong>{indicator.name}</strong>
      <span>{indicator.description}</span>
    </div>
  );
}

function Results({
  candidates,
  funnel,
  zeroReason,
  runId = null,
  compact = false,
  addToWatchlist,
}: {
  candidates: Candidate[];
  funnel: FunnelStep[];
  zeroReason: string | null;
  runId?: string | null;
  compact?: boolean;
  addToWatchlist?: (payload: Record<string, unknown>) => Promise<void>;
}) {
  if (compact) {
    return <CandidatePanel candidates={candidates} zeroReason={zeroReason} title="最新候选" />;
  }
  return <ReportResults initialCandidates={{ run_id: runId, rows: candidates, funnel, zero_reason: zeroReason }} addToWatchlist={addToWatchlist} />;
}

function ReportResults({
  initialCandidates,
  addToWatchlist,
}: {
  initialCandidates: CandidateBundle;
  addToWatchlist?: (payload: Record<string, unknown>) => Promise<void>;
}) {
  const [groups, setGroups] = useState<AnalysisReportGroup[]>([]);
  const [selectedMode, setSelectedMode] = useState<string>('');
  const [selectedRunId, setSelectedRunId] = useState<string | null>(initialCandidates.run_id);
  const [bundle, setBundle] = useState<CandidateBundle>(initialCandidates);
  const [loadingReports, setLoadingReports] = useState(false);
  const [loadingReport, setLoadingReport] = useState(false);
  const [reportError, setReportError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    async function loadReports() {
      try {
        setLoadingReports(true);
        const result = await api.analysisReports();
        if (!alive) return;
        setGroups(result.groups);
        const flat = flattenReports(result.groups);
        const preferred = flat.find((report) => report.id === initialCandidates.run_id) || flat[0];
        setSelectedMode(preferred?.config?.signal_mode || result.groups[0]?.signal_mode || '');
        setSelectedRunId(preferred?.id || initialCandidates.run_id);
      } catch (error) {
        if (alive) setReportError(error instanceof Error ? error.message : '报告列表读取失败');
      } finally {
        if (alive) setLoadingReports(false);
      }
    }
    loadReports();
    return () => {
      alive = false;
    };
  }, [initialCandidates.run_id]);

  useEffect(() => {
    if (!selectedRunId) {
      setBundle(initialCandidates);
      return;
    }
    if (selectedRunId === initialCandidates.run_id) {
      setBundle(initialCandidates);
    }
    const runToLoad = selectedRunId;
    let alive = true;
    async function loadReport() {
      try {
        setLoadingReport(true);
        const result = await api.analysisReport(runToLoad);
        if (!alive) return;
        setBundle(result.candidates);
        setReportError(null);
      } catch (error) {
        if (alive) setReportError(error instanceof Error ? error.message : '报告读取失败');
      } finally {
        if (alive) setLoadingReport(false);
      }
    }
    loadReport();
    return () => {
      alive = false;
    };
  }, [selectedRunId, initialCandidates]);

  const selectedReports = groups.find((group) => group.signal_mode === selectedMode)?.reports || [];
  const selectedReport = selectedReports.find((report) => report.id === selectedRunId);
  const sourceLabel = selectedReport
    ? `${analysisModeLabel(selectedReport.config?.analysis_mode)} · ${signalModeLabel(selectedReport.config?.signal_mode)}`
    : '分析结果';
  const addRows = addToWatchlist
    ? (rows: Candidate[]) => addToWatchlist({
      source_type: 'analysis',
      source_label: sourceLabel,
      source_summary: selectedReport ? strategySummary(selectedReport.config) : '',
      source_ref: bundle.run_id || selectedRunId || '',
      batch_date: reportDate(selectedReport),
      items: rows.map(candidateWatchlistPayload),
    })
    : undefined;

  return (
    <div className="results-stack">
      <ReportSelector
        groups={groups}
        selectedMode={selectedMode}
        selectedRunId={selectedRunId}
        selectedReport={selectedReport}
        loading={loadingReports || loadingReport}
        error={reportError}
        onModeChange={(mode) => {
          const reports = groups.find((group) => group.signal_mode === mode)?.reports || [];
          setSelectedMode(mode);
          setSelectedRunId(reports[0]?.id || null);
        }}
        onRunChange={setSelectedRunId}
      />
      <CandidatePanel candidates={bundle.rows} zeroReason={bundle.zero_reason} title="候选股票" onAddRows={addRows} />
      <Funnel funnel={bundle.funnel} candidateCount={bundle.rows.length} zeroReason={bundle.zero_reason} />
    </div>
  );
}

function CandidatePanel({
  candidates,
  zeroReason,
  title,
  onAddRows,
}: {
  candidates: Candidate[];
  zeroReason: string | null;
  title: string;
  onAddRows?: (rows: Candidate[]) => void | Promise<void>;
}) {
  const [expandedCode, setExpandedCode] = useState<string | null>(null);
  const [sortPrimary, setSortPrimary] = useState<CandidateSortKey>('signal_score');
  const [sortSecondary, setSortSecondary] = useState<CandidateSortKey>('none');
  const [sortTertiary, setSortTertiary] = useState<CandidateSortKey>('none');
  const sortedCandidates = useMemo(
    () => sortCandidates(candidates, [sortPrimary, sortSecondary, sortTertiary]),
    [candidates, sortPrimary, sortSecondary, sortTertiary],
  );

  return (
    <section className="panel">
      <div className="table-toolbar">
        <PanelTitle icon={<BarChart3 size={18} />} title={title} />
        <div className="toolbar-actions">
          {onAddRows && candidates.length > 0 && (
            <button className="ghost small-action" onClick={() => void onAddRows(candidates)}>
              <Plus size={14} />
              加入本页
            </button>
          )}
          <span className="pill">{formatInt(candidates.length)} 只</span>
        </div>
      </div>
      {candidates.length > 1 && (
        <div className="candidate-sort-bar">
          <span>排序</span>
          <label>
            第一优先
            <select value={sortPrimary} onChange={(event) => setSortPrimary(event.target.value as CandidateSortKey)}>
              {candidateSortOptions.filter((option) => option.value !== 'none').map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </label>
          <label>
            第二优先
            <select value={sortSecondary} onChange={(event) => setSortSecondary(event.target.value as CandidateSortKey)}>
              {candidateSortOptions.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </label>
          <label>
            第三优先
            <select value={sortTertiary} onChange={(event) => setSortTertiary(event.target.value as CandidateSortKey)}>
              {candidateSortOptions.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </label>
        </div>
      )}
      {candidates.length === 0 && <EmptyState text={zeroReason || '暂无候选。'} />}
      {candidates.length > 0 && (
        <div className="table-wrap">
          <table className="candidate-table">
            <thead>
              <tr>
                <th>#</th>
                <th>代码</th>
                <th>名称</th>
                <th>最新价</th>
                <th>涨跌幅</th>
                <th>成交额</th>
                <th>换手率</th>
                <th>振幅</th>
                <th>RPS</th>
                <th>MA</th>
                <th>流通市值</th>
                <th>信号</th>
                <th>阶段</th>
                <th>分数</th>
                <th>细分</th>
                {onAddRows && <th className="sticky-action">入池</th>}
              </tr>
            </thead>
            <tbody>
              {sortedCandidates.map((row, index) => {
                const expanded = expandedCode === row.code;
                const interpretation = candidateInterpretation(row);
                return (
                  <Fragment key={`${row.rank}-${row.code}`}>
                    <tr>
                      <td>{index + 1}</td>
                      <td className="mono">{row.code}</td>
                      <td>
                        <div className="name-action-cell">
                          <div className="name-cell">
                            <strong>{row.name}</strong>
                            <span>{row.reasons?.slice(0, 2).join(' / ')}</span>
                          </div>
                          <ChartAction href={row.chart_url} title="看图" />
                        </div>
                      </td>
                      <td>{formatPrice(row.latest_price)}</td>
                      <td className={toneClass(Number(row.pct_chg || 0))}>{formatPercent(row.pct_chg)}</td>
                      <td>{formatMoney(row.amount)}</td>
                      <td>{formatPercent(row.turnover_rate)}</td>
                      <td>{formatPercentRatio(row.amplitude)}</td>
                      <td>{formatPrice(row.rps20)}</td>
                      <td>{formatPrice(row.ma_short)} / {formatPrice(row.ma_long)}</td>
                      <td>{formatMoney(row.float_market_value)}</td>
                      <td><span className="signal">{row.signal_type}</span></td>
                      <td>
                        <span className={freshnessTagClass(interpretation.freshness_label)}>
                          {interpretation.freshness_label || '-'}
                        </span>
                      </td>
                      <td><strong>{formatPrice(row.signal_score)}</strong></td>
                      <td>
                        <button
                          className={expanded ? 'table-action active' : 'table-action'}
                          onClick={() => setExpandedCode(expanded ? null : row.code)}
                          title="查看子分数"
                        >
                          <BarChart3 size={14} />
                        </button>
                      </td>
                      {onAddRows && (
                        <td className="sticky-action">
                          <button className="table-action" onClick={() => void onAddRows([row])} title="加入观察池">
                            <Plus size={14} />
                          </button>
                        </td>
                      )}
                    </tr>
                    {expanded && (
                      <tr className="candidate-expanded">
                        <td colSpan={onAddRows ? 16 : 15}>
                          <CandidateScoreDetails row={row} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function CandidateScoreDetails({ row }: { row: Candidate }) {
  const breakdown = candidateScoreBreakdown(row);
  const freshness = candidateFreshness(row);
  const interpretation = candidateInterpretation(row);
  const hasBreakdown = Object.values(breakdown).some((value) => value !== null);
  const scoreItems: Array<{ key: keyof typeof breakdown; label: string; note: string }> = [
    { key: 'position', label: '位置', note: '靠近合理买点' },
    { key: 'volume', label: '量能', note: '成交额与放量质量' },
    { key: 'pattern', label: '形态', note: '平台、K线和结构' },
    { key: 'trend', label: '趋势', note: 'RPS、均线与 MACD' },
    { key: 'theme', label: '题材', note: '题材热度和涨停扩散' },
    { key: 'custom_rules', label: '规则', note: '自定义指标规则' },
    { key: 'custom_multiplier', label: '倍率', note: '组合条件命中后的乘数' },
    { key: 'freshness', label: '新鲜度', note: '越靠近触发点越高' },
    { key: 'risk', label: '风险扣分', note: '过热、偏离和追高' },
  ];

  return (
    <div className="candidate-detail-panel">
      {!hasBreakdown ? (
        <EmptyState text="旧报告暂无子分数，重新运行分析后会显示。" />
      ) : (
        <>
          <div className="candidate-readout">
            <div className="candidate-readout-head">
              <span className={freshnessTagClass(interpretation.freshness_label)}>
                {interpretation.freshness_label || '趋势观察'}
              </span>
              <strong>{interpretation.trade_read || '谨慎确认'}</strong>
              <p>{interpretation.conclusion || '综合分进入候选，仍需结合盘口与大盘环境确认。'}</p>
            </div>
            <div className="candidate-readout-grid">
              <div>
                <span>强项</span>
                <ul>
                  {(interpretation.strengths.length ? interpretation.strengths : ['综合条件尚可，主要依靠总分排序进入候选。']).map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
              <div>
                <span>留意</span>
                <ul>
                  {(interpretation.risks.length ? interpretation.risks : ['暂无明显过热项，仍需结合盘口与大盘环境确认。']).map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
          <div className="score-card-grid">
            {scoreItems.map((item) => {
              const value = breakdown[item.key];
              const isRisk = item.key === 'risk';
              const isMultiplier = item.key === 'custom_multiplier';
              const width = isMultiplier
                ? Math.min(Math.abs(Number(value || 1) - 1) / 0.6, 1) * 100
                : Math.min(Math.abs(Number(value || 0)) / (isRisk ? 20 : 30), 1) * 100;
              return (
                <div className={isRisk ? 'score-card risk' : isMultiplier ? 'score-card multiplier' : 'score-card'} key={item.key}>
                  <span>{item.label}</span>
                  <strong>{isMultiplier ? formatMultiplier(value) : formatSignedScore(value, isRisk)}</strong>
                  <div className="score-meter"><i style={{ width: `${width}%` }} /></div>
                  <small>{item.note}</small>
                </div>
              );
            })}
          </div>
          <div className="freshness-grid">
            <MetricMini label="首次突破" value={formatDays(freshness.first_breakout_days)} />
            <MetricMini label="站上平台" value={formatDays(freshness.days_above_platform)} />
            <MetricMini label="突破上沿" value={formatPercentRatio(freshness.breakout_clearance)} />
            <MetricMini label="距平台上沿" value={formatPercentRatio(freshness.distance_to_platform_upper)} />
            <MetricMini label="近5日" value={formatPercentRatio(freshness.recent_gain_5d)} />
            <MetricMini label="均线偏离" value={formatPercentRatio(freshness.ma_distance)} />
          </div>
          {row.reasons?.length > 0 && (
            <div className="candidate-reason-strip">
              {row.reasons.slice(0, 8).map((reason) => <span key={reason}>{reason}</span>)}
            </div>
          )}
        </>
      )}
    </div>
  );
}

function ChartAction({ href, title }: { href?: string | null; title: string }) {
  if (!href) {
    return (
      <span className="table-action disabled" title="暂无看盘链接">
        <CandlestickChart size={14} />
      </span>
    );
  }
  return (
    <a
      className="table-action chart-action"
      href={href}
      target="_blank"
      rel="noreferrer"
      title={title}
      onClick={(event) => event.stopPropagation()}
    >
      <CandlestickChart size={14} />
    </a>
  );
}

function MetricMini({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric-mini">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function ReportSelector({
  groups,
  selectedMode,
  selectedRunId,
  selectedReport,
  loading,
  error,
  onModeChange,
  onRunChange,
}: {
  groups: AnalysisReportGroup[];
  selectedMode: string;
  selectedRunId: string | null;
  selectedReport?: AnalysisReportSummary;
  loading: boolean;
  error: string | null;
  onModeChange: (mode: string) => void;
  onRunChange: (runId: string) => void;
}) {
  const selectedReports = groups.find((group) => group.signal_mode === selectedMode)?.reports || [];
  return (
    <section className="panel report-panel">
      <div className="table-toolbar">
        <PanelTitle icon={<Layers3 size={18} />} title="报告库" />
        <span className={loading ? 'pill' : 'pill good'}>{loading ? '读取中' : '最近 3 份'}</span>
      </div>
      {error && <div className="report-error">{error}</div>}
      <div className="report-mode-tabs">
        {signalModes.map((mode) => {
          const count = groups.find((group) => group.signal_mode === mode.id)?.reports.length || 0;
          return (
            <button
              key={mode.id}
              className={mode.id === selectedMode ? 'active' : ''}
              disabled={count === 0}
              onClick={() => onModeChange(mode.id)}
              type="button"
            >
              <strong>{mode.label}</strong>
              <small>{count ? `${count} 份` : '暂无'}</small>
            </button>
          );
        })}
      </div>
      <div className="report-run-list">
        {selectedReports.length === 0 && <div className="report-empty">这个信号模式还没有完成的分析报告。</div>}
        {selectedReports.map((report) => (
          <button
            key={report.id}
            className={report.id === selectedRunId ? 'report-run active' : 'report-run'}
            onClick={() => onRunChange(report.id)}
            type="button"
          >
            <span>{formatShortDateTime(report.finished_at || report.started_at)}</span>
            <strong>{formatInt(report.summary?.candidate_count ?? 0)} 只</strong>
            <small>{analysisModeLabel(report.config?.analysis_mode)} · {strategySummary(report.config)}</small>
          </button>
        ))}
      </div>
      {selectedReport && (
        <div className="report-current">
          <span>当前报告</span>
          <b>{formatShortDateTime(selectedReport.finished_at || selectedReport.started_at)}</b>
          <small>{selectedReport.id}</small>
        </div>
      )}
    </section>
  );
}

function WatchlistPage({
  result,
  reload,
}: {
  result: WatchlistResult;
  reload: () => Promise<void>;
}) {
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const summary = result.summary || {
    batch_count: 0,
    item_count: 0,
    avg_return_latest: null,
    avg_return_1d: null,
    avg_return_3d: null,
    avg_return_5d: null,
    avg_return_10d: null,
    positive_count: 0,
    positive_rate: null,
    hit_5pct_count: 0,
    hit_8pct_count: 0,
    hit_5pct_rate: null,
    hit_8pct_rate: null,
    worst_drawdown: null,
    best_item: null,
    worst_item: null,
  };

  async function removeBatch(batch: WatchlistBatch) {
    setBusyKey(batch.id);
    try {
      await api.deleteWatchlistBatch(batch.id);
      await reload();
    } finally {
      setBusyKey(null);
    }
  }

  async function removeItem(item: WatchlistItem) {
    const key = `${item.batch_id}-${item.code}`;
    setBusyKey(key);
    try {
      await api.deleteWatchlistItem(item.batch_id, item.code);
      await reload();
    } finally {
      setBusyKey(null);
    }
  }

  async function saveItemMeta(item: WatchlistItem, payload: Record<string, unknown>) {
    const key = `${item.batch_id}-${item.code}-meta`;
    setBusyKey(key);
    try {
      await api.updateWatchlistItem(item.batch_id, item.code, payload);
      await reload();
    } finally {
      setBusyKey(null);
    }
  }

  async function saveBatchMeta(batch: WatchlistBatch, payload: Record<string, unknown>) {
    const key = `${batch.id}-batch-meta`;
    setBusyKey(key);
    try {
      await api.updateWatchlistBatch(batch.id, payload);
      await reload();
    } finally {
      setBusyKey(null);
    }
  }

  return (
    <div className="page-stack watchlist-page">
      <section className="metric-grid">
        <MetricCard label="批次" value={formatInt(summary.batch_count)} sub={`${formatInt(summary.item_count)} 只观察`} icon={<Star size={18} />} />
        <MetricCard label="平均累计" value={formatPercentRatio(summary.avg_return_latest)} sub={`${formatInt(summary.positive_count)} 只为正`} icon={<LineChart size={18} />} />
        <MetricCard label="T+5 均值" value={formatPercentRatio(summary.avg_return_5d)} sub={`T+10 ${formatPercentRatio(summary.avg_return_10d)}`} icon={<Gauge size={18} />} />
        <MetricCard label="+5% 触达" value={formatPercentRatio(summary.hit_5pct_rate)} sub={`最新收盘 ${latestWatchlistDate(result.batches)}`} icon={<Database size={18} />} />
      </section>

      {result.batches.length === 0 ? (
        <section className="panel">
          <PanelTitle icon={<Star size={18} />} title="观察池" />
          <EmptyState text="还没有加入观察股票。" />
        </section>
      ) : (
        result.batches.map((batch) => (
          <section className="panel watchlist-batch" key={batch.id}>
            <div className="watchlist-batch-head">
              <div>
                <span className="eyebrow">{formatDate(batch.batch_date)} · {sourceTypeLabel(batch.source_type)}</span>
                <h3>{batch.name || batch.source_label}</h3>
                <p>{batch.source_label} · {formatInt(batch.item_count)} 只 · 平均累计 {formatPercentRatio(batch.avg_return_latest)}</p>
                {batch.source_summary && <p className="source-summary">{batch.source_summary}</p>}
                <div className="batch-recap">
                  <span>最佳 {batch.best_item ? `${batch.best_item.name} ${formatPercentRatio(batch.best_item.return_latest)}` : '-'}</span>
                  <span>最弱 {batch.worst_item ? `${batch.worst_item.name} ${formatPercentRatio(batch.worst_item.return_latest)}` : '-'}</span>
                </div>
              </div>
              <div className="batch-kpis">
                <span>为正率 <strong>{formatPercentRatio(batch.positive_rate)}</strong></span>
                <span>T+3 <strong>{formatPercentRatio(batch.avg_return_3d)}</strong></span>
                <span>T+5 <strong>{formatPercentRatio(batch.avg_return_5d)}</strong></span>
                <span>+5% <strong>{formatPercentRatio(batch.hit_5pct_rate)}</strong></span>
                <span>最大回撤 <strong>{formatPercentRatio(batch.worst_drawdown)}</strong></span>
                <select
                  className="watchlist-status"
                  value={batch.review_status || '观察中'}
                  disabled={busyKey === `${batch.id}-batch-meta`}
                  onChange={(event) => void saveBatchMeta(batch, { review_status: event.target.value, note: batch.note || '' })}
                >
                  {batchReviewStatuses.map((status) => (
                    <option key={status} value={status}>{status}</option>
                  ))}
                </select>
                <button className="ghost danger-action" disabled={busyKey === batch.id} onClick={() => void removeBatch(batch)}>
                  <Trash2 size={15} />
                  删除批次
                </button>
              </div>
            </div>
            <input
              className="batch-note"
              defaultValue={batch.note || ''}
              placeholder="给这批信号写一句复盘备注"
              disabled={busyKey === `${batch.id}-batch-meta`}
              onBlur={(event) => {
                if (event.target.value !== (batch.note || '')) {
                  void saveBatchMeta(batch, { note: event.target.value, review_status: batch.review_status || '观察中' });
                }
              }}
              onKeyDown={(event) => {
                if (event.key === 'Enter') event.currentTarget.blur();
              }}
            />
            <div className="table-wrap">
              <table className="watchlist-table">
                <thead>
                  <tr>
                    <th>代码</th>
                    <th>名称</th>
                    <th>入池价</th>
                    <th>最新</th>
                    <th>累计</th>
                    <th>T+1</th>
                    <th>T+3</th>
                    <th>T+5</th>
                    <th>T+10</th>
                    <th>最高</th>
                    <th>回撤</th>
                    <th>天数</th>
                    <th>状态</th>
                    <th>备注</th>
                    <th className="sticky-action">删除</th>
                  </tr>
                </thead>
                <tbody>
                  {batch.items.map((item) => (
                    <tr key={`${batch.id}-${item.code}`}>
                      <td className="mono">{item.code}</td>
                      <td>
                        <div className="name-action-cell">
                          <div className="name-cell">
                            <strong>{item.name}</strong>
                            <span>{item.signal_type || batch.source_label} · {item.reasons?.slice(0, 2).join(' / ') || '观察记录'}</span>
                          </div>
                          <ChartAction href={item.chart_url} title="看盘" />
                        </div>
                      </td>
                      <td>{formatPrice(item.entry_price)}</td>
                      <td>
                        <div className="name-cell compact">
                          <strong>{formatPrice(item.latest_close)}</strong>
                          <span>{formatDate(item.latest_date)}</span>
                        </div>
                      </td>
                      <td className={toneClass(Number(item.return_latest || 0))}>{formatPercentRatio(item.return_latest)}</td>
                      <td className={toneClass(Number(item.return_1d || 0))}>{formatPercentRatio(item.return_1d)}</td>
                      <td className={toneClass(Number(item.return_3d || 0))}>{formatPercentRatio(item.return_3d)}</td>
                      <td className={toneClass(Number(item.return_5d || 0))}>{formatPercentRatio(item.return_5d)}</td>
                      <td className={toneClass(Number(item.return_10d || 0))}>{formatPercentRatio(item.return_10d)}</td>
                      <td className={toneClass(Number(item.max_return || 0))}>{formatPercentRatio(item.max_return)}</td>
                      <td className={toneClass(Number(item.max_drawdown || 0))}>{formatPercentRatio(item.max_drawdown)}</td>
                      <td>{formatInt(item.days)}</td>
                      <td>
                        <select
                          className="watchlist-status"
                          value={item.review_status || '观察中'}
                          disabled={busyKey === `${item.batch_id}-${item.code}-meta`}
                          onChange={(event) => void saveItemMeta(item, { review_status: event.target.value, note: item.note || '' })}
                        >
                          {reviewStatuses.map((status) => (
                            <option key={status} value={status}>{status}</option>
                          ))}
                        </select>
                      </td>
                      <td>
                        <input
                          className="watchlist-note"
                          defaultValue={item.note || ''}
                          placeholder="记录走势"
                          disabled={busyKey === `${item.batch_id}-${item.code}-meta`}
                          onBlur={(event) => {
                            if (event.target.value !== (item.note || '')) {
                              void saveItemMeta(item, { note: event.target.value, review_status: item.review_status || '观察中' });
                            }
                          }}
                          onKeyDown={(event) => {
                            if (event.key === 'Enter') {
                              event.currentTarget.blur();
                            }
                          }}
                        />
                      </td>
                      <td className="sticky-action">
                        <button
                          className="table-action danger"
                          disabled={busyKey === `${item.batch_id}-${item.code}`}
                          onClick={() => void removeItem(item)}
                          title="移出观察池"
                        >
                          <Trash2 size={14} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        ))
      )}
    </div>
  );
}

function BacktestPage({
  result,
  task,
  strategy,
  presets,
  startBacktest,
}: {
  result: BacktestResult;
  task: TaskRun | null;
  strategy: StrategyConfig;
  presets: StrategyPreset[];
  startBacktest: (options: Record<string, unknown>, config?: StrategyConfig) => Promise<void>;
}) {
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [step, setStep] = useState('5');
  const [candidateLimit, setCandidateLimit] = useState(String(strategy.candidate_limit || 50));
  const [selectedBacktestStrategyId, setSelectedBacktestStrategyId] = useState('current');
  const [floatPolicy, setFloatPolicy] = useState('allow_missing');
  const [runs, setRuns] = useState<BacktestRun[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [report, setReport] = useState<BacktestResult>(result);
  const running = isTaskActive(task);
  const backtestPresets = presets.filter((preset) => !preset.is_system);
  const selectedPreset = backtestPresets.find((preset) => preset.id === selectedBacktestStrategyId);
  const runStrategy = selectedBacktestStrategyId === 'current' || !selectedPreset ? strategy : selectedPreset.config;
  const runStrategyName = selectedBacktestStrategyId === 'current' || !selectedPreset ? '当前编辑策略' : selectedPreset.name;

  useEffect(() => {
    setCandidateLimit(String(runStrategy.candidate_limit || 50));
  }, [runStrategy.candidate_limit]);

  useEffect(() => {
    if (selectedBacktestStrategyId !== 'current' && !selectedPreset) {
      setSelectedBacktestStrategyId('current');
    }
  }, [selectedBacktestStrategyId, selectedPreset]);

  useEffect(() => {
    async function loadRuns() {
      try {
        const response = await api.backtestRuns();
        setRuns(response.rows || []);
      } catch {
        setRuns([]);
      }
    }
    void loadRuns();
  }, [result?.run?.id, task?.status]);

  useEffect(() => {
    if (!selectedRunId || selectedRunId === result?.run?.id) {
      setReport(result);
    }
  }, [result, selectedRunId]);

  async function selectRun(runId: string) {
    setSelectedRunId(runId);
    setReport(await api.backtestResult(runId));
  }

  async function runBacktest() {
    setSelectedRunId(null);
    await startBacktest({
      start_date: startDate || undefined,
      end_date: endDate || undefined,
      step: Number(step) || 5,
      candidate_limit: Number(candidateLimit) || runStrategy.candidate_limit || 50,
      float_market_value_policy: floatPolicy,
    }, runStrategy);
  }

  return (
    <div className="page-stack">
      <section className="panel backtest-console">
        <div className="table-toolbar">
          <PanelTitle icon={<History size={18} />} title="历史回放" />
          <button className="primary lime" disabled={running} onClick={runBacktest}>
            <Play size={16} />
            开始回测
          </button>
        </div>
        <div className="backtest-form">
          <label className="field">
            <span>回测策略</span>
            <select value={selectedBacktestStrategyId} onChange={(event) => setSelectedBacktestStrategyId(event.target.value)}>
              <option value="current">当前编辑策略</option>
              {backtestPresets.map((preset) => (
                <option key={preset.id} value={preset.id}>{preset.name} · {strategySummary(preset.config)}</option>
              ))}
            </select>
            <small className="field-hint">{runStrategyName} · {strategySummary(runStrategy)}</small>
          </label>
          <label className="field">
            <span>开始日期</span>
            <input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} />
            <small className="field-hint">留空使用最近区间</small>
          </label>
          <label className="field">
            <span>结束日期</span>
            <input type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} />
            <small className="field-hint">留空避开未完成标签</small>
          </label>
          <label className="field">
            <span>采样间隔</span>
            <input inputMode="numeric" value={step} onChange={(event) => setStep(event.target.value)} />
            <small className="field-hint">每隔 N 个交易日回放一次</small>
          </label>
          <label className="field">
            <span>每次候选上限</span>
            <input inputMode="numeric" value={candidateLimit} onChange={(event) => setCandidateLimit(event.target.value)} />
            <small className="field-hint">沿用当前策略，可临时覆盖</small>
          </label>
          <label className="field">
            <span>历史市值缺失</span>
            <select value={floatPolicy} onChange={(event) => setFloatPolicy(event.target.value)}>
              <option value="allow_missing">回测中保留缺失股票</option>
              <option value="latest_proxy">使用最新市值近似</option>
              <option value="strategy">按策略处理</option>
            </select>
            <small className="field-hint">只影响回测，不改变本地数据</small>
          </label>
        </div>
        <div className="backtest-mode-readout">
          <span>{analysisModeLabel(runStrategy.analysis_mode)}</span>
          <b>{strategySummary(runStrategy)}</b>
        </div>
        <TaskStrip task={task} fallback="回测尚未启动" />
      </section>

      <BacktestReportLibrary runs={runs} selectedRunId={report?.run?.id || null} onSelect={selectRun} />
      <BacktestSummary result={report} />
      <BacktestSignals signals={report?.signals || []} />
    </div>
  );
}

function BacktestReportLibrary({
  runs,
  selectedRunId,
  onSelect,
}: {
  runs: BacktestRun[];
  selectedRunId: string | null;
  onSelect: (id: string) => Promise<void>;
}) {
  if (!runs.length) return null;
  return (
    <section className="panel report-library">
      <div className="table-toolbar">
        <PanelTitle icon={<Layers3 size={18} />} title="回测报告库" />
        <span className="pill">最近 {formatInt(runs.length)} 份</span>
      </div>
      <div className="report-strip">
        {runs.map((run) => (
          <button
            key={run.id}
            className={run.id === selectedRunId ? 'active' : ''}
            onClick={() => void onSelect(run.id)}
            type="button"
          >
            <strong>{formatShortDateTime(run.finished_at || run.started_at)}</strong>
            <span>{analysisModeLabel(run.config?.analysis_mode)} · {signalModeLabel(run.config?.signal_mode)}</span>
            <small>{formatDate(run.summary?.start_date)} → {formatDate(run.summary?.end_date)} · {formatInt(run.summary?.signal_count)} 条</small>
          </button>
        ))}
      </div>
    </section>
  );
}

function BacktestSummary({ result }: { result: BacktestResult }) {
  const run = result?.run;
  const summary = run?.summary || {};
  return (
    <section className="backtest-summary-grid">
      <MetricCard label="信号数" value={formatInt(summary.signal_count)} sub={run ? formatShortDateTime(run.finished_at || run.started_at) : '暂无回测'} icon={<History size={18} />} />
      <MetricCard label="10日均值" value={formatPercentRatio(summary.avg_return_10d)} sub={`20日标签 ${formatPercentRatio(summary.label_20d_coverage)}`} icon={<LineChart size={18} />} />
      <MetricCard label="+5% 命中" value={formatPercentRatio(summary.hit_5pct_10d_rate)} sub={`+8% ${formatPercentRatio(summary.hit_8pct_10d_rate)}`} icon={<Star size={18} />} />
      <MetricCard label="10日回撤" value={formatPercentRatio(summary.median_max_drawdown_10d)} sub={`回测日 ${formatInt(summary.evaluated_dates)}`} icon={<ShieldAlert size={18} />} />
      {run && (
        <div className="panel backtest-runline">
          <span className={`status-badge ${run.status}`}>{statusLabel(run.status)}</span>
          <strong>{formatDate(summary.start_date)} → {formatDate(summary.end_date)}</strong>
          <small>每 {formatInt(summary.step)} 个交易日采样 · {analysisModeLabel(run.config?.analysis_mode)}</small>
        </div>
      )}
    </section>
  );
}

function BacktestSignals({ signals }: { signals: BacktestSignal[] }) {
  return (
    <section className="panel">
      <div className="table-toolbar">
        <PanelTitle icon={<BarChart3 size={18} />} title="回测信号" />
        <span className="pill">{formatInt(signals.length)} 条</span>
      </div>
      {signals.length === 0 ? (
        <EmptyState text="暂无回测信号。" />
      ) : (
        <div className="table-wrap">
          <table className="backtest-table">
            <thead>
              <tr>
                <th>信号日</th>
                <th>#</th>
                <th>代码</th>
                <th>名称</th>
                <th>信号</th>
                <th>分数</th>
                <th>入场</th>
                <th>5日</th>
                <th>10日</th>
                <th>20日</th>
                <th>10日最高</th>
                <th>10日回撤</th>
              </tr>
            </thead>
            <tbody>
              {signals.map((row) => (
                <tr key={`${row.run_id}-${row.as_of_date}-${row.code}`}>
                  <td className="mono">{formatDate(row.as_of_date)}</td>
                  <td>{row.rank}</td>
                  <td className="mono">{row.code}</td>
                  <td>
                    <div className="name-cell">
                      <strong>{row.name}</strong>
                      <span>{row.reasons?.slice(0, 2).join(' / ')}</span>
                    </div>
                  </td>
                  <td><span className="signal">{row.signal_type}</span></td>
                  <td><strong>{formatPrice(row.signal_score)}</strong></td>
                  <td>{formatDate(row.entry_date)} · {formatPrice(row.entry_price)}</td>
                  <td className={toneClass(Number(row.return_5d || 0))}>{formatPercentRatio(row.return_5d)}</td>
                  <td className={toneClass(Number(row.return_10d || 0))}>{formatPercentRatio(row.return_10d)}</td>
                  <td className={toneClass(Number(row.return_20d || 0))}>{formatPercentRatio(row.return_20d)}</td>
                  <td className={toneClass(Number(row.max_return_10d || 0))}>{formatPercentRatio(row.max_return_10d)}</td>
                  <td className={toneClass(Number(row.max_drawdown_10d || 0))}>{formatPercentRatio(row.max_drawdown_10d)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function IntradayRadarPage({
  result,
  task,
  runtime,
  startSample,
  saveConfig,
  addToWatchlist,
}: {
  result: IntradayRadarResult;
  task: TaskRun | null;
  runtime: RuntimeHealth;
  startSample: () => Promise<void>;
  saveConfig: (config: IntradayRadarConfig) => Promise<void>;
  addToWatchlist?: (payload: Record<string, unknown>) => Promise<void>;
}) {
  const [config, setConfig] = useState<IntradayRadarConfig>(result.config);
  const [radarMode, setRadarMode] = useState<'strict' | 'score'>('strict');
  const [settingsOpen, setSettingsOpen] = useState(false);
  const running = isTaskActive(task);
  const strictRows = result.strict_rows || result.rows || [];
  const scoreRows = result.score_rows || [];
  const activeRows = radarMode === 'score' ? scoreRows : strictRows;
  const candidateCount = activeRows.length;
  const configSummary = useMemo(() => intradayConfigSummary(config), [config]);

  useEffect(() => {
    setConfig(result.config);
  }, [result.config]);

  const update = (key: keyof IntradayRadarConfig, value: unknown) => {
    setConfig({ ...config, [key]: value });
  };

  return (
    <div className="page-stack intraday-page">
      <section className="panel intraday-console">
        <div className="table-toolbar">
          <PanelTitle icon={<Activity size={18} />} title="盘中雷达" />
          <div className="quick-actions">
            <button className="ghost" onClick={() => saveConfig(config)}>
              <Save size={16} />
              保存设置
            </button>
            <button className="primary lime" disabled={running} onClick={startSample}>
              <Play size={16} />
              采样一次
            </button>
          </div>
        </div>
        <IntradaySlotTimeline slots={runtime.scheduler.slots} />
        <IntradayRunStrip task={task} />
      </section>

      <section className="metric-grid">
        <MetricCard label="最近采样" value={formatChinaLocalDateTime(result.sample_at)} sub="盘中快照时间" icon={<Activity size={18} />} />
        <MetricCard label="样本股票" value={formatInt(result.sample_count)} sub="本次快照覆盖" icon={<Database size={18} />} />
        <MetricCard label="观察" value={formatInt(candidateCount)} sub={radarMode === 'score' ? '综合打分' : '严格筛选'} icon={<Gauge size={18} />} />
        <MetricCard label="状态" value={task?.status === 'queued' ? '排队中' : task?.status === 'running' ? '运行中' : '待命'} sub={task?.stage || '等待采样'} icon={<ShieldAlert size={18} />} />
      </section>

      <section className="panel radar-config-panel">
        <div className="radar-config-head">
          <PanelTitle icon={<Settings2 size={18} />} title="雷达设置" />
          <button className="ghost small-action" onClick={() => setSettingsOpen(!settingsOpen)}>
            {settingsOpen ? '收起参数' : '展开参数'}
          </button>
        </div>
        <div className="radar-config-summary">
          <strong>{configSummary.title}</strong>
          <span>{configSummary.detail}</span>
        </div>
        {settingsOpen && (
          <div className="form-grid radar-form">
            <NumberField label="平台观察天数" value={config.platform_lookback_days} onChange={(value) => update('platform_lookback_days', value || 20)} description="从最近历史 K 线向前取样，不包含盘中快照。" />
            <NumberField label="平台最大振幅" value={config.platform_max_range} onChange={(value) => update('platform_max_range', value || 0)} description={`平台高低区间不超过 ${formatPercentRatio(config.platform_max_range)}。`} />
            <NumberField label="接近上沿距离" value={config.near_upper_distance} onChange={(value) => update('near_upper_distance', value || 0)} description={`未突破时，距离上沿小于 ${formatPercentRatio(config.near_upper_distance)} 会进入观察。`} />
            <NumberField label="突破上沿下限" value={config.breakout_min_clearance} onChange={(value) => update('breakout_min_clearance', value || 0)} description="0 表示刚越过平台上沿即可触发。" />
            <NumberField label="突破上沿上限" value={config.breakout_max_clearance} onChange={(value) => update('breakout_max_clearance', value || 0)} description={`超过 ${formatPercentRatio(config.breakout_max_clearance)} 视为买点偏后。`} />
            <NumberField label="最小当日涨幅" value={config.min_pct_chg} onChange={(value) => update('min_pct_chg', value || 0)} description={`快照涨幅低于 ${formatPercent(config.min_pct_chg)} 会跳过。`} />
            <NumberField label="最大当日涨幅" value={config.max_pct_chg} onChange={(value) => update('max_pct_chg', value || 0)} description={`快照涨幅高于 ${formatPercent(config.max_pct_chg)} 会跳过。`} />
            <MoneyField label="当前累计成交额" value={config.min_amount} onChange={(value) => update('min_amount', value || 0)} />
            <NumberField label="时段量能强度" value={config.min_intraday_amount_ratio} onChange={(value) => update('min_intraday_amount_ratio', value || 0)} description={`1.0 表示符合当前时间点正常成交进度，当前阈值 ${formatRatioX(config.min_intraday_amount_ratio)}。`} />
            <NumberField label="近几日首次突破" value={config.first_breakout_lookback_days} onChange={(value) => update('first_breakout_lookback_days', value || 0)} description="向前检查最近几天，避免已经脱离平台后才入榜。" />
            <NumberField label="前置突破容忍" value={config.first_breakout_max_clearance} onChange={(value) => update('first_breakout_max_clearance', value || 0)} description={`最近几日已高出平台上沿超过 ${formatPercentRatio(config.first_breakout_max_clearance)} 会跳过。`} />
            <NumberField label="贴沿检查天数" value={config.near_upper_recent_days} onChange={(value) => update('near_upper_recent_days', value || 0)} description="确认最近价格一直贴近平台上沿，不是突然从平台底部抽上来。" />
            <NumberField label="贴沿最大距离" value={config.near_upper_recent_distance} onChange={(value) => update('near_upper_recent_distance', value || 0)} description={`最近高点距离平台上沿不超过 ${formatPercentRatio(config.near_upper_recent_distance)}。`} />
            <NumberField label="平台阳线占比" value={config.platform_min_bullish_ratio} onChange={(value) => update('platform_min_bullish_ratio', value || 0)} description={`平台内阳线占比目标 ${formatPercentRatio(config.platform_min_bullish_ratio)}。`} />
            <NumberField label="阳线均额优势" value={config.platform_bull_amount_advantage} onChange={(value) => update('platform_bull_amount_advantage', value || 0)} description={config.platform_bull_amount_advantage ? `阳线日均成交额至少为阴线的 ${formatRatioX(config.platform_bull_amount_advantage)}。` : '0 表示不作为严格门槛。'} />
            <NumberField label="近5日涨幅上限" value={config.max_recent_gain_5d} onChange={(value) => update('max_recent_gain_5d', value || 0)} description={`最近 5 个历史交易日涨幅高于 ${formatPercentRatio(config.max_recent_gain_5d)} 会视为偏后。`} />
            <NumberField label="观察上限" value={config.candidate_limit} onChange={(value) => update('candidate_limit', value || 80)} />
            <label className="toggle">
              <input type="checkbox" checked={config.require_ma_bullish} onChange={(event) => update('require_ma_bullish', event.target.checked)} />
              <span>要求 MA5/10/20 多头</span>
            </label>
            <label className="toggle">
              <input type="checkbox" checked={config.require_macd_strong} onChange={(event) => update('require_macd_strong', event.target.checked)} />
              <span>要求 MACD 强势</span>
            </label>
            <label className="toggle">
              <input type="checkbox" checked={config.exclude_star_board} onChange={(event) => update('exclude_star_board', event.target.checked)} />
              <span>排除科创板</span>
            </label>
          </div>
        )}
      </section>

      <IntradayRadarTable
        rows={activeRows}
        mode={radarMode}
        sampleAt={result.sample_at}
        strictCount={strictRows.length}
        scoreCount={scoreRows.length}
        onModeChange={setRadarMode}
        onAddRows={addToWatchlist
          ? (rows) => addToWatchlist({
            source_type: 'intraday',
            source_label: `盘中雷达 · ${radarMode === 'score' ? '综合打分' : '严格筛选'}`,
            source_summary: `盘中雷达 · ${radarMode === 'score' ? '综合打分' : '严格筛选'} · ${formatChinaLocalDateTime(result.sample_at)}`,
            source_ref: result.sample_at || '',
            batch_date: formatDate(result.sample_at || new Date().toISOString()),
            items: rows.map(intradayWatchlistPayload),
          })
          : undefined}
      />
    </div>
  );
}

function compactSlotWindow(slots: RuntimeSlot[]) {
  const nextIndex = slots.findIndex((slot) => slot.status === 'pending' || slot.status === 'due');
  const latestIndex = slots.reduce((last, slot, index) => (isObservedSlotStatus(slot.status) ? index : last), -1);
  const anchor = nextIndex >= 0 ? nextIndex : latestIndex >= 0 ? latestIndex : 0;
  const start = Math.max(0, anchor - 2);
  const end = Math.min(slots.length, anchor + 3);
  return {
    rows: slots.slice(start, end),
    hiddenBefore: start,
    hiddenAfter: Math.max(0, slots.length - end),
    nextSlot: nextIndex >= 0 ? slots[nextIndex] : null,
    latestSlot: latestIndex >= 0 ? slots[latestIndex] : null,
    remaining: slots.filter((slot) => slot.status === 'pending' || slot.status === 'due').length,
  };
}

function isObservedSlotStatus(status: string) {
  return status === 'completed_full' || status === 'completed_partial' || status === 'queued' || status === 'running';
}

function IntradaySlotTimeline({ slots }: { slots: RuntimeSlot[] }) {
  const compact = compactSlotWindow(slots);
  return (
    <div className="intraday-slot-panel">
      <div className="slot-summary">
        <span>最近 <b>{compact.latestSlot?.time || '-'}</b></span>
        <span>下次 <b>{compact.nextSlot?.time || '-'}</b></span>
        <span>今日还剩 <b>{formatInt(compact.remaining)}</b> 次</span>
      </div>
      <div className="slot-grid intraday-slot-grid compact" aria-label="盘中雷达时间轴">
        {compact.hiddenBefore ? <span className="slot-card muted compressed-slot">+{formatInt(compact.hiddenBefore)}</span> : null}
        {compact.rows.map((slot) => (
          <span key={slot.time} className={`slot-card ${slot.status} ${compact.nextSlot?.time === slot.time ? 'next' : ''}`}>
            <i />
            <b>{slot.time}</b>
            <em>{slotStatusLabel(slot.status)}</em>
            <small>{slot.sample_count ? `${formatInt(slot.sample_count)} 样本` : slot.task_status ? statusLabel(slot.task_status) : '-'}</small>
          </span>
        ))}
        {compact.hiddenAfter ? <span className="slot-card muted compressed-slot">+{formatInt(compact.hiddenAfter)}</span> : null}
      </div>
    </div>
  );
}

function IntradayRunStrip({ task }: { task: TaskRun | null }) {
  if (!task) return <div className="task-strip idle compact-task-strip">盘中采样尚未启动</div>;
  if (task.status === 'queued' || task.status === 'running' || task.status === 'failed') {
    return <TaskStrip task={task} fallback="盘中采样尚未启动" />;
  }
  return (
    <div className="compact-task-strip">
      <span className={`status-badge ${task.status}`}>{statusLabel(task.status)}</span>
      <strong>{task.stage}</strong>
      <small>{task.source || '本地仓库'}</small>
    </div>
  );
}

function intradayConfigSummary(config: IntradayRadarConfig) {
  return {
    title: `${config.platform_lookback_days}日平台 · 区间≤${formatPercentRatio(config.platform_max_range)} · 量能≥${formatRatioX(config.min_intraday_amount_ratio)}`,
    detail: `贴沿${config.near_upper_recent_days}日≤${formatPercentRatio(config.near_upper_recent_distance)} · 首突${config.first_breakout_lookback_days}日≤${formatPercentRatio(config.first_breakout_max_clearance)} · 涨幅 ${formatPercent(config.min_pct_chg)}~${formatPercent(config.max_pct_chg)} · 成交额≥${formatMoney(config.min_amount)} · 阳线均额≥${formatRatioX(config.platform_bull_amount_advantage)}`,
  };
}

function IntradayRadarTable({
  rows,
  mode,
  sampleAt,
  strictCount,
  scoreCount,
  onModeChange,
  onAddRows,
}: {
  rows: IntradayRadarCandidate[];
  mode: 'strict' | 'score';
  sampleAt: string | null;
  strictCount: number;
  scoreCount: number;
  onModeChange: (mode: 'strict' | 'score') => void;
  onAddRows?: (rows: IntradayRadarCandidate[]) => void | Promise<void>;
}) {
  const [expandedCode, setExpandedCode] = useState<string | null>(null);
  const [timeline, setTimeline] = useState<IntradayTimeline | null>(null);
  const [timelineLoading, setTimelineLoading] = useState(false);

  async function toggleTimeline(row: IntradayRadarCandidate) {
    if (expandedCode === row.code) {
      setExpandedCode(null);
      setTimeline(null);
      return;
    }
    setExpandedCode(row.code);
    setTimeline(null);
    setTimelineLoading(true);
    try {
      const tradeDate = formatDate(row.trade_date || row.sample_at);
      const result = await api.intradayTimeline(row.code, tradeDate === '-' ? null : tradeDate);
      setTimeline(result);
    } catch {
      setTimeline({ code: row.code, name: row.name, trade_date: row.trade_date || null, rows: [] });
    } finally {
      setTimelineLoading(false);
    }
  }

  return (
    <section className="panel radar-table-panel">
      <div className="table-toolbar">
        <PanelTitle icon={<BarChart3 size={18} />} title="观察榜" />
        <div className="radar-view-switch" aria-label="观察榜模式">
          <button className={mode === 'strict' ? 'active' : ''} onClick={() => onModeChange('strict')}>
            严格筛选
            <small>{formatInt(strictCount)} 只</small>
          </button>
          <button className={mode === 'score' ? 'active' : ''} onClick={() => onModeChange('score')}>
            综合打分
            <small>{formatInt(scoreCount)} 只</small>
          </button>
        </div>
        <div className="toolbar-actions">
          {onAddRows && rows.length > 0 && (
            <button className="ghost small-action" onClick={() => void onAddRows(rows)}>
              <Plus size={14} />
              加入本榜
            </button>
          )}
          <span className="pill">{formatChinaLocalDateTime(sampleAt)} · {formatInt(rows.length)} 只</span>
        </div>
      </div>
      {rows.length === 0 ? (
        <EmptyState text={mode === 'strict' ? '严格筛选暂无盘中观察信号。' : '综合打分暂无盘中观察信号。'} />
      ) : (
        <div className="table-wrap">
          <table className="radar-table">
            <thead>
              <tr>
                <th>#</th>
                <th>代码</th>
                <th>名称</th>
                <th>状态</th>
                <th>最新价</th>
                <th>涨幅</th>
                <th>距上沿</th>
                <th>突破</th>
                <th>成交额</th>
                <th>本段额</th>
                <th>量能</th>
                <th>分数</th>
                <th>时间线</th>
                {onAddRows && <th className="sticky-action">入池</th>}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const rowKey = `${row.sample_at}-${row.radar_mode}-${row.code}`;
                const expanded = expandedCode === row.code;
                return (
                  <Fragment key={rowKey}>
                    <tr>
                      <td>{row.rank}</td>
                      <td className="mono">{row.code}</td>
                      <td>
                        <div className="name-action-cell">
                          <div className="name-cell">
                            <strong>{row.name}</strong>
                            <span>{row.reasons?.slice(0, 2).join(' / ')}</span>
                          </div>
                          <ChartAction href={row.chart_url} title="看盘" />
                        </div>
                      </td>
                      <td><span className="signal radar-signal">{row.status}</span></td>
                      <td>{formatPrice(row.latest_price)}</td>
                      <td className={toneClass(Number(row.pct_chg || 0))}>{formatPercent(row.pct_chg)}</td>
                      <td>{formatPercentRatio(row.distance_to_upper)}</td>
                      <td className={toneClass(Number(row.breakout_clearance || 0))}>{formatPercentRatio(row.breakout_clearance)}</td>
                      <td>{formatMoney(row.amount)}</td>
                      <td>{formatMoney(row.amount_delta)}</td>
                      <td>{formatRatioX(row.amount_ratio)}</td>
                      <td><strong>{formatPrice(row.radar_score)}</strong></td>
                      <td>
                        <button className={expanded ? 'table-action active' : 'table-action'} onClick={() => void toggleTimeline(row)} title="查看盘中时间线">
                          <History size={14} />
                        </button>
                      </td>
                      {onAddRows && (
                        <td className="sticky-action">
                          <button className="table-action" onClick={() => void onAddRows([row])} title="加入观察池">
                            <Plus size={14} />
                          </button>
                        </td>
                      )}
                    </tr>
                    {expanded && (
                      <tr className="timeline-expanded">
                        <td colSpan={onAddRows ? 14 : 13}>
                          <RadarTimeline timeline={timeline} loading={timelineLoading} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function RadarTimeline({ timeline, loading }: { timeline: IntradayTimeline | null; loading: boolean }) {
  if (loading) {
    return <div className="timeline-panel muted-text">读取盘中轨迹...</div>;
  }
  if (!timeline || timeline.rows.length === 0) {
    return <div className="timeline-panel muted-text">暂无该股票的盘中轨迹。</div>;
  }
  return (
    <div className="timeline-panel">
      <div className="timeline-head">
        <strong>{timeline.name || timeline.code}</strong>
        <span>{timeline.trade_date || '-'} · {formatInt(timeline.rows.length)} 个采样点</span>
      </div>
      <div className="timeline-grid">
        {timeline.rows.map((point) => (
          <span key={point.sample_at} className={point.strict_status || point.score_status ? 'timeline-point active' : 'timeline-point'}>
            <b>{point.sample_at.slice(11, 16)}</b>
            <em>{point.strict_status || point.score_status || '观察外'}</em>
            <small>{formatPrice(point.latest_price)} · {formatRatioX(point.amount_ratio)}</small>
          </span>
        ))}
      </div>
    </div>
  );
}

function DataMap({
  capabilities,
  afterProbe,
  backfillCapability,
  backfillDisabled,
}: {
  capabilities: Capability[];
  afterProbe: () => Promise<void>;
  backfillCapability: (capability: string) => Promise<void>;
  backfillDisabled: boolean;
}) {
  const [probing, setProbing] = useState(false);
  const [backfilling, setBackfilling] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [showNormal, setShowNormal] = useState(false);
  const rows = useMemo(() => buildDataLedgerRows(capabilities), [capabilities]);
  const visibleRows = useMemo(
    () => (showNormal ? rows : rows.filter((row) => row.status !== 'normal')),
    [rows, showNormal],
  );
  const groupedRows = useMemo(() => groupLedgerRows(visibleRows), [visibleRows]);
  const summary = useMemo(
    () => ({
      normal: rows.filter((row) => row.status === 'normal').length,
      stale: rows.filter((row) => row.status === 'stale').length,
      partial: rows.filter((row) => row.status === 'partial').length,
      empty: rows.filter((row) => row.status === 'empty').length,
    }),
    [rows],
  );
  async function probe() {
    try {
      setProbing(true);
      const result = (await api.probeSources()) as { rows: Array<{ status: string }> };
      const available = result.rows.filter((row) => row.status === 'available').length;
      setMessage(`检测完成，${available} 项连接可用`);
      await afterProbe();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : '探测失败');
    } finally {
      setProbing(false);
    }
  }
  async function backfill(capability: string) {
    try {
      setBackfilling(capability);
      await backfillCapability(capability);
      setMessage(`${capability}补齐任务已排队`);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : '补齐启动失败');
    } finally {
      setBackfilling(null);
    }
  }
  return (
    <div className="page-stack">
      <section className="panel data-ledger">
        <div className="data-ledger-head">
          <div>
            <PanelTitle icon={<Layers3 size={18} />} title="数据账本" />
            <p>按数据类检查本地仓库的新鲜度和字段覆盖。</p>
          </div>
          <div className="quick-actions">
            {message && <span className="muted-text">{message}</span>}
            <button className="ghost" onClick={() => setShowNormal((value) => !value)}>
              {showNormal ? '隐藏正常项' : '显示全部'}
            </button>
            <button className="ghost" disabled={probing} onClick={probe}>
              <RefreshCw size={16} />
              刷新状态
            </button>
          </div>
        </div>
        <div className="ledger-summary">
          <span>
            <b>{summary.normal}</b>
            正常
          </span>
          <span>
            <b>{summary.stale}</b>
            落后
          </span>
          <span>
            <b>{summary.partial}</b>
            缺口
          </span>
          <span>
            <b>{summary.empty}</b>
            未接入
          </span>
        </div>
        {visibleRows.length === 0 ? (
          <div className="ledger-all-clear">
            <b>当前没有异常数据项</b>
            <span>需要检查完整账本时可以打开“显示全部”。</span>
          </div>
        ) : (
          <div className="ledger-groups">
            {groupedRows.map((group) => (
              <section className="ledger-group" key={group.key}>
                <div className="ledger-group-head">
                  <div>
                    <strong>{group.label}</strong>
                    <span>{group.description}</span>
                  </div>
                  <b>{group.rows.length}</b>
                </div>
                <div className="data-ledger-table">
                  {group.rows.map((row) => (
                    <div key={row.key} className="data-ledger-row">
                      <div className="ledger-name">
                        <strong>{row.label}</strong>
                        <small>{row.fields}</small>
                      </div>
                      <div className="ledger-date-pair">
                        <span>当前 <b className="mono">{row.currentLatest}</b></span>
                        <span>应该 <b className="mono">{row.expectedLatest}</b></span>
                      </div>
                      <div className="ledger-coverage">
                        <span>{row.coverageText}</span>
                        <Progress value={row.percent} />
                      </div>
                      <div className="ledger-actions">
                        <span className={`ledger-status ${row.status}`}>{row.statusLabel}</span>
                        <button
                          className="mini-action"
                          disabled={!row.canBackfill || backfillDisabled || backfilling === row.key}
                          onClick={() => backfill(row.key)}
                          title={`${row.label}补齐`}
                        >
                          <RotateCcw size={13} />
                          补齐
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function StatusBoard({
  runtime,
  update,
  analyze,
  backtest,
  intraday,
  brief,
  latestAnalysis,
}: {
  runtime: RuntimeHealth;
  update: TaskRun | null;
  analyze: TaskRun | null;
  backtest: TaskRun | null;
  intraday: TaskRun | null;
  brief: TaskRun | null;
  latestAnalysis: unknown;
}) {
  return (
    <div className="page-stack">
      <RuntimeHealthPanel runtime={runtime} />
      <div className="status-grid">
        <section className="panel">
          <PanelTitle icon={<RefreshCw size={18} />} title="数据更新" />
          <TaskDetail task={update} />
        </section>
        <section className="panel">
          <PanelTitle icon={<Play size={18} />} title="运行分析" />
          <TaskDetail task={analyze} />
        </section>
        <section className="panel">
          <PanelTitle icon={<History size={18} />} title="策略回测" />
          <TaskDetail task={backtest} />
        </section>
        <section className="panel">
          <PanelTitle icon={<Activity size={18} />} title="盘中雷达" />
          <TaskDetail task={intraday} />
        </section>
        <section className="panel">
          <PanelTitle icon={<Layers3 size={18} />} title="资讯简报" />
          <TaskDetail task={brief} />
        </section>
        <section className="panel wide-panel">
          <PanelTitle icon={<BarChart3 size={18} />} title="最近分析" />
          <pre className="json-readout">{JSON.stringify(latestAnalysis || {}, null, 2)}</pre>
        </section>
      </div>
    </div>
  );
}

function RuntimeHealthPanel({ runtime }: { runtime: RuntimeHealth }) {
  const dataTokens = [
    { label: '历史', value: runtime.data.latest_history_date || '-' },
    { label: '快照', value: runtime.data.latest_snapshot_date || '-' },
    { label: '盘中', value: formatChinaLocalDateTime(runtime.data.latest_intraday_sample) },
    { label: '简报', value: runtime.data.latest_brief_date || '-' },
  ];
  const nextSlot = runtime.scheduler.next_slot?.time || (runtime.scheduler.is_weekend ? '非交易日' : '-');
  const activeStage = runtime.tasks.latest_intraday?.stage || runtime.tasks.latest_update?.stage || runtime.tasks.latest_analyze?.stage || runtime.tasks.latest_brief?.stage;
  const schedulerState = !runtime.scheduler.enabled ? '定时关闭' : runtime.scheduler.is_weekend ? '周末休眠' : '系统待命';
  const nextAction = runtime.scheduler.enabled ? `下一次盘中采样 ${nextSlot}` : '定时任务未启用';
  const compact = compactSlotWindow(runtime.scheduler.slots);
  return (
    <section className="panel runtime-panel">
      <div className="runtime-head">
        <PanelTitle icon={<ShieldAlert size={18} />} title="数据健康与定时任务" />
        <span className={runtime.scheduler.enabled ? 'pill good' : 'pill muted'}>
          {runtime.scheduler.enabled ? `北京时间 · 下次 ${nextSlot}` : '定时未启用'}
        </span>
      </div>
      <div className="runtime-console">
        <div className="runtime-primary">
          <span>运行中枢</span>
          <strong>{schedulerState}</strong>
          <small>{nextAction}</small>
        </div>
        <div className="runtime-queue">
          <span>任务队列</span>
          <strong>运行 {formatInt(runtime.tasks.running)} · 排队 {formatInt(runtime.tasks.queued)}</strong>
          <small>{activeStage || `补触发窗口 ${formatInt(runtime.scheduler.catchup_minutes)} 分钟`}</small>
        </div>
        <div className="runtime-data-strip">
          {dataTokens.map((item) => (
            <span key={item.label}>
              <em>{item.label}</em>
              <b>{item.value}</b>
            </span>
          ))}
          <span>
            <em>股票池</em>
            <b>{formatInt(runtime.data.stock_count)}</b>
          </span>
        </div>
      </div>
      <div className="slot-summary runtime-slot-summary">
        <span>最近 <b>{compact.latestSlot?.time || '-'}</b></span>
        <span>下次 <b>{compact.nextSlot?.time || '-'}</b></span>
        <span>今日还剩 <b>{formatInt(runtime.scheduler.remaining_count)}</b> 次</span>
        <span>共 <b>{formatInt(runtime.scheduler.slot_count)}</b> 个节点</span>
      </div>
      <div className="slot-grid compact">
        {compact.hiddenBefore ? <span className="slot-card muted compressed-slot">+{formatInt(compact.hiddenBefore)}</span> : null}
        {compact.rows.map((slot) => (
          <span key={slot.time} className={`slot-card ${slot.status} ${runtime.scheduler.next_slot?.time === slot.time ? 'next' : ''}`}>
            <i />
            <b>{slot.time}</b>
            <em>{slotStatusLabel(slot.status)}</em>
            <small>{slot.sample_count ? `${formatInt(slot.sample_count)} 样本` : slot.task_status ? statusLabel(slot.task_status) : '-'}</small>
            {(slot.strict_count || slot.score_count) ? <small>{formatInt(slot.strict_count)} / {formatInt(slot.score_count)}</small> : null}
          </span>
        ))}
        {compact.hiddenAfter ? <span className="slot-card muted compressed-slot">+{formatInt(compact.hiddenAfter)}</span> : null}
      </div>
    </section>
  );
}

function TaskDetail({ task }: { task: TaskRun | null }) {
  if (!task) return <EmptyState text="暂无记录。" />;
  const visual = taskProgressVisual(task);
  const queued = task.status === 'queued';
  const analyzeRunning = task.kind === 'analyze' && task.status === 'running';
  const historyProgress = taskHistoryProgress(task);
  const summaryStats = taskSummaryStats(task);
  const sourceValue = compactTaskText(task.source || '本地缓存');
  const currentValue = compactTaskText(historyProgress ? `${historyProgress.currentDate} · ${historyProgress.step}` : task.current_stock || '-');
  return (
    <div className="task-detail">
      <div className="status-line">
        <span className={`status-badge ${task.status}`}>{statusLabel(task.status)}</span>
        <strong>{task.stage || '等待'}</strong>
      </div>
      <Progress value={visual.value} indeterminate={visual.indeterminate} />
      <div className="task-stats">
        <TaskStatCell label="来源" value={sourceValue.text} title={sourceValue.title} />
        {queued ? (
          <>
            <TaskStatCell label="当前" value="等待前序任务" />
            <TaskStatCell label="进度" value="排队中" />
            <TaskStatCell label="成功" value={formatInt(task.success)} />
            <TaskStatCell label="失败" value={formatInt(task.failed)} />
            <TaskStatCell label="跳过" value={formatInt(task.skipped)} />
          </>
        ) : analyzeRunning ? (
          <>
            <TaskStatCell label="当前阶段" value={task.stage || '准备分析'} />
            <TaskStatCell label="方式" value="批量计算" />
            <TaskStatCell label="进度" value="自动刷新" />
            <TaskStatCell label="结果" value="完成后写入报告" />
            <TaskStatCell label="状态" value="运行中" />
          </>
        ) : (
          <>
            <TaskStatCell label="当前" value={currentValue.text} title={currentValue.title} />
            <TaskStatCell label="进度" value={historyProgress ? `${formatInt(historyProgress.dayIndex)} / ${formatInt(historyProgress.dayTotal)} 个日期` : `${formatInt(task.processed)} / ${formatInt(task.total)}`} />
            <TaskStatCell label="成功" value={formatInt(task.success)} />
            <TaskStatCell label="失败" value={formatInt(task.failed)} />
            <TaskStatCell label="跳过" value={formatInt(task.skipped)} />
          </>
        )}
      </div>
      {historyProgress && (
        <div className={`history-heartbeat ${historyProgress.stale ? 'stale' : ''}`}>
          <span>
            <em>接口</em>
            <b>{historyProgress.step}</b>
          </span>
          <span>
            <em>参考日</em>
            <b>{historyProgress.referenceDate || '-'}</b>
          </span>
          <span>
            <em>已写入</em>
            <b>{formatInt(historyProgress.writtenRows)} 行</b>
          </span>
          <span>
            <em>心跳</em>
            <b>{historyProgress.heartbeatLabel}</b>
          </span>
        </div>
      )}
      {summaryStats.length > 0 && (
        <div className="task-stats">
          {summaryStats.map((item) => (
            <TaskStatCell key={item.label} label={item.label} value={compactTaskText(item.value).text} title={compactTaskText(item.value).title} />
          ))}
        </div>
      )}
      {task.warning && <InlineError text={task.warning} />}
      {task.error_message && <InlineError text={task.error_message} />}
    </div>
  );
}

function TaskStatCell({ label, value, title }: { label: string; value: ReactNode; title?: string }) {
  return (
    <span className="task-stat-cell">
      <em>{label}</em>
      <b title={title}>{value}</b>
    </span>
  );
}

function compactTaskText(value: unknown) {
  const raw = String(value || '-').trim();
  if (!raw || raw === '-') return { text: '-', title: undefined };
  const parts = raw.split(/[,\s]+/).map((part) => part.trim()).filter(Boolean);
  const looksLikeCodeList = parts.length > 2 && parts.every((part) => /^\d{6}\.(SH|SZ|BJ)$/.test(part));
  if (looksLikeCodeList) {
    return {
      text: `${parts.slice(0, 2).join(', ')} 等 ${formatInt(parts.length)} 项`,
      title: raw,
    };
  }
  if (raw.length > 34) {
    return {
      text: `${raw.slice(0, 31)}...`,
      title: raw,
    };
  }
  return { text: raw, title: undefined };
}

function taskHistoryProgress(task: TaskRun) {
  if (task.kind !== 'update') return null;
  const summary = task.summary || {};
  const raw = asRecord(summary.history_progress);
  if (!raw || raw.mode !== 'streaming') return null;
  const dayIndex = nullableNumber(raw.day_index) ?? 0;
  const dayTotal = nullableNumber(raw.day_total) ?? task.total ?? 0;
  const writtenRows = nullableNumber(raw.written_rows) ?? 0;
  const heartbeat = typeof raw.last_heartbeat_at === 'string' ? raw.last_heartbeat_at : '';
  const heartbeatAgeMs = heartbeat ? Date.now() - parseBackendUtc(heartbeat).getTime() : Number.POSITIVE_INFINITY;
  return {
    currentDate: String(raw.current_date || '-'),
    step: String(raw.step || '-'),
    dayIndex,
    dayTotal,
    writtenRows,
    referenceDate: typeof raw.reference_date === 'string' ? raw.reference_date : '',
    heartbeatLabel: formatHeartbeatAge(heartbeatAgeMs),
    stale: task.status === 'running' && heartbeatAgeMs > 45_000,
  };
}

function formatHeartbeatAge(ageMs: number) {
  if (!Number.isFinite(ageMs) || ageMs < 0) return '-';
  const seconds = Math.round(ageMs / 1000);
  if (seconds < 60) return `${seconds} 秒前`;
  const minutes = Math.round(seconds / 60);
  return `${minutes} 分钟前`;
}

function taskSummaryStats(task: TaskRun): Array<{ label: string; value: string }> {
  if (task.kind !== 'update') return [];
  const summary = task.summary || {};
  const stats: Array<{ label: string; value: string }> = [];
  const cleanup = summary.intraday_cleanup;
  if (isRecord(cleanup)) {
    const total = numericObjectTotal(cleanup);
    stats.push({ label: '盘中清理', value: `${formatInt(total)} 条` });
  }
  const enrichment = summary.tushare_enrichment;
  if (isRecord(enrichment)) {
    stats.push({ label: 'Tushare', value: `${formatInt(numericObjectTotal(enrichment))} 行` });
  }
  const floatCount = nullableNumber(summary.float_market_value_count);
  if (floatCount !== null) {
    stats.push({ label: '流通市值', value: `${formatInt(floatCount)} 行` });
  }
  const marketCount = nullableNumber(summary.market_environment_count);
  if (marketCount !== null) {
    stats.push({ label: '市场环境', value: `${formatInt(marketCount)} 日` });
  }
  return stats;
}

function numericObjectTotal(record: Record<string, unknown>) {
  return Object.values(record).reduce<number>((total, value) => {
    const number = nullableNumber(value);
    return total + (number ?? 0);
  }, 0);
}

function Funnel({
  funnel,
  candidateCount,
  zeroReason,
}: {
  funnel: FunnelStep[];
  candidateCount: number;
  zeroReason: string | null;
}) {
  if (!funnel.length) return null;
  const firstCount = funnel[0]?.before_count || 0;
  const finalCount = funnel[funnel.length - 1]?.after_count ?? candidateCount;
  const bottlenecks = [...funnel]
    .filter((step) => step.removed_count > 0)
    .sort((a, b) => b.removed_count - a.removed_count)
    .slice(0, 3);
  const bottleneckNames = new Set(bottlenecks.map((step) => step.step_name));
  const groups = groupFunnelSteps(funnel);
  return (
    <section className="panel analysis-diagnostic">
      <div className="diagnostic-head">
        <PanelTitle icon={<BarChart3 size={18} />} title="分析摘要" />
        <span className={candidateCount > 0 ? 'pill good' : 'pill muted'}>{formatInt(firstCount)} → {formatInt(finalCount)}</span>
      </div>
      <div className="diagnostic-summary">
        <div>
          <span>筛选路径</span>
          <strong>{formatInt(firstCount)} → {formatInt(finalCount)}</strong>
          <small>{zeroReason || '按当前策略完成筛选。'}</small>
        </div>
        <div>
          <span>主要卡点</span>
          <strong>{bottlenecks.length ? bottlenecks.map((step) => step.step_name).join(' / ') : '无明显卡点'}</strong>
          <small>{bottlenecks.length ? '按淘汰数量排序' : '各层过滤较平缓'}</small>
        </div>
      </div>
      <div className="funnel-table" role="table" aria-label="筛选路径">
        <div className="funnel-table-head" role="row">
          <span>条件</span>
          <span>通过</span>
          <span>淘汰</span>
          <span>保留率</span>
          <span />
        </div>
        {groups.map((group) => (
          <div className="funnel-section" key={group.name}>
            <div className="funnel-group-label">{group.name}</div>
            {group.steps.map((step) => {
              const retention = step.before_count ? step.after_count / step.before_count : 1;
              const isBottleneck = bottleneckNames.has(step.step_name);
              return (
                <div key={step.step_name} className={isBottleneck ? 'funnel-row bottleneck' : 'funnel-row'} role="row">
                  <div className="funnel-name">
                    <strong>{step.step_name}</strong>
                    {step.note && <span>{step.note}</span>}
                  </div>
                  <div className="funnel-pass">
                    <span>{formatInt(step.after_count)} / {formatInt(step.before_count)}</span>
                    <i><b style={{ width: `${Math.max(3, Math.min(100, retention * 100))}%` }} /></i>
                  </div>
                  <b className="funnel-loss">{step.removed_count ? `-${formatInt(step.removed_count)}` : '-'}</b>
                  <span>{formatRetainRate(retention)}</span>
                  <em>{isBottleneck ? '主要卡点' : ''}</em>
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </section>
  );
}

function groupFunnelSteps(funnel: FunnelStep[]) {
  const groupOrder = ['股票池', '趋势强弱', '趋势共振', '平台形态', '突破确认', '输出'];
  const groups = new Map<string, FunnelStep[]>();
  for (const step of funnel) {
    const group = funnelGroupName(step.step_name);
    groups.set(group, [...(groups.get(group) || []), step]);
  }
  return groupOrder
    .filter((name) => groups.has(name))
    .map((name) => ({ name, steps: groups.get(name) || [] }));
}

function funnelGroupName(stepName: string) {
  if (stepName.includes('EMA') || stepName.includes('随机指标') || stepName.includes('趋势信号') || stepName === 'MACD 共振') return '趋势共振';
  if (stepName.includes('平台') || stepName.includes('阳线')) return '平台形态';
  if (stepName.includes('突破') || stepName.includes('实体') || stepName.includes('MACD')) return '突破确认';
  if (stepName.includes('候选')) return '输出';
  if (
    stepName.includes('趋势') ||
    stepName.includes('RPS') ||
    stepName.includes('均线') ||
    stepName.includes('振幅') ||
    stepName.includes('涨跌幅') ||
    stepName.includes('成交量')
  ) {
    return '趋势强弱';
  }
  return '股票池';
}

function formatRetainRate(value: number) {
  if (!Number.isFinite(value)) return '100%';
  return `${trimZeros(Math.max(0, Math.min(100, value * 100)))}%`;
}

function MetricCard({ label, value, sub, icon }: { label: string; value: string; sub: string; icon: ReactNode }) {
  return (
    <article className="metric-card">
      <span>{icon}</span>
      <p>{label}</p>
      <strong>{value}</strong>
      <small>{sub}</small>
    </article>
  );
}

function PanelTitle({ icon, title }: { icon: ReactNode; title: string }) {
  return (
    <div className="panel-title">
      {icon}
      <h2>{title}</h2>
    </div>
  );
}

function TaskStrip({ task, fallback }: { task: TaskRun | null; fallback: string }) {
  if (!task) return <div className="task-strip idle">{fallback}</div>;
  const visual = taskProgressVisual(task);
  const detail = compactTaskText(task.status === 'queued' ? '等待前序任务' : task.kind === 'analyze' && task.status === 'running' ? '阶段推进中' : task.current_stock || task.source || '本地缓存');
  return (
    <div className="task-strip">
      <div>
        <span className={`status-badge ${task.status}`}>{statusLabel(task.status)}</span>
        <strong>{task.stage}</strong>
        <small title={detail.title}>{detail.text}</small>
      </div>
      <Progress value={visual.value} indeterminate={visual.indeterminate} />
    </div>
  );
}

function taskProgressVisual(task: TaskRun) {
  if (task.status === 'queued') {
    return { value: 8, indeterminate: false };
  }
  if (task.kind === 'analyze' && task.status === 'running') {
    return { value: 46, indeterminate: true };
  }
  return {
    value: task.total ? Math.round((task.processed / task.total) * 100) : task.status === 'running' ? 18 : 100,
    indeterminate: false,
  };
}

function StatusDot({ task, label }: { task?: TaskRun | null; label: string }) {
  return (
    <span className={`dot ${task?.status || 'idle'}`}>
      <i />
      {label}
    </span>
  );
}

function Progress({ value, indeterminate = false }: { value: number; indeterminate?: boolean }) {
  return (
    <div className={indeterminate ? 'progress indeterminate' : 'progress'} aria-label={indeterminate ? '运行中' : `进度 ${value}%`}>
      <i style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
    </div>
  );
}

function isTaskActive(task?: TaskRun | null) {
  return task?.status === 'queued' || task?.status === 'running';
}

function MoneyField({
  label,
  value,
  onChange,
  allowBlank = false,
}: {
  label: string;
  value: number | null;
  onChange: (value: number | null) => void;
  allowBlank?: boolean;
}) {
  const [draft, setDraft] = useState(value == null ? '' : String(value));
  const [editing, setEditing] = useState(false);
  const parsedDraft = parseMoneyInput(draft);

  useEffect(() => {
    if (!editing) {
      setDraft(value == null ? '' : String(value));
    }
  }, [value, editing]);

  const changeValue = (raw: string) => {
    setDraft(raw);
    if (raw.trim() === '') {
      onChange(allowBlank ? null : 0);
      return;
    }
    const parsed = parseMoneyInput(raw);
    if (parsed !== null) {
      onChange(parsed);
    }
  };

  const hintValue = editing && parsedDraft !== null ? parsedDraft : value;
  const hint = draft.trim() && editing && parsedDraft === null
    ? '无法识别'
    : moneyInputHint(hintValue, allowBlank);

  return (
    <label className="field">
      <span>{label}</span>
      <input
        inputMode="decimal"
        value={editing ? draft : value ?? ''}
        onBlur={() => {
          setEditing(false);
          setDraft(value == null ? '' : String(value));
        }}
        onChange={(event) => changeValue(event.target.value)}
        onFocus={() => setEditing(true)}
        placeholder={allowBlank ? '留空不启用' : undefined}
      />
      <small className={hint === '无法识别' ? 'field-hint danger' : 'field-hint'}>{hint}</small>
    </label>
  );
}

function NumberField({
  label,
  value,
  onChange,
  allowBlank = false,
  description,
}: {
  label: string;
  value: number | null;
  onChange: (value: number | null) => void;
  allowBlank?: boolean;
  description?: ReactNode;
}) {
  const [draft, setDraft] = useState(value == null ? '' : String(value));
  const [editing, setEditing] = useState(false);

  useEffect(() => {
    if (!editing) {
      setDraft(value == null ? '' : String(value));
    }
  }, [value, editing]);

  const changeValue = (raw: string) => {
    setDraft(raw);
    if (raw.trim() === '') {
      onChange(allowBlank ? null : 0);
      return;
    }
    const parsed = Number(raw);
    if (Number.isFinite(parsed)) {
      onChange(parsed);
    }
  };

  return (
    <label className="field">
      <span>{label}</span>
      <input
        inputMode="decimal"
        value={editing ? draft : value ?? ''}
        onBlur={() => {
          setEditing(false);
          setDraft(value == null ? '' : String(value));
        }}
        onChange={(event) => changeValue(event.target.value)}
        onFocus={() => setEditing(true)}
        placeholder={allowBlank ? '留空不启用' : undefined}
      />
      {(allowBlank || description) && (
        <small className="field-hint">{allowBlank ? numberInputHint(value) : description}</small>
      )}
    </label>
  );
}

function SelectField({
  label,
  value,
  options,
  onChange,
  description,
}: {
  label: string;
  value: string;
  options: Array<[string, string]>;
  onChange: (value: string) => void;
  description?: ReactNode;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        {options.map(([optionValue, labelText]) => (
          <option key={optionValue} value={optionValue}>{labelText}</option>
        ))}
      </select>
      {description && <small className="field-hint">{description}</small>}
    </label>
  );
}

function Banner({ tone, text, onClose }: { tone: 'danger' | 'good'; text: string; onClose: () => void }) {
  return (
    <div className={`banner ${tone}`}>
      <span>{text}</span>
      <button onClick={onClose}>关闭</button>
    </div>
  );
}

function InlineError({ text }: { text: string }) {
  return <div className="inline-error">{text}</div>;
}

function EmptyState({ text }: { text: string }) {
  return <div className="empty-state">{text}</div>;
}

function InitialLoading() {
  return (
    <div className="initial">
      <Activity size={22} />
      <span>读取本地状态</span>
    </div>
  );
}

function strategySummary(strategy: StrategyConfig) {
  const rules = Array.isArray(strategy.strategy_rules)
    ? strategy.strategy_rules.filter((rule) => rule.enabled !== false).length
    : 0;
  const interactions = Array.isArray(strategy.strategy_interactions)
    ? strategy.strategy_interactions.filter((interaction) => interaction.enabled !== false).length
    : 0;
  const parts = [
    rules > 0 ? `${rules} 条指标` : '基础参数',
    interactions > 0 ? `${interactions} 个组合倍率` : '',
    `成交额≥${formatMoneyCompact(strategy.min_amount || 0)}`,
    `RPS${strategy.rps_window}`,
    `MA${strategy.ma_short_window}/${strategy.ma_long_window}`,
  ].filter(Boolean);
  return parts.join(' · ');
}

function suggestStrategyName(strategy: StrategyConfig) {
  const analysis = strategy.analysis_mode === 'score' ? '评分' : '严格';
  const rules = Array.isArray(strategy.strategy_rules)
    ? strategy.strategy_rules.filter((rule) => rule.enabled !== false).length
    : 0;
  const interactions = Array.isArray(strategy.strategy_interactions)
    ? strategy.strategy_interactions.filter((interaction) => interaction.enabled !== false).length
    : 0;
  const core = rules > 0 ? `${rules}指标` : `RPS${strategy.rps_window}`;
  const combo = interactions > 0 ? `-${interactions}组合` : '';
  return `自定义策略-${analysis}-${core}${combo}`;
}

function dataHealthHints(bootstrap: Bootstrap) {
  const hints: string[] = [];
  const overview = bootstrap.overview;
  const historyDate = overview.latest_history_date || '';
  const snapshotDate = overview.latest_snapshot_date || '';
  if (isTaskActive(bootstrap.update_status)) {
    hints.push('数据更新正在运行，完成后覆盖情况会自动刷新。');
  }
  if (snapshotDate && historyDate && snapshotDate > historyDate) {
    hints.push(`快照已到 ${snapshotDate}，历史 K 线仍是 ${historyDate}，观察池收益会等收盘 K 线补齐后推进。`);
  } else if (snapshotDate && historyDate && snapshotDate === historyDate) {
    hints.push(`快照与历史 K 线同为 ${historyDate}，当前分析可读取最新收盘数据。`);
  } else if (historyDate) {
    hints.push(`历史 K 线最新到 ${historyDate}，可先分析本地已有数据。`);
  }
  if (bootstrap.intraday?.sample_at) {
    hints.push(`盘中雷达最近采样 ${formatChinaLocalDateTime(bootstrap.intraday.sample_at)}。`);
  }
  if (bootstrap.daily_brief?.generated_at) {
    hints.push(`资讯简报最近生成 ${formatShortDateTime(bootstrap.daily_brief.generated_at)}。`);
  }
  if (Number(overview.turnover_coverage?.percent || 0) < 95) {
    hints.push(`换手率覆盖 ${overview.turnover_coverage.percent}%，缺失股票会按当前策略设置处理。`);
  }
  return hints.slice(0, 3);
}

function parseMoneyInput(raw: string): number | null {
  const value = raw.trim().replace(/,/g, '').replace(/\s+/g, '').toLowerCase();
  if (!value) return null;
  const match = value.match(/^(-?\d+(?:\.\d+)?)(亿|万|w)?$/);
  if (!match) return null;
  const base = Number(match[1]);
  if (!Number.isFinite(base)) return null;
  const unit = match[2];
  if (unit === '亿') return base * 100_000_000;
  if (unit === '万' || unit === 'w') return base * 10_000;
  return base;
}

function moneyInputHint(value: number | null, allowBlank: boolean) {
  if (value == null) return allowBlank ? '当前未参与过滤' : '请输入数值';
  if (value === 0) return '阈值为 0，仍会参与过滤';
  return `≈ ${formatMoneyCompact(value)}`;
}

function numberInputHint(value: number | null) {
  if (value == null) return '当前未参与过滤';
  if (value === 0) return '阈值为 0，仍会参与过滤';
  return `当前阈值：${trimZeros(value)}`;
}

function formatMoneyCompact(value: number) {
  const abs = Math.abs(value);
  if (abs >= 100_000_000) return `${trimZeros(value / 100_000_000)}亿`;
  if (abs >= 10_000) return `${trimZeros(value / 10_000)}万`;
  return trimZeros(value);
}

function trimZeros(value: number) {
  return value.toFixed(2).replace(/\.00$/, '').replace(/(\.\d)0$/, '$1');
}

function formatInt(value: unknown) {
  const number = Number(value || 0);
  return new Intl.NumberFormat('zh-CN').format(number);
}

function formatPrice(value: unknown) {
  if (value === null || value === undefined || value === '') return '-';
  const number = Number(value);
  if (!Number.isFinite(number)) return '-';
  return number.toFixed(2);
}

function boardLabel(value: unknown) {
  const key = String(value || '');
  if (key === 'main') return '主板';
  if (key === 'gem') return '创业板';
  if (key === 'star') return '科创板';
  if (key === 'bj') return '北交所';
  return '-';
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : null;
}

function compactRecords(value: unknown): Array<Record<string, unknown>> {
  if (!Array.isArray(value)) return [];
  return value.reduce<Array<Record<string, unknown>>>((items, item) => {
    const record = asRecord(item);
    if (record) items.push(record);
    return items;
  }, []);
}

function warehouseEventLabel(row: Record<string, unknown>) {
  const pieces = [];
  if (row.latest_limit_type) pieces.push(limitTypeLabel(row.latest_limit_type));
  if (nullableNumber(row.latest_top_net_amount) !== null) pieces.push(`龙虎 ${formatMoney(row.latest_top_net_amount)}`);
  return pieces.length ? pieces.join(' · ') : '普通';
}

function limitTypeLabel(value: unknown) {
  const text = String(value || '').toUpperCase();
  if (text === 'U') return '涨停';
  if (text === 'D') return '跌停';
  if (text === 'Z') return '炸板';
  return text || '-';
}

function indicatorStatusClass(indicator: IndicatorDefinition) {
  if (indicator.status === 'planned') return 'planned';
  if (indicator.analysis_ready) return 'active';
  return 'available';
}

function supportedRuleActions(indicator: IndicatorDefinition): RuleAction[] {
  const actions = (indicator.supported_actions || [])
    .filter((action): action is RuleAction => action in ruleActionMeta);
  return actions.length > 0 ? actions : ['display'];
}

function supportedRuleOperators(indicator: IndicatorDefinition, action: RuleAction): RuleOperator[] {
  if (action === 'display') return [indicator.default_operator || 'gte'];
  const operators = (indicator.supported_operators || [])
    .filter((operator): operator is RuleOperator => operator in ruleOperatorMeta);
  return operators.length > 0 ? operators : ['gte', 'lte', 'between'];
}

function defaultOperatorForIndicator(indicator: IndicatorDefinition): RuleOperator {
  const operators = supportedRuleOperators(indicator, 'filter');
  return (indicator.default_operator && operators.includes(indicator.default_operator))
    ? indicator.default_operator
    : operators[0] || 'gte';
}

function defaultValueForIndicator(indicator: IndicatorDefinition) {
  const recommendation = (indicator.recommended_rules || [])[0];
  if (recommendation?.value !== undefined) return recommendation.value;
  if (indicator.default_operator === 'between' && indicator.range_hint?.min !== undefined) return indicator.range_hint.min;
  return '';
}

function defaultStrategyRule(indicator: IndicatorDefinition): StrategyRule {
  const actions = supportedRuleActions(indicator);
  const action = actions.includes('filter') ? 'filter' : actions[0] || 'display';
  const recommendation = (indicator.recommended_rules || []).find((item) => item.action === action)
    || (indicator.recommended_rules || [])[0];
  const operator = recommendation?.operator || defaultOperatorForIndicator(indicator);
  const missingPolicy = indicator.default_missing_policy === 'skip'
    ? 'skip'
    : indicator.default_missing_policy === 'allow'
      ? 'keep'
      : 'neutral';
  return {
    id: createRuleId(indicator.id),
    indicator_id: indicator.id,
    action,
    operator,
    value: recommendation?.value ?? defaultValueForIndicator(indicator),
    value2: recommendation?.value2 ?? (operator === 'between' ? indicator.range_hint?.max ?? '' : undefined),
    window_days: recommendation?.window_days,
    weight: recommendation?.weight ?? null,
    missing_policy: missingPolicy,
    enabled: true,
  };
}

function defaultRuleCondition(indicator: IndicatorDefinition): StrategyRuleCondition {
  const recommendation = (indicator.recommended_rules || []).find((item) => item.action === 'filter')
    || (indicator.recommended_rules || [])[0];
  const operator = recommendation?.operator || defaultOperatorForIndicator(indicator);
  const missingPolicy = indicator.default_missing_policy === 'skip'
    ? 'skip'
    : indicator.default_missing_policy === 'allow'
      ? 'keep'
      : 'neutral';
  return {
    id: createInteractionConditionId(indicator.id),
    indicator_id: indicator.id,
    operator,
    value: recommendation?.value ?? defaultValueForIndicator(indicator),
    value2: recommendation?.value2 ?? (operator === 'between' ? indicator.range_hint?.max ?? '' : undefined),
    window_days: recommendation?.window_days,
    missing_policy: missingPolicy,
  };
}

function createRuleId(indicatorId: string) {
  const random = typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  return `rule-${indicatorId}-${random}`;
}

function createInteractionId() {
  const random = typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  return `combo-${random}`;
}

function createInteractionConditionId(indicatorId: string) {
  const random = typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  return `combo-condition-${indicatorId}-${random}`;
}

function isNumericIndicator(indicator: IndicatorDefinition) {
  return !['boolean', 'choice', 'event'].includes(String(indicator.value_type || 'number'));
}

function ruleInputStep(indicator: IndicatorDefinition) {
  if (indicator.value_type === 'money') return '1000000';
  if (indicator.value_type === 'percent' || indicator.value_type === 'ratio' || indicator.value_type === 'multiple') return '0.01';
  return '1';
}

function ruleValuePlaceholder(indicator: IndicatorDefinition) {
  const recommendation = (indicator.recommended_rules || [])[0];
  if (recommendation?.value !== undefined) return String(recommendation.value);
  if (indicator.range_hint?.min !== undefined) return String(indicator.range_hint.min);
  if (indicator.value_type === 'score') return '60';
  if (indicator.value_type === 'multiple') return '1.5';
  return '';
}

function indicatorRuleCapabilityLabel(indicator: IndicatorDefinition) {
  if (indicator.data_status === 'display_only') return '只展示';
  return supportedRuleActions(indicator).map((action) => ruleActionMeta[action].label).join(' / ');
}

function ruleSummary(rule: StrategyRule, indicator: IndicatorDefinition) {
  const action = rule.action in ruleActionMeta ? rule.action : 'display';
  if (action === 'display') return ruleActionMeta.display.verb;
  const operator = ruleOperatorMeta[rule.operator]?.summary || rule.operator;
  const unit = indicator.unit || '';
  const left = rule.value === null || rule.value === undefined || rule.value === '' ? '未设定' : `${rule.value}${unit}`;
  if (rule.operator === 'between') {
    const right = rule.value2 === null || rule.value2 === undefined || rule.value2 === '' ? '未设定' : `${rule.value2}${unit}`;
    return `${operator} ${left} - ${right}，${ruleActionMeta[action].verb}`;
  }
  if (rule.operator === 'is_true') return `${operator}，${ruleActionMeta[action].verb}`;
  return `${operator} ${left}，${ruleActionMeta[action].verb}`;
}

function indicatorStatusLabel(indicator: IndicatorDefinition) {
  if (indicator.status === 'planned') return '待接入';
  if (indicator.kind === 'strategy_param') return '可填写';
  if (indicator.analysis_ready) return '分析可用';
  return '观察可用';
}

function indicatorReadinessLabel(indicator: IndicatorDefinition) {
  if (indicator.status === 'planned') return '等待接入';
  if (indicator.kind === 'strategy_param') return '运行时参数';
  if (indicator.analysis_ready) return '已参与过滤/评分';
  return '已接入，可观察配置';
}

function indicatorUsageLabel(values: string[] = []) {
  const labels: Record<string, string> = {
    filter: '过滤',
    score: '加权',
    risk: '扣分',
    sort: '排序',
    display: '展示',
    interaction: '组合',
    context: '环境',
  };
  return values.map((value) => labels[value] || value).join(' / ') || '-';
}

function indicatorKindLabel(indicator: IndicatorDefinition) {
  return indicator.kind === 'strategy_param' ? '可填写参数' : '观察指标';
}

function pairedStrategyIndicators(
  indicator: IndicatorDefinition | undefined,
  indicatorById: Record<string, IndicatorDefinition>,
) {
  if (!indicator?.paired_strategy_ids?.length) return [];
  return indicator.paired_strategy_ids
    .map((id) => indicatorById[id])
    .filter((item): item is IndicatorDefinition => Boolean(item && item.kind === 'strategy_param'));
}

function missingPolicyLabel(value: string) {
  const labels: Record<string, string> = {
    allow: '允许缺失',
    skip: '缺失跳过',
    neutral: '缺失中性',
  };
  return labels[value] || value || '-';
}

function strategyParameterProfile(library: IndicatorLibrary): SignalModeTemplate {
  const fields = library.indicators
    .filter((indicator) => indicator.kind === 'strategy_param')
    .map((indicator) => ({
      indicator_id: indicator.id,
      role: 'filter',
      group_id: indicator.group_id || indicator.category_id,
      group_label: indicator.group_label || indicator.category_id,
    }));
  return {
    id: 'strategy-parameters',
    name: '策略参数',
    description: '当前策略使用的运行参数。',
    note: '',
    runtime_signal_mode: 'breakout_or_pullback',
    fields,
    rule_groups: [],
  };
}

function activeSignalProfile(strategy: StrategyConfig, library: IndicatorLibrary): SignalModeTemplate | null {
  if (strategy.signal_profile) {
    return strategy.signal_profile;
  }
  return library.signal_modes.find((template) => template.id === strategy.signal_mode)
    || library.signal_modes.find((template) => (template.runtime_signal_mode || template.id) === strategy.signal_mode)
    || library.signal_modes[0]
    || null;
}

function cloneSignalProfile(profile: SignalModeTemplate): SignalModeTemplate {
  return JSON.parse(JSON.stringify(profile)) as SignalModeTemplate;
}

function signalRuleKindLabel(kind: IndicatorRule['kind']) {
  const labels: Record<IndicatorRule['kind'], string> = {
    filter: '过滤',
    score: '加分',
    risk: '风控',
    interaction: '组合',
  };
  return labels[kind] || kind;
}

function signalRuleEffectLabel(effect: IndicatorRule['effect']) {
  if (!effect) return '-';
  if (effect.type === 'gate') return `门槛 ${String(effect.value)}`;
  if (effect.type === 'risk') return `风险 ${String(effect.value)}`;
  if (effect.type === 'score') return `评分 ${String(effect.value)}`;
  return `${effect.type} ${String(effect.value)}`;
}

function formatPercent(value: unknown) {
  if (value === null || value === undefined || value === '') return '-';
  const number = Number(value);
  if (!Number.isFinite(number)) return '-';
  return `${number.toFixed(2)}%`;
}

function formatPercentRatio(value: unknown) {
  if (value === null || value === undefined || value === '') return '-';
  const number = Number(value);
  if (!Number.isFinite(number)) return '-';
  return `${(number * 100).toFixed(2)}%`;
}

function formatMoney(value: unknown) {
  if (value === null || value === undefined || value === '') return '-';
  const number = Number(value);
  if (!Number.isFinite(number)) return '-';
  if (Math.abs(number) >= 100_000_000) return `${(number / 100_000_000).toFixed(2)} 亿`;
  if (Math.abs(number) >= 10_000) return `${(number / 10_000).toFixed(2)} 万`;
  return number.toFixed(0);
}

function formatRatioX(value: unknown) {
  const text = formatPrice(value);
  return text === '-' ? '-' : `${text}x`;
}

function formatShortDateTime(value: string | null | undefined) {
  if (!value) return '未完成';
  const date = parseBackendUtc(value);
  if (Number.isNaN(date.getTime())) return value.slice(0, 16);
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(date).replace(/\//g, '-');
}

function formatChinaLocalDateTime(value: string | null | undefined) {
  if (!value) return '-';
  return value.slice(5, 16).replace('T', ' ');
}

function formatDate(value: unknown) {
  if (!value) return '-';
  return String(value).slice(0, 10);
}

function parseBackendUtc(value: string) {
  if (/[zZ]$|[+-]\d{2}:?\d{2}$/.test(value)) return new Date(value);
  return new Date(`${value.replace(' ', 'T')}Z`);
}

function flattenReports(groups: AnalysisReportGroup[]) {
  return groups
    .flatMap((group) => group.reports)
    .sort((a, b) => String(b.finished_at || b.started_at).localeCompare(String(a.finished_at || a.started_at)));
}

function reportDate(report?: AnalysisReportSummary) {
  return formatDate(report?.finished_at || report?.started_at || new Date().toISOString());
}

function sortCandidates(rows: Candidate[], priorities: CandidateSortKey[]) {
  const active = priorities.filter((key) => key !== 'none');
  if (active.length === 0) return rows;
  return [...rows].sort((a, b) => {
    for (const key of active) {
      const left = candidateSortValue(a, key);
      const right = candidateSortValue(b, key);
      if (left !== right) return right - left;
    }
    return Number(a.rank || 0) - Number(b.rank || 0);
  });
}

function candidateSortValue(row: Candidate, key: CandidateSortKey) {
  if (key === 'none') return 0;
  if (key === 'signal_score') return finiteNumber(row.signal_score);
  if (key === 'amount') return finiteNumber(row.amount);
  if (key === 'rps20') return finiteNumber(row.rps20);
  if (key === 'pct_chg') return finiteNumber(row.pct_chg);
  const breakdown = candidateScoreBreakdown(row);
  if (key === 'score_position') return finiteNumber(breakdown.position);
  if (key === 'score_volume') return finiteNumber(breakdown.volume);
  if (key === 'score_pattern') return finiteNumber(breakdown.pattern);
  if (key === 'score_trend') return finiteNumber(breakdown.trend);
  if (key === 'score_theme') return finiteNumber(breakdown.theme);
  if (key === 'score_freshness') return finiteNumber(breakdown.freshness);
  if (key === 'score_risk') return finiteNumber(breakdown.risk);
  return 0;
}

function candidateScoreBreakdown(row: Candidate) {
  const metrics = row.metrics || {};
  const raw = (isRecord(metrics.score_breakdown) ? metrics.score_breakdown : isRecord((row as unknown as Record<string, unknown>).score_breakdown) ? (row as unknown as Record<string, unknown>).score_breakdown : {}) as Record<string, unknown>;
  return {
    position: nullableNumber(raw.position),
    volume: nullableNumber(raw.volume),
    pattern: nullableNumber(raw.pattern),
    trend: nullableNumber(raw.trend),
    theme: nullableNumber(raw.theme),
    freshness: nullableNumber(raw.freshness),
    risk: nullableNumber(raw.risk),
    custom_rules: nullableNumber(raw.custom_rules),
    custom_multiplier: nullableNumber(raw.custom_multiplier),
  };
}

function candidateFreshness(row: Candidate) {
  const metrics = row.metrics || {};
  const raw = (isRecord(metrics.freshness) ? metrics.freshness : isRecord((row as unknown as Record<string, unknown>).freshness) ? (row as unknown as Record<string, unknown>).freshness : {}) as Record<string, unknown>;
  return {
    first_breakout_days: nullableNumber(raw.first_breakout_days),
    days_above_platform: nullableNumber(raw.days_above_platform),
    distance_to_platform_upper: nullableNumber(raw.distance_to_platform_upper),
    breakout_clearance: nullableNumber(raw.breakout_clearance),
    recent_gain_5d: nullableNumber(raw.recent_gain_5d),
    ma_distance: nullableNumber(raw.ma_distance),
  };
}

function candidateInterpretation(row: Candidate) {
  const metrics = row.metrics || {};
  const raw = (isRecord(metrics.interpretation)
    ? metrics.interpretation
    : isRecord((row as unknown as Record<string, unknown>).interpretation)
      ? (row as unknown as Record<string, unknown>).interpretation
      : {}) as Record<string, unknown>;
  return {
    freshness_label: typeof raw.freshness_label === 'string' ? raw.freshness_label : null,
    trade_read: typeof raw.trade_read === 'string' ? raw.trade_read : null,
    conclusion: typeof raw.conclusion === 'string' ? raw.conclusion : null,
    strengths: normalizeStringList(raw.strengths),
    risks: normalizeStringList(raw.risks),
  };
}

function normalizeStringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === 'string' && item.trim().length > 0);
}

function freshnessTagClass(label: string | null) {
  const base = 'freshness-tag';
  if (!label) return base;
  if (label.includes('首日') || label.includes('临界')) return `${base} fresh`;
  if (label.includes('二次') || label.includes('确认')) return `${base} confirm`;
  if (label.includes('走远') || label.includes('后段')) return `${base} late`;
  return base;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === 'object' && !Array.isArray(value));
}

function nullableNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function finiteNumber(value: unknown) {
  return nullableNumber(value) ?? Number.NEGATIVE_INFINITY;
}

function formatSignedScore(value: unknown, isRisk = false) {
  const number = nullableNumber(value);
  if (number === null) return '-';
  if (isRisk && number === 0) return '0.00';
  return number > 0 ? `+${number.toFixed(2)}` : number.toFixed(2);
}

function formatMultiplier(value: unknown) {
  const number = nullableNumber(value);
  if (number === null) return '-';
  return `x${number.toFixed(2)}`;
}

function formatDays(value: unknown) {
  const number = nullableNumber(value);
  if (number === null) return '-';
  return `${Math.round(number)} 天`;
}

function candidateWatchlistPayload(row: Candidate) {
  return {
    code: row.code,
    name: row.name,
    entry_price: row.latest_price,
    signal_score: row.signal_score,
    signal_type: row.signal_type,
    chart_url: row.chart_url,
    reasons: row.reasons || [],
    metrics: {
      pct_chg: row.pct_chg,
      amount: row.amount,
      turnover_rate: row.turnover_rate,
      amplitude: row.amplitude,
      rps20: row.rps20,
      rps60: row.rps60,
      rps120: row.rps120,
      ma_short: row.ma_short,
      ma_long: row.ma_long,
      float_market_value: row.float_market_value,
      ...row.metrics,
    },
  };
}

function intradayWatchlistPayload(row: IntradayRadarCandidate) {
  return {
    code: row.code,
    name: row.name,
    entry_price: row.latest_price,
    signal_score: row.radar_score,
    signal_type: row.status,
    chart_url: row.chart_url,
    reasons: row.reasons || [],
    metrics: {
      radar_mode: row.radar_mode,
      pct_chg: row.pct_chg,
      amount: row.amount,
      distance_to_upper: row.distance_to_upper,
      breakout_clearance: row.breakout_clearance,
      amount_ratio: row.amount_ratio,
      ...row.metrics,
    },
  };
}

function latestWatchlistDate(batches: WatchlistBatch[]) {
  const dates = batches
    .flatMap((batch) => batch.items)
    .map((item) => item.latest_date)
    .filter(Boolean)
    .sort();
  const latest = dates[dates.length - 1];
  return latest ? formatDate(latest) : '-';
}

function sourceTypeLabel(value: string) {
  const labels: Record<string, string> = {
    analysis: '分析',
    intraday: '盘中',
    manual: '手动',
  };
  return labels[value] || value;
}

function analysisModeLabel(mode: string | undefined) {
  return analysisModes.find((item) => item.id === (mode || 'strict'))?.label || '严格筛选';
}

function signalModeLabel(mode: string | undefined) {
  return signalModes.find((item) => item.id === mode)?.label || '策略';
}

function toneClass(value: number) {
  if (value > 0) return 'up';
  if (value < 0) return 'down';
  return '';
}

function statusLabel(status: string) {
  const labels: Record<string, string> = {
    queued: '排队中',
    running: '运行中',
    completed_full: '完整完成',
    completed_partial: '部分完成',
    failed: '失败',
    skipped: '跳过',
  };
  return labels[status] || status;
}

function slotStatusLabel(status: string) {
  const labels: Record<string, string> = {
    pending: '等待',
    due: '待触发',
    missed: '已错过',
    weekend: '休眠',
    disabled: '关闭',
    queued: '排队',
    running: '运行',
    completed_full: '完成',
    completed_partial: '部分',
    failed: '失败',
    skipped: '跳过',
  };
  return labels[status] || status;
}

type DataLedgerStatus = 'normal' | 'stale' | 'partial' | 'empty';
type ExpectedDateKind = 'history' | 'snapshot' | 'long_lived' | 'as_needed';
type CoverageKind = 'stock' | 'event' | 'dataset';
type DataLedgerGroupKey = 'core' | 'daily' | 'event' | 'structure' | 'context';

interface DataLedgerRow {
  key: string;
  label: string;
  group: DataLedgerGroupKey;
  fields: string;
  currentLatest: string;
  expectedLatest: string;
  coverage: number;
  total: number;
  percent: number;
  coverageText: string;
  status: DataLedgerStatus;
  statusLabel: string;
  canBackfill: boolean;
}

const dataLedgerGroupMeta: Record<DataLedgerGroupKey, { label: string; description: string }> = {
  core: { label: '基础行情', description: '股票池、快照、历史 K 线和衍生行情字段' },
  daily: { label: '日频增强', description: 'Tushare 日线增强指标、资金流和技术因子' },
  event: { label: '事件数据', description: '涨跌停、龙虎榜、游资等低覆盖但高信息密度数据' },
  structure: { label: '结构关系', description: '概念、行业、筹码等横截面标签' },
  context: { label: '市场上下文', description: '大盘环境与本地宽度诊断' },
};

const dataLedgerMeta: Record<string, { fields: string[]; expected: ExpectedDateKind; coverageKind?: CoverageKind; group: DataLedgerGroupKey }> = {
  '历史 K 线': {
    fields: ['code', 'date', 'open', 'high', 'low', 'close', 'volume', 'amount', 'turn'],
    expected: 'history',
    group: 'core',
  },
  当天行情快照: {
    fields: ['code', 'date', 'name', 'latest_price', 'pct_chg', 'volume', 'amount'],
    expected: 'snapshot',
    group: 'core',
  },
  股票基础信息: {
    fields: ['code', 'name', 'exchange', 'list_date', 'is_active'],
    expected: 'long_lived',
    group: 'core',
  },
  流通市值: {
    fields: ['code', 'date', 'float_share', 'float_market_value', 'price'],
    expected: 'history',
    group: 'core',
  },
  换手率: {
    fields: ['code', 'date', 'turn', 'turnover_rate'],
    expected: 'history',
    group: 'core',
  },
  RPS: {
    fields: ['code', 'date', 'rps20', 'rps60', 'rps120'],
    expected: 'history',
    group: 'core',
  },
  振幅: {
    fields: ['code', 'date', 'high', 'low', 'prev_close', 'amplitude'],
    expected: 'history',
    group: 'core',
  },
  'ST / 停牌状态': {
    fields: ['code', 'date', 'is_st', 'tradestatus'],
    expected: 'history',
    group: 'core',
  },
  市场环境: {
    fields: ['date', 'trend_score', 'breadth_score', 'risk_level'],
    expected: 'as_needed',
    coverageKind: 'dataset',
    group: 'context',
  },
  每日指标: {
    fields: ['code', 'date', 'turnover_rate', 'volume_ratio', 'circ_mv'],
    expected: 'history',
    group: 'daily',
  },
  技术因子: {
    fields: ['code', 'date', 'macd', 'kdj', 'rsi', 'boll'],
    expected: 'history',
    group: 'daily',
  },
  资金流向: {
    fields: ['code', 'date', 'net_mf_amount', 'buy_lg_amount'],
    expected: 'history',
    group: 'daily',
  },
  涨跌停: {
    fields: ['code', 'trade_date', 'limit_type', 'open_times', 'fd_amount'],
    expected: 'history',
    coverageKind: 'event',
    group: 'event',
  },
  筹码分布: {
    fields: ['code', 'trade_date', 'winner_rate', 'cost_50pct'],
    expected: 'history',
    group: 'structure',
  },
  '概念/行业成分': {
    fields: ['code', 'ts_code', 'con_name', 'source'],
    expected: 'as_needed',
    group: 'structure',
  },
  '龙虎榜/游资': {
    fields: ['code', 'trade_date', 'net_amount', 'hm_name'],
    expected: 'as_needed',
    coverageKind: 'event',
    group: 'event',
  },
};

function buildDataLedgerRows(capabilities: Capability[]): DataLedgerRow[] {
  return capabilities.map((capability) => {
    const meta = dataLedgerMeta[capability.capability] || {
      fields: ['code', 'date', 'value'],
      expected: 'history' as ExpectedDateKind,
      group: 'daily' as DataLedgerGroupKey,
    };
    const coverageKind = meta.coverageKind || 'stock';
    const total = coverageKind === 'stock' ? capability.coverage_count + capability.missing_count : capability.coverage_count;
    const percent = total ? Math.round((capability.coverage_count / total) * 100) : 0;
    const currentLatest = capability.latest_update ? formatDate(capability.latest_update) : '暂无';
    const expectedLatest = expectedLatestLabel(meta.expected);
    const status = classifyLedgerStatus(capability.coverage_count, percent, currentLatest, expectedLatest, coverageKind);
    return {
      key: capability.capability,
      label: capability.capability,
      group: meta.group,
      fields: meta.fields.join(' · '),
      currentLatest,
      expectedLatest,
      coverage: capability.coverage_count,
      total,
      percent,
      coverageText: ledgerCoverageText(capability.coverage_count, total, coverageKind),
      status,
      statusLabel: ledgerStatusLabel(status),
      canBackfill: capability.can_backfill || (capability.capability in dataLedgerMeta),
    };
  });
}

function groupLedgerRows(rows: DataLedgerRow[]) {
  const priority: Record<DataLedgerStatus, number> = { empty: 0, stale: 1, partial: 2, normal: 3 };
  return (Object.keys(dataLedgerGroupMeta) as DataLedgerGroupKey[])
    .map((key) => ({
      key,
      ...dataLedgerGroupMeta[key],
      rows: rows
        .filter((row) => row.group === key)
        .sort((a, b) => priority[a.status] - priority[b.status] || a.label.localeCompare(b.label, 'zh-Hans-CN')),
    }))
    .filter((group) => group.rows.length > 0);
}

function expectedLatestLabel(kind: ExpectedDateKind) {
  if (kind === 'long_lived') return '长期有效';
  if (kind === 'as_needed') return '按需';
  return expectedMarketDate(kind);
}

function classifyLedgerStatus(
  coverage: number,
  percent: number,
  currentLatest: string,
  expectedLatest: string,
  coverageKind: CoverageKind,
): DataLedgerStatus {
  if (coverage <= 0) return 'empty';
  if (isDateLabel(currentLatest) && isDateLabel(expectedLatest) && currentLatest < expectedLatest) return 'stale';
  if (coverageKind !== 'stock') return 'normal';
  if (percent < 98) return 'partial';
  return 'normal';
}

function ledgerCoverageText(coverage: number, total: number, coverageKind: CoverageKind) {
  if (coverageKind === 'event') return `${formatInt(coverage)} 事件`;
  if (coverageKind === 'dataset') return `${formatInt(coverage)} 日`;
  return `${formatInt(coverage)} / ${formatInt(total)}`;
}

function ledgerStatusLabel(status: DataLedgerStatus) {
  const labels: Record<DataLedgerStatus, string> = {
    normal: '正常',
    stale: '落后',
    partial: '缺口',
    empty: '未接入',
  };
  return labels[status];
}

function isDateLabel(value: string) {
  return /^\d{4}-\d{2}-\d{2}$/.test(value);
}

function expectedMarketDate(kind: 'history' | 'snapshot') {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(new Date());
  const byType = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  const today = `${byType.year}-${byType.month}-${byType.day}`;
  const todayDate = new Date(`${today}T00:00:00Z`);
  const day = todayDate.getUTCDay();
  const minuteOfDay = Number(byType.hour) * 60 + Number(byType.minute);
  const threshold = kind === 'snapshot' ? 9 * 60 + 30 : 15 * 60 + 30;
  if (day >= 1 && day <= 5 && minuteOfDay >= threshold) return today;
  return previousWeekday(todayDate);
}

function previousWeekday(date: Date) {
  const copy = new Date(date);
  do {
    copy.setUTCDate(copy.getUTCDate() - 1);
  } while (copy.getUTCDay() === 0 || copy.getUTCDay() === 6);
  return copy.toISOString().slice(0, 10);
}

function coveragePercent(capability: Capability) {
  const total = capability.coverage_count + capability.missing_count;
  if (!total) return 0;
  return Math.round((capability.coverage_count / total) * 100);
}

function sourceList(sources: string[]) {
  return sources.length ? sources.join(' / ') : '暂无';
}

createRoot(document.getElementById('root')!).render(<App />);
