import type { ThemePulse } from '../../api/intraday';
import { Badge } from '../../design/Badge';
import { formatMoney, formatPercent, formatRatio } from '../../utils/format';

export function IntradayTimeline({ themes }: { themes: ThemePulse[] }) {
  return (
    <section className="surface pad">
      <div className="section-heading">
        <div>
          <h2>题材同步脉冲</h2>
          <p>把盘中异动和板块热力连接起来，避免只看孤立个股。</p>
        </div>
      </div>
      <div className="rule-chip-grid">
        {themes.slice(0, 10).map((theme, index) => (
          <Badge key={`${theme.name || theme.sector_name}-${index}`} tone="purple">
            {theme.name || theme.sector_name || '题材'} · {formatRatio(theme.heat_score)} · {formatPercent(theme.pct_chg)} · {formatMoney(theme.net_amount)}
          </Badge>
        ))}
        {!themes.length ? <Badge>等待板块脉冲</Badge> : null}
      </div>
    </section>
  );
}
