import type { DataFreshnessItem, MarketPulse } from '../../api/market';
import { Badge } from '../../design/Badge';
import { formatDate } from '../../utils/date';
import { formatNumber } from '../../utils/format';

type MarketFlowPanelProps = {
  pulse?: MarketPulse;
  freshness: DataFreshnessItem[];
};

const pulseLabels: Array<[string, string]> = [
  ['breadth_score', '市场宽度'],
  ['limit_score', '涨跌停温度'],
  ['turnover_score', '成交额热度'],
  ['index_score', '指数趋势'],
  ['sector_heat_score', '题材扩散'],
];

export function MarketFlowPanel({ pulse, freshness }: MarketFlowPanelProps) {
  return (
    <section className="grid-2">
      <div className="surface pad">
        <div className="section-heading">
          <div>
            <h2>Market Pulse</h2>
            <p>市场环境拆解为宽度、成交、指数、题材和风险。</p>
          </div>
        </div>
        <div className="metric-row">
          {pulseLabels.map(([key, label]) => (
            <div className="metric-pill" key={key}>
              <span className="metric-label">{label}</span>
              <div className="metric-value">{formatNumber(pulse?.[key], 0)}</div>
            </div>
          ))}
        </div>
      </div>
      <div className="surface pad">
        <div className="section-heading">
          <div>
            <h2>数据新鲜度</h2>
            <p>只展示影响今日决策的关键数据。</p>
          </div>
        </div>
        <div className="list-stack">
          {(freshness.length ? freshness : [{ label: 'Tushare 增强', latest_update: null, status: 'waiting' }]).map((item, index) => (
            <div className="split-row" key={`${item.label || item.capability}-${index}`}>
              <span>{item.label || item.capability || '数据集'}</span>
              <Badge tone={item.status === 'normal' || item.status === 'fresh' ? 'good' : 'watch'}>{formatDate(item.latest_update || item.latest_date)}</Badge>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
