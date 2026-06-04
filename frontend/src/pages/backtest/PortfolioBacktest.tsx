import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Play } from 'lucide-react';
import { getPortfolioBacktest, runPortfolioBacktest } from '../../api/backtest';
import { queryKeys } from '../../api/queryKeys';
import type { StrategyConfig } from '../../types';
import { Button } from '../../design/Button';
import { Badge } from '../../design/Badge';
import { useToast } from '../../design/Toast';
import { useHeavyTaskLock } from '../../hooks/useHeavyTaskLock';
import { useTaskResultQuery } from '../../hooks/useTaskResultQuery';
import { strategySummary } from '../../utils/strategy';
import { formatMoney, formatRatio, formatRatioPercent, toNumber } from '../../utils/format';
import { todayISO } from '../../utils/date';

export function PortfolioBacktest({
  config,
  selectedRunId,
  strategyName,
  onRunStarted,
}: {
  config: StrategyConfig | null;
  selectedRunId: string;
  strategyName: string;
  onRunStarted: (runId: string) => void;
}) {
  const { showToast } = useToast();
  const taskLock = useHeavyTaskLock();
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState(todayISO());
  const [initialEquity, setInitialEquity] = useState('1000000');
  const [maxPositions, setMaxPositions] = useState('8');
  const [holdDays, setHoldDays] = useState('5');
  const [rebalanceStep, setRebalanceStep] = useState('5');
  const [candidateLimit, setCandidateLimit] = useState('');
  const [feeBps, setFeeBps] = useState('8');
  const [slippageBps, setSlippageBps] = useState('5');
  const mutation = useMutation({
    mutationFn: () =>
      runPortfolioBacktest({
        config,
        strategy_name: strategyName,
        initial_equity: Number(initialEquity) || 1_000_000,
        start_date: startDate || undefined,
        end_date: endDate || undefined,
        candidate_limit: Number(candidateLimit) || config?.candidate_limit || 80,
        max_positions: Number(maxPositions) || 8,
        hold_days: Number(holdDays) || 5,
        step: Number(rebalanceStep) || 5,
        transaction_cost_bps: Number(feeBps) || 8,
        slippage_bps: Number(slippageBps) || 5,
      }),
    onSuccess: (job) => {
      if (job.runId) onRunStarted(job.runId);
      window.location.hash = '#status';
      showToast('回测任务已开始，可在任务状态查看进度', 'success');
    },
    onError: (error) => showToast(error instanceof Error ? error.message : '回测任务启动失败', 'danger'),
  });
  const result = useTaskResultQuery<Record<string, unknown>>({
    queryKey: queryKeys.backtest.portfolio(selectedRunId),
    queryFn: () => getPortfolioBacktest(selectedRunId),
    enabled: Boolean(selectedRunId),
    initialStatus: mutation.data?.status,
    getResultStatus: (data) => String(((data?.run as Record<string, unknown> | undefined)?.status as string | undefined) || ''),
  });
  const run = (result.data?.run || {}) as Record<string, unknown>;
  const summary = (run.summary || {}) as Record<string, unknown>;
  return (
    <section className="surface pad backtest-panel">
      <div className="section-heading">
        <div>
          <h2>简化组合模拟</h2>
          <p>{strategyName} · {strategySummary(config)}</p>
        </div>
        <Button disabled={taskLock.locked || mutation.isPending || !config} icon={<Play size={16} />} onClick={() => mutation.mutate()} variant="primary">
          运行组合回测
        </Button>
      </div>
      <div className="notice-card" style={{ marginBottom: 14 }}>
        当前为简化组合模拟，适合快速比较策略，不等同真实交易账户回测。
      </div>
      <div className="backtest-form-grid">
        <label>
          <span>初始模拟权益</span>
          <input inputMode="numeric" value={initialEquity} onChange={(event) => setInitialEquity(event.target.value)} />
        </label>
        <label>
          <span>开始日期</span>
          <input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} />
        </label>
        <label>
          <span>结束日期</span>
          <input type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} />
        </label>
        <label>
          <span>候选数量</span>
          <input inputMode="numeric" placeholder={String(config?.candidate_limit || 80)} value={candidateLimit} onChange={(event) => setCandidateLimit(event.target.value)} />
        </label>
        <label>
          <span>持仓数量</span>
          <input inputMode="numeric" value={maxPositions} onChange={(event) => setMaxPositions(event.target.value)} />
        </label>
        <label>
          <span>持有天数</span>
          <input inputMode="numeric" value={holdDays} onChange={(event) => setHoldDays(event.target.value)} />
        </label>
        <label>
          <span>调仓频率</span>
          <input inputMode="numeric" value={rebalanceStep} onChange={(event) => setRebalanceStep(event.target.value)} />
        </label>
        <label>
          <span>交易成本</span>
          <input inputMode="numeric" value={feeBps} onChange={(event) => setFeeBps(event.target.value)} />
        </label>
        <label>
          <span>滑点</span>
          <input inputMode="numeric" value={slippageBps} onChange={(event) => setSlippageBps(event.target.value)} />
        </label>
      </div>
      {selectedRunId ? (
        <div className="backtest-runline">
          <strong>{statusLabel(String(run.status || mutation.data?.status || ''))}</strong>
          <Button onClick={() => (window.location.hash = '#status')} variant="ghost">
            查看任务状态
          </Button>
        </div>
      ) : null}
      <div className="backtest-results-grid metric-row">
        <Metric label="初始权益" value={formatMoneyStatus(summary.initial_equity)} />
        <Metric label="最终权益" value={formatMoneyStatus(summary.ending_equity)} />
        <Metric label="总收益" value={formatPercentStatus(summary.total_return)} />
        <Metric label="最大回撤" value={formatPercentStatus(summary.max_drawdown)} />
        <Metric label="胜率" value={formatPercentStatus(summary.win_rate)} />
        <Metric label="平均单笔" value={formatPercentStatus(summary.avg_trade_return)} />
        <Metric label="交易次数" value={formatRatioStatus(summary.trade_count)} />
        <Metric label="调仓期换手" value={formatRatioStatus(summary.turnover_rate)} />
      </div>
      <div className="rule-chip-grid" style={{ marginTop: 14 }}>
        <Badge tone="info">涨停买不进</Badge>
        <Badge tone="info">跌停延后卖出</Badge>
        <Badge>次日开盘</Badge>
        <Badge>持有 N 日</Badge>
        <Badge>等权持仓</Badge>
        <Badge>任务队列跟踪</Badge>
      </div>
      <div className="backtest-placeholder-grid" style={{ marginTop: 14 }}>
        <Placeholder title="资金曲线" />
        <Placeholder title="回撤曲线" />
        <Placeholder title="月度收益表" />
        <Placeholder title="交易明细" />
        <Placeholder title="当前持仓模拟" />
      </div>
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric-pill">
      <span className="metric-label">{label}</span>
      <div className="metric-value">{value}</div>
    </div>
  );
}

function formatMoneyStatus(value: unknown) {
  return toNumber(value) === null ? '待回测' : formatMoney(value);
}

function formatPercentStatus(value: unknown) {
  return toNumber(value) === null ? '待回测' : formatRatioPercent(value);
}

function formatRatioStatus(value: unknown) {
  return toNumber(value) === null ? '待回测' : formatRatio(value);
}

function Placeholder({ title }: { title: string }) {
  return (
    <article className="surface-subtle">
      <h3>{title}</h3>
      <p className="card-copy">回测完成后展示。</p>
    </article>
  );
}

function statusLabel(status: string) {
  if (status === 'queued') return '已排队';
  if (status === 'running') return '运行中';
  if (status === 'completed_full' || status === 'completed') return '完成';
  if (status === 'failed') return '失败';
  return status || '已提交';
}
