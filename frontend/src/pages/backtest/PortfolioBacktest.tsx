import { useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Play } from 'lucide-react';
import { getPortfolioBacktest, runPortfolioBacktest } from '../../api/backtest';
import { Button } from '../../design/Button';
import { Badge } from '../../design/Badge';
import { useBootstrap } from '../../hooks/useBootstrap';
import { useStrategyDraft } from '../../hooks/useStrategyDraft';
import { composeStrategyConfig, strategySummary } from '../../utils/strategy';
import { formatMoney, formatPercent, formatRatio } from '../../utils/format';
import { todayISO } from '../../utils/date';

export function PortfolioBacktest() {
  const bootstrap = useBootstrap();
  const draft = useStrategyDraft();
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState(todayISO());
  const [maxPositions, setMaxPositions] = useState('8');
  const [holdDays, setHoldDays] = useState('5');
  const [candidateLimit, setCandidateLimit] = useState('');
  const baseConfig = draft.config || bootstrap.data?.default_strategy || null;
  const config = useMemo(() => (baseConfig ? composeStrategyConfig(baseConfig, draft.rules, draft.resonances) : null), [baseConfig, draft.rules, draft.resonances]);
  const mutation = useMutation({
    mutationFn: () =>
      runPortfolioBacktest({
        config,
        start_date: startDate || undefined,
        end_date: endDate || undefined,
        candidate_limit: Number(candidateLimit) || config?.candidate_limit || 80,
        max_positions: Number(maxPositions) || 8,
        position_sizing: 'equal_weight',
        max_position_pct: 0.15,
        entry_rule: 'next_open',
        exit_rule: 'hold_days',
        hold_days: Number(holdDays) || 5,
        transaction_cost_bps: 8,
        slippage_bps: 5,
        limit_up_down_model: true,
      }),
  });
  const result = useQuery({
    queryKey: ['portfolio-backtest', mutation.data?.run_id],
    queryFn: () => getPortfolioBacktest(mutation.data?.run_id || ''),
    enabled: Boolean(mutation.data?.run_id),
    refetchInterval: (query) => {
      const run = (query.state.data as Record<string, unknown> | undefined)?.run as Record<string, unknown> | undefined;
      const status = String(run?.status || '');
      return status === 'queued' || status === 'running' ? 2600 : false;
    },
  });
  const run = (result.data?.run || {}) as Record<string, unknown>;
  const summary = (run.summary || {}) as Record<string, unknown>;
  return (
    <section className="surface pad">
      <div className="section-heading">
        <div>
          <h2>组合回测</h2>
          <p>{strategySummary(config)}</p>
        </div>
        <Button disabled={mutation.isPending || !config} icon={<Play size={16} />} onClick={() => mutation.mutate()} variant="primary">
          运行组合回测
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
          <span>候选上限</span>
          <input inputMode="numeric" placeholder={String(config?.candidate_limit || 80)} value={candidateLimit} onChange={(event) => setCandidateLimit(event.target.value)} />
        </label>
        <label>
          <span>最大持仓</span>
          <input inputMode="numeric" value={maxPositions} onChange={(event) => setMaxPositions(event.target.value)} />
        </label>
        <label>
          <span>持有天数</span>
          <input inputMode="numeric" value={holdDays} onChange={(event) => setHoldDays(event.target.value)} />
        </label>
      </div>
      {mutation.data ? (
        <div className="backtest-runline">
          <strong>{String(run.status || mutation.data.status)}</strong>
          <small>{mutation.data.task_id} · {mutation.data.run_id}</small>
        </div>
      ) : null}
      <div className="metric-row">
        <Metric label="总收益" value={formatPercent(summary.total_return)} />
        <Metric label="最大回撤" value={formatPercent(summary.max_drawdown)} />
        <Metric label="胜率" value={formatPercent(summary.win_rate)} />
        <Metric label="交易次数" value={formatRatio(summary.trade_count)} />
        <Metric label="最终权益" value={formatMoney(summary.ending_equity || summary.final_equity)} />
      </div>
      <div className="rule-chip-grid" style={{ marginTop: 14 }}>
        <Badge tone="info">涨停买不进</Badge>
        <Badge tone="info">跌停延后卖出</Badge>
        <Badge>等权持仓</Badge>
        <Badge>异步任务</Badge>
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
