import { useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { createRoot } from 'react-dom/client';
import {
  Activity,
  BarChart3,
  CandlestickChart,
  Database,
  Gauge,
  Layers3,
  LineChart,
  Play,
  RefreshCw,
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
  Candidate,
  Capability,
  FunnelStep,
  StrategyConfig,
  StrategyPreset,
  TaskRun,
} from './types';
import './styles.css';

type Tab = 'overview' | 'warehouse' | 'strategy' | 'results' | 'map' | 'status';

const navItems: Array<{ id: Tab; label: string; icon: ReactNode }> = [
  { id: 'overview', label: '总览', icon: <Gauge size={17} /> },
  { id: 'warehouse', label: '数据仓库', icon: <Database size={17} /> },
  { id: 'strategy', label: '策略', icon: <SlidersHorizontal size={17} /> },
  { id: 'results', label: '分析结果', icon: <BarChart3 size={17} /> },
  { id: 'map', label: '数据地图', icon: <Layers3 size={17} /> },
  { id: 'status', label: '运行状态', icon: <Workflow size={17} /> },
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
  const [updateLimit, setUpdateLimit] = useState(0);

  async function load(silent = false) {
    try {
      if (!silent) setLoading(true);
      const next = await api.bootstrap();
      setBootstrap(next);
      if (!strategy) {
        setStrategy(next.default_strategy);
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

  const updateRunning = bootstrap?.update_status?.status === 'running';
  const analyzeRunning = bootstrap?.analyze_status?.status === 'running';

  useEffect(() => {
    if (!updateRunning && !analyzeRunning) return;
    const timer = window.setInterval(() => void load(true), 2200);
    return () => window.clearInterval(timer);
  }, [updateRunning, analyzeRunning]);

  async function startUpdate(force = false) {
    try {
      await api.startUpdate({ force, limit: updateLimit || undefined });
      setNotice('数据更新已开始');
      await load(true);
      setTab('status');
    } catch (err) {
      setError(err instanceof Error ? err.message : '无法启动更新');
    }
  }

  async function startAnalyze(current = strategy) {
    if (!current) return;
    try {
      await api.startAnalyze(current);
      setNotice('分析已开始');
      await load(true);
      setTab('status');
    } catch (err) {
      setError(err instanceof Error ? err.message : '无法启动分析');
    }
  }

  async function saveStrategy(setDefault = false) {
    if (!strategy) return;
    try {
      const payload = {
        id: selectedPresetId?.startsWith('custom-') ? selectedPresetId : undefined,
        name: strategyName,
        config: strategy,
        set_default: setDefault,
      };
      await api.saveStrategy(payload);
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
          updateLimit={updateLimit}
          setUpdateLimit={setUpdateLimit}
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
            setSelectedPresetId(preset.id);
            setStrategyName(preset.name);
            setStrategy(preset.config);
          }}
          saveStrategy={saveStrategy}
          saveAndRun={saveAndRun}
          duplicate={async () => {
            if (!selectedPresetId) return;
            await api.duplicateStrategy(selectedPresetId);
            setNotice('策略已复制');
            await load(true);
          }}
          remove={async () => {
            if (!selectedPresetId) return;
            await api.deleteStrategy(selectedPresetId);
            setNotice('策略已删除');
            setSelectedPresetId(null);
            await load(true);
          }}
          setDefault={async () => {
            if (!selectedPresetId) return;
            await api.setDefaultStrategy(selectedPresetId);
            setNotice('默认策略已更新');
            await load(true);
          }}
          reset={async () => {
            await api.resetSystemStrategies();
            setNotice('系统预设已恢复');
            await load(true);
          }}
        />
      );
    }
    if (tab === 'results') return <Results candidates={bootstrap.candidates.rows} funnel={bootstrap.candidates.funnel} zeroReason={bootstrap.candidates.zero_reason} />;
    if (tab === 'map') {
      return <DataMap capabilities={bootstrap.capabilities} afterProbe={() => load(true)} />;
    }
    return <StatusBoard update={bootstrap.update_status} analyze={bootstrap.analyze_status} latestAnalysis={bootstrap.latest_analysis} />;
  }, [bootstrap, tab, strategy, strategyName, selectedPresetId, updateLimit]);

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
            <button className="primary" disabled={updateRunning} onClick={() => startUpdate(false)}>
              <RefreshCw size={16} />
              更新数据
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

function Overview({
  bootstrap,
  updateLimit,
  setUpdateLimit,
  startUpdate,
  startAnalyze,
}: {
  bootstrap: Bootstrap;
  updateLimit: number;
  setUpdateLimit: (value: number) => void;
  startUpdate: (force?: boolean) => void;
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
            <label className="field compact">
              <span>本次上限</span>
              <input value={updateLimit} onChange={(event) => setUpdateLimit(numberFromInput(event.target.value, 0) || 0)} />
            </label>
            <button onClick={() => startUpdate(false)} className="primary">
              <RefreshCw size={16} />
              更新
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
  remove: () => Promise<void>;
  setDefault: () => Promise<void>;
  reset: () => Promise<void>;
}) {
  const selected = props.presets.find((preset) => preset.id === props.selectedPresetId);
  const update = (key: keyof StrategyConfig, value: unknown) => {
    props.setStrategy({ ...props.strategy, [key]: value });
  };
  return (
    <div className="strategy-layout">
      <section className="panel preset-panel">
        <PanelTitle icon={<Settings2 size={18} />} title="预设" />
        <div className="preset-list">
          {props.presets.map((preset) => (
            <button
              key={preset.id}
              className={preset.id === props.selectedPresetId ? 'preset active' : 'preset'}
              onClick={() => props.selectPreset(preset)}
            >
              <span>{preset.name}</span>
              <small>{preset.is_default ? '默认' : preset.is_system ? '系统' : '自定义'}</small>
            </button>
          ))}
        </div>
        <div className="button-grid">
          <button className="ghost" onClick={props.duplicate}>复制</button>
          <button className="ghost" onClick={props.setDefault}>设默认</button>
          <button className="ghost danger" disabled={Boolean(selected?.is_system)} onClick={props.remove}>
            <Trash2 size={15} />
            删除
          </button>
          <button className="ghost" onClick={props.reset}>恢复</button>
        </div>
      </section>

      <section className="panel editor-panel">
        <div className="table-toolbar">
          <PanelTitle icon={<SlidersHorizontal size={18} />} title="指标配置" />
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

        <div className="form-grid">
          <label className="field wide">
            <span>预设名称</span>
            <input value={props.strategyName} onChange={(event) => props.setStrategyName(event.target.value)} />
          </label>
          <NumberField label="最低股价" value={props.strategy.min_price} onChange={(value) => update('min_price', value)} />
          <NumberField label="成交额门槛" value={props.strategy.min_amount} onChange={(value) => update('min_amount', value)} />
          <NumberField label="最小流通市值" value={props.strategy.min_float_market_value} onChange={(value) => update('min_float_market_value', value)} allowBlank />
          <NumberField label="最大流通市值" value={props.strategy.max_float_market_value} onChange={(value) => update('max_float_market_value', value)} allowBlank />
          <NumberField label="MA 短期" value={props.strategy.ma_short_window} onChange={(value) => update('ma_short_window', value)} />
          <NumberField label="MA 长期" value={props.strategy.ma_long_window} onChange={(value) => update('ma_long_window', value)} />
          <SelectField label="信号模式" value={props.strategy.signal_mode} onChange={(value) => update('signal_mode', value)} options={[['breakout_or_pullback', '突破或回踩'], ['breakout', '右侧突破'], ['pullback', '左侧回踩']]} />
          <NumberField label="振幅上限" value={props.strategy.max_amplitude} onChange={(value) => update('max_amplitude', value)} />
          <SelectField label="RPS 周期" value={String(props.strategy.rps_window)} onChange={(value) => update('rps_window', Number(value))} options={[['20', 'RPS20'], ['60', 'RPS60'], ['120', 'RPS120']]} />
          <NumberField label="RPS20 下限" value={props.strategy.min_rps20} onChange={(value) => update('min_rps20', value)} allowBlank />
          <NumberField label="RPS60 下限" value={props.strategy.min_rps60} onChange={(value) => update('min_rps60', value)} allowBlank />
          <NumberField label="RPS120 下限" value={props.strategy.min_rps120} onChange={(value) => update('min_rps120', value)} allowBlank />
          <NumberField label="最小换手率" value={props.strategy.min_turnover} onChange={(value) => update('min_turnover', value)} allowBlank />
          <NumberField label="最大换手率" value={props.strategy.max_turnover} onChange={(value) => update('max_turnover', value)} allowBlank />
          <NumberField label="最小涨跌幅" value={props.strategy.min_pct_chg} onChange={(value) => update('min_pct_chg', value)} allowBlank />
          <NumberField label="最大涨跌幅" value={props.strategy.max_pct_chg} onChange={(value) => update('max_pct_chg', value)} allowBlank />
          <NumberField label="成交量放大" value={props.strategy.volume_ratio_min} onChange={(value) => update('volume_ratio_min', value)} allowBlank />
          <NumberField label="最大均线偏离" value={props.strategy.max_ma_distance} onChange={(value) => update('max_ma_distance', value)} allowBlank />
          <NumberField label="候选上限" value={props.strategy.candidate_limit} onChange={(value) => update('candidate_limit', value)} />
          <SelectField label="排序" value={props.strategy.sort_by} onChange={(value) => update('sort_by', value)} options={[['signal_score', '信号分数'], ['rps20', 'RPS20'], ['amount', '成交额'], ['pct_chg', '涨跌幅']]} />
          <SelectField label="缺失换手率" value={props.strategy.missing_turnover_policy} onChange={(value) => update('missing_turnover_policy', value)} options={[['allow', '允许降级'], ['skip', '直接跳过']]} />
          <SelectField label="缺失市值" value={props.strategy.missing_float_market_value_policy} onChange={(value) => update('missing_float_market_value_policy', value)} options={[['allow', '允许降级'], ['skip', '直接跳过']]} />
          <label className="toggle">
            <input type="checkbox" checked={props.strategy.include_bj} onChange={(event) => update('include_bj', event.target.checked)} />
            <span>包含北交所</span>
          </label>
          <label className="toggle">
            <input type="checkbox" checked={props.strategy.exclude_star_board} onChange={(event) => update('exclude_star_board', event.target.checked)} />
            <span>排除科创板</span>
          </label>
        </div>
      </section>
    </div>
  );
}

function Results({
  candidates,
  funnel,
  zeroReason,
  compact = false,
}: {
  candidates: Candidate[];
  funnel: FunnelStep[];
  zeroReason: string | null;
  compact?: boolean;
}) {
  return (
    <section className="panel">
      <div className="table-toolbar">
        <PanelTitle icon={<BarChart3 size={18} />} title={compact ? '最新候选' : '候选股票'} />
        <span className="pill">{formatInt(candidates.length)} 只</span>
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
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {!compact && <Funnel funnel={funnel} />}
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
  latestAnalysis,
}: {
  update: TaskRun | null;
  analyze: TaskRun | null;
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
      <section className="panel wide-panel">
        <PanelTitle icon={<BarChart3 size={18} />} title="最近分析" />
        <pre className="json-readout">{JSON.stringify(latestAnalysis || {}, null, 2)}</pre>
      </section>
    </div>
  );
}

function TaskDetail({ task }: { task: TaskRun | null }) {
  if (!task) return <EmptyState text="暂无记录。" />;
  const percent = task.total ? Math.round((task.processed / task.total) * 100) : task.status === 'running' ? 18 : 100;
  return (
    <div className="task-detail">
      <div className="status-line">
        <span className={`status-badge ${task.status}`}>{statusLabel(task.status)}</span>
        <strong>{task.stage || '等待'}</strong>
      </div>
      <Progress value={percent} />
      <div className="task-stats">
        <span>来源 <b>{task.source || '本地缓存'}</b></span>
        <span>当前 <b>{task.current_stock || '-'}</b></span>
        <span>进度 <b>{formatInt(task.processed)} / {formatInt(task.total)}</b></span>
        <span>成功 <b>{formatInt(task.success)}</b></span>
        <span>失败 <b>{formatInt(task.failed)}</b></span>
        <span>跳过 <b>{formatInt(task.skipped)}</b></span>
      </div>
      {task.warning && <InlineError text={task.warning} />}
      {task.error_message && <InlineError text={task.error_message} />}
    </div>
  );
}

function Funnel({ funnel }: { funnel: FunnelStep[] }) {
  if (!funnel.length) return null;
  const max = Math.max(...funnel.map((step) => step.before_count), 1);
  return (
    <div className="funnel">
      {funnel.map((step) => (
        <div key={step.step_name} className="funnel-step">
          <div>
            <strong>{step.step_name}</strong>
            <span>{step.note}</span>
          </div>
          <div className="funnel-bar">
            <i style={{ width: `${Math.max(4, (step.after_count / max) * 100)}%` }} />
          </div>
          <b>{formatInt(step.after_count)}</b>
        </div>
      ))}
    </div>
  );
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
  const percent = task.total ? Math.round((task.processed / task.total) * 100) : task.status === 'running' ? 18 : 100;
  return (
    <div className="task-strip">
      <div>
        <span className={`status-badge ${task.status}`}>{statusLabel(task.status)}</span>
        <strong>{task.stage}</strong>
        <small>{task.current_stock || task.source || '本地缓存'}</small>
      </div>
      <Progress value={percent} />
    </div>
  );
}

function StatusDot({ task, label }: { task?: TaskRun | null; label: string }) {
  return (
    <span className={`dot ${task?.status || 'idle'}`}>
      <i />
      {label}
    </span>
  );
}

function Progress({ value }: { value: number }) {
  return (
    <div className="progress" aria-label={`进度 ${value}%`}>
      <i style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
    </div>
  );
}

function NumberField({
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
  return (
    <label className="field">
      <span>{label}</span>
      <input
        value={value ?? ''}
        onChange={(event) => onChange(numberFromInput(event.target.value, allowBlank ? null : 0))}
      />
    </label>
  );
}

function SelectField({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: Array<[string, string]>;
  onChange: (value: string) => void;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        {options.map(([optionValue, labelText]) => (
          <option key={optionValue} value={optionValue}>{labelText}</option>
        ))}
      </select>
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

function numberFromInput(value: string, fallback: number | null): number | null {
  if (value.trim() === '') return fallback;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function formatInt(value: unknown) {
  const number = Number(value || 0);
  return new Intl.NumberFormat('zh-CN').format(number);
}

function formatPrice(value: unknown) {
  const number = Number(value);
  if (!Number.isFinite(number)) return '-';
  return number.toFixed(2);
}

function formatPercent(value: unknown) {
  const number = Number(value);
  if (!Number.isFinite(number)) return '-';
  return `${number.toFixed(2)}%`;
}

function formatPercentRatio(value: unknown) {
  const number = Number(value);
  if (!Number.isFinite(number)) return '-';
  return `${(number * 100).toFixed(2)}%`;
}

function formatMoney(value: unknown) {
  const number = Number(value);
  if (!Number.isFinite(number)) return '-';
  if (Math.abs(number) >= 100_000_000) return `${(number / 100_000_000).toFixed(2)} 亿`;
  if (Math.abs(number) >= 10_000) return `${(number / 10_000).toFixed(2)} 万`;
  return number.toFixed(0);
}

function toneClass(value: number) {
  if (value > 0) return 'up';
  if (value < 0) return 'down';
  return '';
}

function statusLabel(status: string) {
  const labels: Record<string, string> = {
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
