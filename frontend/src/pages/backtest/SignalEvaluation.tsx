import { useMutation } from '@tanstack/react-query';
import { Activity, Play } from 'lucide-react';
import { runSignalEvaluation } from '../../api/backtest';
import { Button } from '../../design/Button';
import { Badge } from '../../design/Badge';
import { formatRatio } from '../../utils/format';
import { todayISO } from '../../utils/date';

export function SignalEvaluation() {
  const mutation = useMutation({
    mutationFn: () =>
      runSignalEvaluation({
        start_date: '2024-01-01',
        end_date: todayISO(),
        sample_frequency: 'daily',
        candidate_limit: 80,
      }),
  });
  const summary = (mutation.data?.summary || {}) as Record<string, unknown>;
  return (
    <section className="surface pad">
      <div className="section-heading">
        <div>
          <h2>信号评估</h2>
          <p>评估信号数量、收益、IC / Rank IC、Top N、分桶单调性和共振命中。</p>
        </div>
        <Button disabled={mutation.isPending} icon={<Play size={16} />} onClick={() => mutation.mutate()} variant="primary">
          运行评估
        </Button>
      </div>
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
