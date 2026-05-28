import { useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Activity, Play } from 'lucide-react';
import { getSignalEvaluation, runSignalEvaluation } from '../../api/backtest';
import { Button } from '../../design/Button';
import { Badge } from '../../design/Badge';
import { useBootstrap } from '../../hooks/useBootstrap';
import { useStrategyDraft } from '../../hooks/useStrategyDraft';
import { composeStrategyConfig, strategySummary } from '../../utils/strategy';
import { formatRatio } from '../../utils/format';
import { todayISO } from '../../utils/date';

export function SignalEvaluation() {
  const bootstrap = useBootstrap();
  const draft = useStrategyDraft();
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState(todayISO());
  const [step, setStep] = useState('5');
  const [candidateLimit, setCandidateLimit] = useState('');
  const baseConfig = draft.config || bootstrap.data?.default_strategy || null;
  const config = useMemo(() => (baseConfig ? composeStrategyConfig(baseConfig, draft.rules, draft.resonances) : null), [baseConfig, draft.rules, draft.resonances]);
  const mutation = useMutation({
    mutationFn: () =>
      runSignalEvaluation({
        config,
        start_date: startDate || undefined,
        end_date: endDate || undefined,
        step: Number(step) || 5,
        candidate_limit: Number(candidateLimit) || config?.candidate_limit || 80,
      }),
  });
  const result = useQuery({
    queryKey: ['signal-evaluation', mutation.data?.run_id],
    queryFn: () => getSignalEvaluation(mutation.data?.run_id || ''),
    enabled: Boolean(mutation.data?.run_id),
    refetchInterval: (query) => {
      const status = query.state.data?.run?.status;
      return status === 'queued' || status === 'running' ? 2600 : false;
    },
  });
  const summary = (result.data?.run?.summary || {}) as Record<string, unknown>;
  const queued = mutation.data && !result.data?.run?.summary;
  return (
    <section className="surface pad">
      <div className="section-heading">
        <div>
          <h2>信号评估</h2>
          <p>{strategySummary(config)}</p>
        </div>
        <Button disabled={mutation.isPending || !config} icon={<Play size={16} />} onClick={() => mutation.mutate()} variant="primary">
          运行评估
        </Button>
      </div>
      <div className="backtest-form">
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
          <span>候选上限</span>
          <input inputMode="numeric" placeholder={String(config?.candidate_limit || 80)} value={candidateLimit} onChange={(event) => setCandidateLimit(event.target.value)} />
        </label>
      </div>
      {mutation.data ? (
        <div className="backtest-runline">
          <strong>{queued ? '已进入任务队列' : result.data?.run?.status || mutation.data.status}</strong>
          <small>{mutation.data.task_id} · {mutation.data.run_id}</small>
        </div>
      ) : null}
      <div className="metric-row">
        <Metric label="Rank IC" value={formatRatio(summary.rank_ic)} />
        <Metric label="IC" value={formatRatio(summary.ic)} />
        <Metric label="Top N 收益" value={formatRatio(summary.top_n_avg_return_10d)} />
        <Metric label="共振命中" value={formatRatio(summary.resonance_hit_count)} />
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
