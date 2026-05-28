import type { IntradayCandidate } from '../../api/intraday';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Badge } from '../../design/Badge';
import { Button } from '../../design/Button';
import { EmptyState } from '../../design/EmptyState';
import { addWatchlistItems } from '../../api/watchlist';
import { formatMoney, formatPercent, formatRatio } from '../../utils/format';

type IntradayBoardProps = {
  rows: IntradayCandidate[];
  tone: 'info' | 'good' | 'risk';
};

export function IntradayBoard({ rows, tone }: IntradayBoardProps) {
  const queryClient = useQueryClient();
  const addMutation = useMutation({
    mutationFn: (row: IntradayCandidate) =>
      addWatchlistItems({
        source_type: 'intraday',
        source_label: '盘中雷达',
        source_ref: row.code,
        items: [
          {
            code: row.code,
            name: row.name,
            entry_price: row.metrics?.latest_price || null,
            reasons: row.reasons || row.signal_tags || [],
            metrics: row.metrics || {},
            hypothesis: (row.reasons || row.signal_tags || []).slice(0, 2).join('；'),
            invalidation_rule: '跌破分时均价或题材热度回落',
          },
        ],
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['watchlist'] });
      void queryClient.invalidateQueries({ queryKey: ['bootstrap'] });
    },
  });
  if (!rows.length) return <EmptyState title="暂无盘中异动" description="完成两次以上采样后，会显示成交变化和榜单原因。" />;
  return (
    <div className="list-stack">
      {rows.map((row) => {
        const metrics = row.metrics || {};
        const amountSpeed = row.intraday_amount_speed ?? row.amount_speed ?? metrics.intraday_amount_speed;
        const amountDelta = row.amount_delta ?? metrics.amount_delta;
        const themeSync = row.theme_sync_score ?? metrics.theme_sync_score;
        const drawdown = row.intraday_drawdown ?? metrics.intraday_drawdown;
        return (
        <article className="rule-card" key={row.code}>
          <div className="rule-card-header">
            <strong>
              {row.rank ? `${row.rank}. ` : ''}{row.code} · {row.name || '待确认'}
            </strong>
            <Badge tone={tone}>{formatPercent(row.pct_chg)}</Badge>
          </div>
          <div className="metric-row">
            <div className="metric-pill">
              <span className="metric-label">成交额</span>
              <div className="metric-value">{formatMoney(row.amount ?? metrics.amount)}</div>
            </div>
            <div className="metric-pill">
              <span className="metric-label">成交速度</span>
              <div className="metric-value">{amountSpeed == null ? '样本不足' : formatRatio(amountSpeed)}</div>
            </div>
            <div className="metric-pill">
              <span className="metric-label">成交增量</span>
              <div className="metric-value">{amountDelta == null ? '需要两次采样' : formatMoney(amountDelta)}</div>
            </div>
            <div className="metric-pill">
              <span className="metric-label">题材同步</span>
              <div className="metric-value">{themeSync == null ? '题材数据待同步' : formatRatio(themeSync)}</div>
              {row.strong_theme_name || metrics.strong_theme_name ? <small>{String(row.strong_theme_name || metrics.strong_theme_name)}</small> : null}
            </div>
            <div className="metric-pill">
              <span className="metric-label">日内回落</span>
              <div className="metric-value">{drawdown == null ? '样本不足' : formatPercent(Number(drawdown) * 100)}</div>
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
          <div className="rule-card-actions">
            <Button disabled={addMutation.isPending} onClick={() => addMutation.mutate(row)} variant="ghost">
              加入观察池
            </Button>
            {row.chart_url ? (
              <Button onClick={() => window.open(row.chart_url || '', '_blank', 'noopener,noreferrer')} variant="ghost">
                打开 K 线
              </Button>
            ) : null}
            <Button onClick={() => window.location.hash = `#intraday?code=${encodeURIComponent(row.code)}`} variant="ghost">
              查看分时轨迹
            </Button>
          </div>
        </article>
        );
      })}
    </div>
  );
}
