import type { IntradayCandidate } from '../../api/intraday';
import { Badge } from '../../design/Badge';
import { EmptyState } from '../../design/EmptyState';
import { formatMoney, formatPercent, formatRatio } from '../../utils/format';

type IntradayBoardProps = {
  rows: IntradayCandidate[];
  tone: 'info' | 'good' | 'risk';
};

export function IntradayBoard({ rows, tone }: IntradayBoardProps) {
  if (!rows.length) return <EmptyState title="暂无盘中候选" description="盘中采样后会基于多次快照生成榜单。" />;
  return (
    <div className="list-stack">
      {rows.map((row) => (
        <article className="rule-card" key={row.code}>
          <div className="rule-card-header">
            <strong>
              {row.code} · {row.name || '--'}
            </strong>
            <Badge tone={tone}>{formatPercent(row.pct_chg)}</Badge>
          </div>
          <div className="metric-row">
            <div className="metric-pill">
              <span className="metric-label">成交速度</span>
              <div className="metric-value">{formatRatio(row.intraday_amount_speed ?? row.amount_speed)}</div>
            </div>
            <div className="metric-pill">
              <span className="metric-label">成交增量</span>
              <div className="metric-value">{formatMoney(row.amount_delta)}</div>
            </div>
            <div className="metric-pill">
              <span className="metric-label">题材同步</span>
              <div className="metric-value">{formatRatio(row.theme_sync_score)}</div>
            </div>
          </div>
          <div className="rule-chip-grid">
            {(row.signal_tags || row.reasons || []).slice(0, 4).map((tag) => (
              <Badge key={tag}>{tag}</Badge>
            ))}
            {(row.risk_tags || []).slice(0, 3).map((tag) => (
              <Badge key={tag} tone="risk">
                {tag}
              </Badge>
            ))}
          </div>
        </article>
      ))}
    </div>
  );
}
