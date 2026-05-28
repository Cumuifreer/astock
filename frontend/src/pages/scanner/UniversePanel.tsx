import type { StrategyConfig } from '../../types';
import { Badge } from '../../design/Badge';
import { formatMoney, formatNumber } from '../../utils/format';

export function UniversePanel({ config }: { config: StrategyConfig }) {
  return (
    <section className="surface pad">
      <div className="section-heading">
        <div>
          <h2>Universe 股票池</h2>
          <p>把交易范围、活跃口径、市值、成交额和排序口径放在用户能理解的位置。</p>
        </div>
        <Badge tone="info">{config.include_bj ? '含北交所' : '沪深为主'}</Badge>
      </div>
      <div className="metric-row">
        <Metric label="最低价格" value={`${formatNumber(config.min_price, 2)} 元`} />
        <Metric label="成交额门槛" value={formatMoney(config.min_amount)} />
        <Metric label="流通市值" value={`${formatMoney(config.min_float_market_value)} - ${formatMoney(config.max_float_market_value)}`} />
        <Metric label="候选上限" value={formatNumber(config.candidate_limit)} />
        <Metric label="排序字段" value={config.sort_by || 'signal_score'} />
        <Metric label="科创板" value={config.exclude_star_board ? '排除' : '包含'} />
      </div>
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric-pill">
      <span className="metric-label">{label}</span>
      <div className="metric-value" style={{ fontSize: 15 }}>
        {value}
      </div>
    </div>
  );
}
