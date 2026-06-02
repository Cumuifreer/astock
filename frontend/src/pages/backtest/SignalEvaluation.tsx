import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Activity, Play } from 'lucide-react';
import { getSignalEvaluation, runSignalEvaluation } from '../../api/backtest';
import { queryKeys } from '../../api/queryKeys';
import type { StrategyConfig } from '../../types';
import { Button } from '../../design/Button';
import { Badge } from '../../design/Badge';
import { CheckTile } from '../../design/CheckTile';
import { useToast } from '../../design/Toast';
import { useTaskResultQuery } from '../../hooks/useTaskResultQuery';
import { strategySummary } from '../../utils/strategy';
import { formatRatio, formatRatioPercent, toNumber } from '../../utils/format';
import { todayISO } from '../../utils/date';

export function SignalEvaluation({
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
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState(todayISO());
  const [step, setStep] = useState('5');
  const [candidateLimit, setCandidateLimit] = useState('');
  const [marketBuckets, setMarketBuckets] = useState(true);
  const [scoreBuckets, setScoreBuckets] = useState(true);
  const mutation = useMutation({
    mutationFn: () =>
      runSignalEvaluation({
        config,
        strategy_name: strategyName,
        start_date: startDate || undefined,
        end_date: endDate || undefined,
        step: Number(step) || 5,
        candidate_limit: Number(candidateLimit) || config?.candidate_limit || 80,
        market_buckets: marketBuckets,
        score_buckets: scoreBuckets,
      }),
    onSuccess: (job) => {
      if (job.runId) onRunStarted(job.runId);
      window.location.hash = '#status';
      showToast('回测任务已开始，可在任务状态查看进度', 'success');
    },
    onError: (error) => showToast(error instanceof Error ? error.message : '回测任务启动失败', 'danger'),
  });
  const result = useTaskResultQuery({
    queryKey: queryKeys.backtest.signalEvaluation(selectedRunId),
    queryFn: () => getSignalEvaluation(selectedRunId),
    enabled: Boolean(selectedRunId),
    initialStatus: mutation.data?.status,
    getResultStatus: (data) => data?.run?.status,
  });
  const summary = (result.data?.run?.summary || {}) as Record<string, unknown>;
  const queued = Boolean(mutation.data && selectedRunId === mutation.data.runId && !result.data?.run?.summary);
  return (
    <section className="surface pad backtest-panel">
      <div className="section-heading">
        <div>
          <h2>信号评估</h2>
          <p>{strategyName} · {strategySummary(config)}</p>
        </div>
        <Button disabled={mutation.isPending || !config} icon={<Play size={16} />} onClick={() => mutation.mutate()} variant="primary">
          运行评估
        </Button>
      </div>
      <div className="backtest-form-grid">
        <label>
          <span>开始日期</span>
          <input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} />
        </label>
        <label>
          <span>结束日期</span>
          <input type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} />
        </label>
        <label>
          <span>采样间隔</span>
          <input inputMode="numeric" value={step} onChange={(event) => setStep(event.target.value)} />
        </label>
        <label>
          <span>候选数量</span>
          <input inputMode="numeric" placeholder={String(config?.candidate_limit || 80)} value={candidateLimit} onChange={(event) => setCandidateLimit(event.target.value)} />
        </label>
        <CheckTile checked={marketBuckets} label="市场状态分层" onCheckedChange={setMarketBuckets} />
        <CheckTile checked={scoreBuckets} label="分数分桶" onCheckedChange={setScoreBuckets} />
      </div>
      {selectedRunId ? (
        <div className="backtest-runline">
          <strong>{queued ? '已排队' : statusLabel(result.data?.run?.status || mutation.data?.status)}</strong>
          <Button onClick={() => (window.location.hash = '#status')} variant="ghost">
            查看任务状态
          </Button>
        </div>
      ) : null}
      <div className="backtest-results-grid metric-row">
        <Metric label="样本数" value={formatRatioStatus(summary.signal_count)} />
        <Metric label="评估日期" value={formatRatioStatus(summary.evaluated_dates)} />
        <Metric label="平均 T+5 收益" value={formatPercentStatus(summary.avg_return_5d)} />
        <Metric label="平均 T+10 收益" value={formatPercentStatus(summary.top_n_avg_return_10d || summary.avg_return_10d)} />
        <Metric label="平均 T+20 收益" value={formatPercentStatus(summary.avg_return_20d)} />
        <Metric label="10日触及5%" value={formatPercentStatus(summary.hit_5pct_10d_rate)} />
        <Metric label="10日回撤中位" value={formatPercentStatus(summary.median_max_drawdown_10d)} />
        <Metric label="排序 IC" value={formatRatioStatus(summary.rank_ic)} />
      </div>
      <div className="rule-chip-grid" style={{ marginTop: 14 }}>
        <Badge tone="info">
          <Activity size={14} />
          风险分层表现
        </Badge>
        <Badge>按市场状态分组</Badge>
        <Badge>按题材分组</Badge>
        <Badge>规则命中贡献</Badge>
      </div>
      <div className="backtest-placeholder-grid" style={{ marginTop: 14 }}>
        <Placeholder title="分数分桶收益" />
        <Placeholder title="市场状态分层表现" />
        <Placeholder title="历史信号表" />
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

function formatPercentStatus(value: unknown) {
  return toNumber(value) === null ? '待评估' : formatRatioPercent(value);
}

function formatRatioStatus(value: unknown) {
  return toNumber(value) === null ? '待评估' : formatRatio(value);
}

function Placeholder({ title }: { title: string }) {
  return (
    <article className="surface-subtle">
      <h3>{title}</h3>
      <p className="card-copy">评估完成后展示。</p>
    </article>
  );
}

function statusLabel(status?: string | null) {
  if (status === 'queued') return '已排队';
  if (status === 'running') return '运行中';
  if (status === 'completed_full' || status === 'completed') return '完成';
  if (status === 'failed') return '失败';
  return status || '已提交';
}
