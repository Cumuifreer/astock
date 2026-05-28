import { useMutation } from '@tanstack/react-query';
import { Play } from 'lucide-react';
import { runPortfolioBacktest } from '../../api/backtest';
import { Button } from '../../design/Button';
import { Badge } from '../../design/Badge';
import { formatMoney, formatPercent, formatRatio } from '../../utils/format';
import { todayISO } from '../../utils/date';

export function PortfolioBacktest() {
  const mutation = useMutation({
    mutationFn: () =>
      runPortfolioBacktest({
        start_date: '2024-01-01',
        end_date: todayISO(),
        rebalance: 'daily',
        max_positions: 8,
        position_sizing: 'equal_weight',
        max_position_pct: 0.15,
        entry_rule: 'next_open',
        exit_rule: 'hold_days',
        hold_days: 5,
        transaction_cost_bps: 8,
        slippage_bps: 5,
        limit_up_down_model: true,
      }),
  });
  const run = (mutation.data?.run || {}) as Record<string, unknown>;
  const summary = (run.summary || {}) as Record<string, unknown>;
  return (
    <section className="surface pad">
      <div className="section-heading">
        <div>
          <h2>组合回测</h2>
          <p>加入仓位、调仓、交易成本、滑点和 A 股涨跌停近似成交限制。</p>
        </div>
        <Button disabled={mutation.isPending} icon={<Play size={16} />} onClick={() => mutation.mutate()} variant="primary">
          运行组合回测
        </Button>
      </div>
      <div className="metric-row">
        <Metric label="总收益" value={formatPercent(summary.total_return)} />
        <Metric label="最大回撤" value={formatPercent(summary.max_drawdown)} />
        <Metric label="胜率" value={formatPercent(summary.win_rate)} />
        <Metric label="交易次数" value={formatRatio(summary.trade_count)} />
        <Metric label="最终权益" value={formatMoney(summary.final_equity)} />
      </div>
      <div className="rule-chip-grid" style={{ marginTop: 14 }}>
        <Badge tone="info">涨停买不进</Badge>
        <Badge tone="info">跌停延后卖出</Badge>
        <Badge>等权持仓</Badge>
        <Badge>可复现交易记录</Badge>
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
