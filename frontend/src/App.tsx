import { useEffect, useMemo, useState } from 'react';
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
} from 'lucide-react';

import { api } from './api';
import type {
  Bootstrap,
  BacktestResult,
  BacktestRun,
  BacktestSignal,
  Candidate,
  CandidateBundle,
  Capability,
  IntradayRadarCandidate,
  IntradayRadarConfig,
  IntradayRadarResult,
  AnalysisReportGroup,
  AnalysisReportSummary,
  FunnelStep,
  StrategyConfig,
  StrategyPreset,
  TaskRun,
  WatchlistBatch,
  WatchlistItem,
  WatchlistResult,
} from './types';
import './styles.css';

type Tab = 'overview' | 'warehouse' | 'strategy' | 'intraday' | 'results' | 'watchlist' | 'backtest' | 'map' | 'status';
type UpdateMode = 'full' | 'daily_light';

const navItems: Array<{ id: Tab; label: string; icon: ReactNode }> = [
  { id: 'overview', label: '总览', icon: <Gauge size={17} /> },
  { id: 'warehouse', label: '数据仓库', icon: <Database size={17} /> },
  { id: 'strategy', label: '策略', icon: <SlidersHorizontal size={17} /> },
  { id: 'intraday', label: '盘中雷达', icon: <Activity size={17} /> },
  { id: 'results', label: '分析结果', icon: <BarChart3 size={17} /> },
  { id: 'watchlist', label: '观察池', icon: <Star size={17} /> },
  { id: 'backtest', label: '回测', icon: <History size={17} /> },
  { id: 'map', label: '数据地图', icon: <Layers3 size={17} /> },
  { id: 'status', label: '运行状态', icon: <Workflow size={17} /> },
];

const signalModes: Array<{ id: string; label: string; sub: string }> = [
  { id: 'breakout_or_pullback', label: '突破或回踩', sub: '双形态' },
  { id: 'breakout', label: '右侧突破', sub: '放量上攻' },
  { id: 'pullback', label: '左侧回踩', sub: '趋势低吸' },
  { id: 'platform_breakout', label: '平台突破', sub: '压缩放量' },
  { id: 'platform_setup', label: '平台临界', sub: '贴近上沿' },
];

const analysisModes: Array<{ id: string; label: string; sub: string }> = [
  { id: 'strict', label: '严格筛选', sub: '逐层淘汰，条件必须同时满足' },
  { id: 'score', label: '综合评分', sub: '基础合格后按信号强弱排序' },
];

const conditionModes: Array<[string, string]> = [
  ['must', '必须满足'],
  ['score', '只参与得分'],
  ['off', '不启用'],
];

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

  useEffect(() => {
    if (!updateRunning && !analyzeRunning && !backtestRunning && !intradayRunning) return;
    const timer = window.setInterval(() => void load(true), 2200);
    return () => window.clearInterval(timer);
  }, [updateRunning, analyzeRunning, backtestRunning, intradayRunning]);

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
    if (tab === 'strategy') {
      return (
        <StrategyPanel
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
      return <DataMap capabilities={bootstrap.capabilities} afterProbe={() => load(true)} />;
    }
    return <StatusBoard update={bootstrap.update_status} analyze={bootstrap.analyze_status} backtest={bootstrap.backtest_status} intraday={bootstrap.intraday_status} latestAnalysis={bootstrap.latest_analysis} />;
  }, [bootstrap, tab, strategy, strategyName, selectedPresetId]);

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
  if (config.signal_mode !== 'platform_breakout') return config;
  return {
    ...config,
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

      <Results candidates={bootstrap.candidates.rows.slice(0, 8)} funnel={bootstrap.candidates.funnel} zeroReason={bootstrap.candidates.zero_reason} compact />
    </div>
  );
}

function Warehouse() {
  const [rows, setRows] = useState<Array<Record<string, unknown>>>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [search, setSearch] = useState('');
  const [error, setError] = useState<string | null>(null);
  const limit = 40;

  async function load() {
    try {
      const data = (await api.stocks(limit, offset, search)) as { rows: Array<Record<string, unknown>>; total: number };
      setRows(data.rows);
      setTotal(data.total);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : '数据仓库加载失败');
    }
  }

  useEffect(() => {
    void load();
  }, [offset, search]);

  return (
    <div className="page-stack">
      <section className="panel">
        <div className="table-toolbar">
          <PanelTitle icon={<Database size={18} />} title="本地股票仓" />
          <input className="search" placeholder="代码 / 名称" value={search} onChange={(event) => { setOffset(0); setSearch(event.target.value); }} />
        </div>
        {error && <InlineError text={error} />}
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>代码</th>
                <th>名称</th>
                <th>交易所</th>
                <th>最新价</th>
                <th>涨跌幅</th>
                <th>成交额</th>
                <th>换手率</th>
                <th>历史天数</th>
                <th>流通市值</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 ? (
                <tr><td colSpan={9} className="empty-cell">暂无本地股票数据</td></tr>
              ) : rows.map((row) => (
                <tr key={String(row.code)}>
                  <td className="mono">{String(row.code || '')}</td>
                  <td>{String(row.name || '')}</td>
                  <td>{String(row.exchange || '')}</td>
                  <td>{formatPrice(row.latest_price)}</td>
                  <td className={toneClass(Number(row.pct_chg || 0))}>{formatPercent(row.pct_chg)}</td>
                  <td>{formatMoney(row.amount)}</td>
                  <td>{formatPercent(row.turnover_rate)}</td>
                  <td>{formatInt(row.history_days)}</td>
                  <td>{formatMoney(row.float_market_value)}</td>
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
    </div>
  );
}

function StrategyPanel(props: {
  presets: StrategyPreset[];
  selectedPresetId: string | null;
  strategy: StrategyConfig;
  strategyName: string;
  setStrategy: (config: StrategyConfig) => void;
  setStrategyName: (name: string) => void;
  selectPreset: (preset: StrategyPreset) => void;
  saveStrategy: (setDefault?: boolean) => Promise<void>;
  saveAndRun: () => Promise<void>;
  duplicate: () => Promise<void>;
  createBlank: () => Promise<void>;
  remove: () => Promise<void>;
  reset: () => Promise<void>;
}) {
  const selected = props.presets.find((preset) => preset.id === props.selectedPresetId);
  const customPresets = props.presets.filter((preset) => !preset.is_system);
  const selectedIsTemplate = Boolean(selected?.is_system);
  const update = (key: keyof StrategyConfig, value: unknown) => {
    props.setStrategy({ ...props.strategy, [key]: value });
  };
  const activeAnalysisMode = analysisModes.find((mode) => mode.id === (props.strategy.analysis_mode || 'strict')) || analysisModes[0];
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
              <span>{preset.name}</span>
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
        {selectedIsTemplate && (
          <div className="template-banner">
            保存后会进入“我的策略”。
          </div>
        )}

        <div className="form-grid">
          <label className="field wide">
            <span>策略名称</span>
            <input value={props.strategyName} onChange={(event) => props.setStrategyName(event.target.value)} />
          </label>
          <div className="mode-tabs wide">
            {signalModes.map((mode) => (
              <button
                key={mode.id}
                className={mode.id === props.strategy.signal_mode ? 'active' : ''}
                onClick={() => update('signal_mode', mode.id)}
                type="button"
              >
                <strong>{mode.label}</strong>
                <small>{mode.sub}</small>
              </button>
            ))}
          </div>
          <div className="analysis-mode-tabs wide" aria-label="选股方式">
            {analysisModes.map((mode) => (
              <button
                key={mode.id}
                className={mode.id === (props.strategy.analysis_mode || 'strict') ? 'active' : ''}
                onClick={() => update('analysis_mode', mode.id)}
                type="button"
              >
                <strong>{mode.label}</strong>
                <small>{mode.sub}</small>
              </button>
            ))}
          </div>
          <div className="form-section wide">
            <span>基础股票池</span>
          </div>
          <NumberField label="最低股价" value={props.strategy.min_price} onChange={(value) => update('min_price', value)} />
          <MoneyField label="成交额门槛" value={props.strategy.min_amount} onChange={(value) => update('min_amount', value)} />
          <MoneyField label="最小流通市值" value={props.strategy.min_float_market_value} onChange={(value) => update('min_float_market_value', value)} allowBlank />
          <MoneyField label="最大流通市值" value={props.strategy.max_float_market_value} onChange={(value) => update('max_float_market_value', value)} allowBlank />
          <label className="toggle">
            <input type="checkbox" checked={props.strategy.include_bj} onChange={(event) => update('include_bj', event.target.checked)} />
            <span>包含北交所</span>
          </label>
          <label className="toggle">
            <input type="checkbox" checked={props.strategy.exclude_star_board} onChange={(event) => update('exclude_star_board', event.target.checked)} />
            <span>排除科创板</span>
          </label>

          {props.strategy.signal_mode === 'platform_breakout' && (
            <>
              <div className="form-section wide">
                <span>平台区间</span>
              </div>
              <NumberField label="平台观察天数" value={props.strategy.platform_lookback_days} onChange={(value) => update('platform_lookback_days', value)} description="这就是你说的 15 天窗口；从最新 K 线前一日往前取样，不含最新 K 线。" />
              <SelectField label="平台振幅口径" value={props.strategy.platform_range_basis} onChange={(value) => update('platform_range_basis', value)} options={[['high_low', '最高价 / 最低价'], ['close', '收盘价区间']]} description="最高价/最低价更严格；收盘价区间会忽略盘中长影线。" />
              <SelectField label="平台区间条件" value={props.strategy.platform_max_range_mode} onChange={(value) => update('platform_max_range_mode', value)} options={conditionModes} description="只控制观察天数这段平台是否必须满足。" />
              <NumberField label="平台区间最大振幅" value={props.strategy.platform_max_range} onChange={(value) => update('platform_max_range', value)} description={`平台最高到最低不超过 ${formatPercentRatio(props.strategy.platform_max_range)}。`} />
              <NumberField label="最小阳线占比" value={props.strategy.platform_min_bullish_ratio} onChange={(value) => update('platform_min_bullish_ratio', value)} description={`平台内红柱占比至少 ${formatPercentRatio(props.strategy.platform_min_bullish_ratio)}。`} />
              <NumberField label="阳线占比加分线" value={props.strategy.platform_bullish_ratio_score} onChange={(value) => update('platform_bullish_ratio_score', value)} description={`得分项：达到 ${formatPercentRatio(props.strategy.platform_bullish_ratio_score)} 会提高排序。`} />
              <NumberField label="阳线均量优势" value={props.strategy.platform_bull_volume_advantage} onChange={(value) => update('platform_bull_volume_advantage', value)} description={`平台红柱均量 / 绿柱均量至少 ${formatPrice(props.strategy.platform_bull_volume_advantage)}x。`} />
              <NumberField label="阳线量能加分线" value={props.strategy.platform_bull_volume_advantage_score} onChange={(value) => update('platform_bull_volume_advantage_score', value)} description={`得分项：达到 ${formatPrice(props.strategy.platform_bull_volume_advantage_score)}x 会提高排序。`} />
              <div className="form-section wide">
                <span>突破确认</span>
              </div>
              <NumberField label="突破上沿最小幅度" value={props.strategy.platform_breakout_clearance} onChange={(value) => update('platform_breakout_clearance', value)} description={`最新收盘价高于平台上沿至少 ${formatPercentRatio(props.strategy.platform_breakout_clearance)}。`} />
              <NumberField label="突破上沿最大距离" value={props.strategy.platform_breakout_max_clearance} onChange={(value) => update('platform_breakout_max_clearance', value)} description={`超过 ${formatPercentRatio(props.strategy.platform_breakout_max_clearance)} 通常说明买点偏后。`} />
              <NumberField label="突破量比" value={props.strategy.platform_breakout_volume_ratio} onChange={(value) => update('platform_breakout_volume_ratio', value)} description={`最新成交量 / 平台均量至少 ${formatPrice(props.strategy.platform_breakout_volume_ratio)}x。`} />
              <NumberField label="突破涨幅下限" value={props.strategy.platform_breakout_pct_chg_min} onChange={(value) => update('platform_breakout_pct_chg_min', value)} description={`最新 K 线涨幅至少 ${formatPercent(props.strategy.platform_breakout_pct_chg_min)}。`} />
              <NumberField label="突破实体强度" value={props.strategy.platform_body_strength_min} onChange={(value) => update('platform_body_strength_min', value)} description="红柱实体 / 上下影线总和；越高说明突破越干净。" />
              <SelectField label="MACD 位置" value={props.strategy.macd_position} onChange={(value) => update('macd_position', value)} options={[['dif_above_zero', 'DIF 在 0 轴上方'], ['dif_dea_above_zero', 'DIF 与 DEA 均在 0 轴上方']]} description="用于判断 MACD 条件是否满足。" />
            </>
          )}

          {props.strategy.signal_mode === 'platform_setup' && (
            <>
              <div className="form-section wide">
                <span>平台临界观察</span>
              </div>
              <NumberField label="平台观察天数" value={props.strategy.platform_setup_lookback_days} onChange={(value) => update('platform_setup_lookback_days', value)} />
              <NumberField label="平台最大振幅" value={props.strategy.platform_setup_max_range} onChange={(value) => update('platform_setup_max_range', value)} />
              <NumberField label="接近上沿距离" value={props.strategy.platform_setup_max_distance_to_high} onChange={(value) => update('platform_setup_max_distance_to_high', value)} />
              <NumberField label="近5日涨幅上限" value={props.strategy.platform_setup_max_recent_gain_5d} onChange={(value) => update('platform_setup_max_recent_gain_5d', value)} />
              <NumberField label="缩量整理上限" value={props.strategy.platform_setup_volume_contraction_max} onChange={(value) => update('platform_setup_volume_contraction_max', value)} />
              <NumberField label="阳线均量优势" value={props.strategy.platform_setup_bull_volume_advantage} onChange={(value) => update('platform_setup_bull_volume_advantage', value)} />
              <NumberField label="均线粘合上限" value={props.strategy.platform_setup_ma_convergence_max} onChange={(value) => update('platform_setup_ma_convergence_max', value)} />
              <SelectField label="MACD 状态" value={props.strategy.platform_setup_macd_mode} onChange={(value) => update('platform_setup_macd_mode', value)} options={[['none', '不启用'], ['dif_above_dea', 'DIF 强于 DEA'], ['dif_above_zero', 'DIF 在 0 轴上方']]} />
              <label className="toggle">
                <input type="checkbox" checked={props.strategy.platform_setup_require_ma_turning} onChange={(event) => update('platform_setup_require_ma_turning', event.target.checked)} />
                <span>要求 MA5 拐头</span>
              </label>
            </>
          )}

          <div className="form-section wide">
            <span>强弱与趋势</span>
          </div>
          <NumberField label="MA 短期" value={props.strategy.ma_short_window} onChange={(value) => update('ma_short_window', value)} />
          <NumberField label="MA 长期" value={props.strategy.ma_long_window} onChange={(value) => update('ma_long_window', value)} />
          <SelectField label="RPS 周期" value={String(props.strategy.rps_window)} onChange={(value) => update('rps_window', Number(value))} options={[['20', 'RPS20'], ['60', 'RPS60'], ['120', 'RPS120']]} />
          <NumberField label="RPS20 下限" value={props.strategy.min_rps20} onChange={(value) => update('min_rps20', value)} allowBlank />
          <NumberField label="RPS60 下限" value={props.strategy.min_rps60} onChange={(value) => update('min_rps60', value)} allowBlank />
          <NumberField label="RPS120 下限" value={props.strategy.min_rps120} onChange={(value) => update('min_rps120', value)} allowBlank />

          <div className="form-section wide">
            <span>量价触发</span>
          </div>
          <NumberField label="振幅上限" value={props.strategy.max_amplitude} onChange={(value) => update('max_amplitude', value)} />
          <NumberField label="最小换手率" value={props.strategy.min_turnover} onChange={(value) => update('min_turnover', value)} allowBlank />
          <NumberField label="最大换手率" value={props.strategy.max_turnover} onChange={(value) => update('max_turnover', value)} allowBlank />
          <NumberField label="最小涨跌幅" value={props.strategy.min_pct_chg} onChange={(value) => update('min_pct_chg', value)} allowBlank />
          <NumberField label="最大涨跌幅" value={props.strategy.max_pct_chg} onChange={(value) => update('max_pct_chg', value)} allowBlank />
          {props.strategy.signal_mode !== 'platform_setup' && (
            <NumberField label="成交量放大" value={props.strategy.volume_ratio_min} onChange={(value) => update('volume_ratio_min', value)} allowBlank />
          )}
          <NumberField label="最大均线偏离" value={props.strategy.max_ma_distance} onChange={(value) => update('max_ma_distance', value)} allowBlank />
          <NumberField label="候选上限" value={props.strategy.candidate_limit} onChange={(value) => update('candidate_limit', value)} />
          <SelectField label="排序" value={props.strategy.sort_by} onChange={(value) => update('sort_by', value)} options={[['signal_score', '信号分数'], ['rps20', 'RPS20'], ['amount', '成交额'], ['pct_chg', '涨跌幅']]} />

          <div className="form-section wide">
            <span>缺失数据处理</span>
          </div>
          <SelectField label="换手率缺失" value={props.strategy.missing_turnover_policy} onChange={(value) => update('missing_turnover_policy', value)} options={[['allow', '保留缺失股票'], ['skip', '跳过缺失股票']]} />
          <SelectField label="流通市值缺失" value={props.strategy.missing_float_market_value_policy} onChange={(value) => update('missing_float_market_value_policy', value)} options={[['allow', '保留缺失股票'], ['skip', '跳过缺失股票']]} />
          <div className="field-note wide">
            空值表示不启用该过滤。保留缺失股票表示字段缺失时不因这一项淘汰；跳过缺失股票表示字段缺失时直接排除该股票。
          </div>
        </div>
      </section>
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
      {candidates.length === 0 && <EmptyState text={zeroReason || '暂无候选。'} />}
      {candidates.length > 0 && (
        <div className="table-wrap">
          <table>
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
                <th>分数</th>
                <th>看图</th>
                {onAddRows && <th>入池</th>}
              </tr>
            </thead>
            <tbody>
              {candidates.map((row) => (
                <tr key={`${row.rank}-${row.code}`}>
                  <td>{row.rank}</td>
                  <td className="mono">{row.code}</td>
                  <td>
                    <div className="name-cell">
                      <strong>{row.name}</strong>
                      <span>{row.reasons?.slice(0, 2).join(' / ')}</span>
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
                  <td><strong>{formatPrice(row.signal_score)}</strong></td>
                  <td><a href={row.chart_url} target="_blank" rel="noreferrer">打开</a></td>
                  {onAddRows && (
                    <td>
                      <button className="table-action" onClick={() => void onAddRows([row])} title="加入观察池">
                        <Plus size={14} />
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
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
    positive_count: 0,
    hit_5pct_count: 0,
    hit_8pct_count: 0,
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

  return (
    <div className="page-stack watchlist-page">
      <section className="metric-grid">
        <MetricCard label="批次" value={formatInt(summary.batch_count)} sub={`${formatInt(summary.item_count)} 只观察`} icon={<Star size={18} />} />
        <MetricCard label="平均累计" value={formatPercentRatio(summary.avg_return_latest)} sub={`${formatInt(summary.positive_count)} 只为正`} icon={<LineChart size={18} />} />
        <MetricCard label="+5% 触达" value={formatInt(summary.hit_5pct_count)} sub={`+8% ${formatInt(summary.hit_8pct_count)} 只`} icon={<Gauge size={18} />} />
        <MetricCard label="最新收盘" value={latestWatchlistDate(result.batches)} sub="来自本地历史 K 线" icon={<Database size={18} />} />
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
              </div>
              <div className="batch-kpis">
                <span>为正 <strong>{formatInt(batch.positive_count)}</strong></span>
                <span>+5% <strong>{formatInt(batch.hit_5pct_count)}</strong></span>
                <span>+8% <strong>{formatInt(batch.hit_8pct_count)}</strong></span>
                <button className="ghost danger-action" disabled={busyKey === batch.id} onClick={() => void removeBatch(batch)}>
                  <Trash2 size={15} />
                  删除批次
                </button>
              </div>
            </div>
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
                    <th>看盘</th>
                    <th>删除</th>
                  </tr>
                </thead>
                <tbody>
                  {batch.items.map((item) => (
                    <tr key={`${batch.id}-${item.code}`}>
                      <td className="mono">{item.code}</td>
                      <td>
                        <div className="name-cell">
                          <strong>{item.name}</strong>
                          <span>{item.signal_type || batch.source_label} · {item.reasons?.slice(0, 2).join(' / ') || '观察记录'}</span>
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
                      <td><a href={item.chart_url} target="_blank" rel="noreferrer">打开</a></td>
                      <td>
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
  const selectedPreset = presets.find((preset) => preset.id === selectedBacktestStrategyId);
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
              {presets.map((preset) => (
                <option key={preset.id} value={preset.id}>{preset.name}</option>
              ))}
            </select>
            <small className="field-hint">{runStrategyName} · 启动时保存策略快照</small>
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
  startSample,
  saveConfig,
  addToWatchlist,
}: {
  result: IntradayRadarResult;
  task: TaskRun | null;
  startSample: () => Promise<void>;
  saveConfig: (config: IntradayRadarConfig) => Promise<void>;
  addToWatchlist?: (payload: Record<string, unknown>) => Promise<void>;
}) {
  const [config, setConfig] = useState<IntradayRadarConfig>(result.config);
  const [radarMode, setRadarMode] = useState<'strict' | 'score'>('strict');
  const running = isTaskActive(task);
  const strictRows = result.strict_rows || result.rows || [];
  const scoreRows = result.score_rows || [];
  const activeRows = radarMode === 'score' ? scoreRows : strictRows;
  const candidateCount = activeRows.length;

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
        <div className="intraday-clockline">
          {['09:35', '10:00', '10:30', '11:00', '11:25', '13:00', '13:30', '14:00', '14:30', '14:55'].map((item) => (
            <span key={item}>{item}</span>
          ))}
        </div>
        <TaskStrip task={task} fallback="盘中采样尚未启动" />
      </section>

      <section className="metric-grid">
        <MetricCard label="最近采样" value={formatChinaLocalDateTime(result.sample_at)} sub="盘中快照时间" icon={<Activity size={18} />} />
        <MetricCard label="样本股票" value={formatInt(result.sample_count)} sub="本次快照覆盖" icon={<Database size={18} />} />
        <MetricCard label="观察" value={formatInt(candidateCount)} sub={radarMode === 'score' ? '综合打分' : '严格筛选'} icon={<Gauge size={18} />} />
        <MetricCard label="状态" value={task?.status === 'queued' ? '排队中' : task?.status === 'running' ? '运行中' : '待命'} sub={task?.stage || '等待采样'} icon={<ShieldAlert size={18} />} />
      </section>

      <section className="panel radar-config-panel">
        <PanelTitle icon={<Settings2 size={18} />} title="雷达设置" />
        <div className="form-grid radar-form">
          <NumberField label="平台观察天数" value={config.platform_lookback_days} onChange={(value) => update('platform_lookback_days', value || 20)} description="从最近历史 K 线向前取样，不包含盘中快照。" />
          <NumberField label="平台最大振幅" value={config.platform_max_range} onChange={(value) => update('platform_max_range', value || 0)} description={`平台高低区间不超过 ${formatPercentRatio(config.platform_max_range)}。`} />
          <NumberField label="接近上沿距离" value={config.near_upper_distance} onChange={(value) => update('near_upper_distance', value || 0)} description={`未突破时，距离上沿小于 ${formatPercentRatio(config.near_upper_distance)} 会进入观察。`} />
          <NumberField label="突破上沿下限" value={config.breakout_min_clearance} onChange={(value) => update('breakout_min_clearance', value || 0)} description="0 表示刚越过平台上沿即可触发。" />
          <NumberField label="突破上沿上限" value={config.breakout_max_clearance} onChange={(value) => update('breakout_max_clearance', value || 0)} description={`超过 ${formatPercentRatio(config.breakout_max_clearance)} 视为买点偏后。`} />
          <NumberField label="最大当日涨幅" value={config.max_pct_chg} onChange={(value) => update('max_pct_chg', value || 0)} description={`快照涨幅高于 ${formatPercent(config.max_pct_chg)} 会跳过。`} />
          <MoneyField label="最小成交额" value={config.min_amount} onChange={(value) => update('min_amount', value || 0)} />
          <NumberField label="时段量能强度" value={config.min_intraday_amount_ratio} onChange={(value) => update('min_intraday_amount_ratio', value || 0)} description={`1.0 表示符合当前时间点正常成交进度，当前阈值 ${formatRatioX(config.min_intraday_amount_ratio)}。`} />
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
            source_ref: result.sample_at || '',
            batch_date: formatDate(result.sample_at || new Date().toISOString()),
            items: rows.map(intradayWatchlistPayload),
          })
          : undefined}
      />
    </div>
  );
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
                <th>看盘</th>
                {onAddRows && <th>入池</th>}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={`${row.sample_at}-${row.radar_mode}-${row.code}`}>
                  <td>{row.rank}</td>
                  <td className="mono">{row.code}</td>
                  <td>
                    <div className="name-cell">
                      <strong>{row.name}</strong>
                      <span>{row.reasons?.slice(0, 2).join(' / ')}</span>
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
                  <td><a href={row.chart_url} target="_blank" rel="noreferrer">打开</a></td>
                  {onAddRows && (
                    <td>
                      <button className="table-action" onClick={() => void onAddRows([row])} title="加入观察池">
                        <Plus size={14} />
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function DataMap({ capabilities, afterProbe }: { capabilities: Capability[]; afterProbe: () => Promise<void> }) {
  const [probing, setProbing] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  async function probe() {
    try {
      setProbing(true);
      const result = (await api.probeSources()) as { rows: Array<{ status: string }> };
      const available = result.rows.filter((row) => row.status === 'available').length;
      setMessage(`${available} 个数据源能力可用`);
      await afterProbe();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : '探测失败');
    } finally {
      setProbing(false);
    }
  }
  return (
    <div className="page-stack">
      <section className="panel map-toolbar">
        <PanelTitle icon={<Layers3 size={18} />} title="能力视图" />
        <div className="quick-actions">
          {message && <span className="muted-text">{message}</span>}
          <button className="ghost" disabled={probing} onClick={probe}>
            <RefreshCw size={16} />
            刷新探测
          </button>
        </div>
      </section>
      <section className="cap-grid">
        {capabilities.map((capability) => (
          <article key={capability.capability} className="cap-card">
            <div className="cap-head">
              <h3>{capability.capability}</h3>
              <span className={capability.participates_in_analysis ? 'pill good' : 'pill muted'}>
                {capability.participates_in_analysis ? '参与分析' : '观察项'}
              </span>
            </div>
            <div className="cap-number">
              <strong>{formatInt(capability.coverage_count)}</strong>
              <span>缺失 {formatInt(capability.missing_count)}</span>
            </div>
            <Progress value={coveragePercent(capability)} />
            <dl>
              <dt>实际来源</dt>
              <dd>{sourceList(capability.actual_sources)}</dd>
              <dt>备用来源</dt>
              <dd>{sourceList(capability.fallback_sources)}</dd>
              <dt>最近更新</dt>
              <dd>{capability.latest_update || '暂无'}</dd>
              <dt>最近失败</dt>
              <dd>{capability.last_failure_reason || '无'}</dd>
            </dl>
          </article>
        ))}
      </section>
    </div>
  );
}

function StatusBoard({
  update,
  analyze,
  backtest,
  intraday,
  latestAnalysis,
}: {
  update: TaskRun | null;
  analyze: TaskRun | null;
  backtest: TaskRun | null;
  intraday: TaskRun | null;
  latestAnalysis: unknown;
}) {
  return (
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
      <section className="panel wide-panel">
        <PanelTitle icon={<BarChart3 size={18} />} title="最近分析" />
        <pre className="json-readout">{JSON.stringify(latestAnalysis || {}, null, 2)}</pre>
      </section>
    </div>
  );
}

function TaskDetail({ task }: { task: TaskRun | null }) {
  if (!task) return <EmptyState text="暂无记录。" />;
  const visual = taskProgressVisual(task);
  const queued = task.status === 'queued';
  const analyzeRunning = task.kind === 'analyze' && task.status === 'running';
  return (
    <div className="task-detail">
      <div className="status-line">
        <span className={`status-badge ${task.status}`}>{statusLabel(task.status)}</span>
        <strong>{task.stage || '等待'}</strong>
      </div>
      <Progress value={visual.value} indeterminate={visual.indeterminate} />
      <div className="task-stats">
        <span>来源 <b>{task.source || '本地缓存'}</b></span>
        {queued ? (
          <>
            <span>当前 <b>等待前序任务</b></span>
            <span>进度 <b>排队中</b></span>
            <span>成功 <b>{formatInt(task.success)}</b></span>
            <span>失败 <b>{formatInt(task.failed)}</b></span>
            <span>跳过 <b>{formatInt(task.skipped)}</b></span>
          </>
        ) : analyzeRunning ? (
          <>
            <span>当前阶段 <b>{task.stage || '准备分析'}</b></span>
            <span>方式 <b>批量计算</b></span>
            <span>进度 <b>自动刷新</b></span>
            <span>结果 <b>完成后写入报告</b></span>
            <span>状态 <b>运行中</b></span>
          </>
        ) : (
          <>
            <span>当前 <b>{task.current_stock || '-'}</b></span>
            <span>进度 <b>{formatInt(task.processed)} / {formatInt(task.total)}</b></span>
            <span>成功 <b>{formatInt(task.success)}</b></span>
            <span>失败 <b>{formatInt(task.failed)}</b></span>
            <span>跳过 <b>{formatInt(task.skipped)}</b></span>
          </>
        )}
      </div>
      {task.warning && <InlineError text={task.warning} />}
      {task.error_message && <InlineError text={task.error_message} />}
    </div>
  );
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
  const groupOrder = ['股票池', '趋势强弱', '平台形态', '突破确认', '输出'];
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
  return (
    <div className="task-strip">
      <div>
        <span className={`status-badge ${task.status}`}>{statusLabel(task.status)}</span>
        <strong>{task.stage}</strong>
        <small>{task.status === 'queued' ? '等待前序任务' : task.kind === 'analyze' && task.status === 'running' ? '阶段推进中' : task.current_stock || task.source || '本地缓存'}</small>
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
  const mode = signalModes.find((item) => item.id === strategy.signal_mode)?.label || '自定义';
  if (strategy.signal_mode === 'platform_setup') {
    return `${mode} · ${strategy.platform_setup_lookback_days}日 · 距上沿≤${formatPercentRatio(strategy.platform_setup_max_distance_to_high)} · 近5日≤${formatPercentRatio(strategy.platform_setup_max_recent_gain_5d)}`;
  }
  if (strategy.signal_mode === 'platform_breakout') {
    const clearance = strategy.platform_breakout_clearance_mode !== 'off'
      ? ` · 上沿≥${formatPercentRatio(strategy.platform_breakout_clearance)}`
      : '';
    const maxClearance = strategy.platform_breakout_max_clearance_mode !== 'off'
      ? ` · 上沿≤${formatPercentRatio(strategy.platform_breakout_max_clearance)}`
      : '';
    const firstBreak = strategy.platform_breakout_first_mode === 'must' ? ' · 首次' : '';
    return `${mode} · ${strategy.platform_lookback_days}日 · 区间≤${formatPercentRatio(strategy.platform_max_range)}${clearance}${maxClearance}${firstBreak} · 量比≥${formatPrice(strategy.platform_breakout_volume_ratio)}x · 涨幅≥${formatPercent(strategy.platform_breakout_pct_chg_min)}`;
  }
  const rpsKey = `RPS${strategy.rps_window}`;
  const amount = formatMoneyCompact(strategy.min_amount || 0);
  return `${mode} · 成交额≥${amount} · ${rpsKey} · MA${strategy.ma_short_window}/${strategy.ma_long_window}`;
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

function coveragePercent(capability: Capability) {
  const total = capability.coverage_count + capability.missing_count;
  if (!total) return 0;
  return Math.round((capability.coverage_count / total) * 100);
}

function sourceList(sources: string[]) {
  return sources.length ? sources.join(' / ') : '暂无';
}

createRoot(document.getElementById('root')!).render(<App />);
