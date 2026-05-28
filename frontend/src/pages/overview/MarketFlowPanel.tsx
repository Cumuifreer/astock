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
];

export function MarketFlowPanel({ pulse, freshness }: MarketFlowPanelProps) {
  return (
    <section className="grid-2">
      <div className="surface pad">
        <div className="section-heading">
          <div>
            <h2>市场状态</h2>
            <p>市场环境拆解为宽度、情绪、成交和指数趋势。</p>
          </div>
        </div>
        <div className="metric-row market-state-grid">
          {pulseLabels.map(([key, label]) => {
            const value = typeof pulse?.[key] === 'number' ? Number(pulse?.[key]) : null;
            return (
              <div className="metric-pill" key={key}>
                <span className="metric-label">{label}</span>
                <div className="metric-value">{value === null ? '待同步' : formatNumber(value, 0)}</div>
                <p className="metric-note">{marketMetricNote(key, value)}</p>
              </div>
            );
          })}
        </div>
      </div>
      <div className="surface pad">
        <div className="section-heading">
          <div>
            <h2>数据状态</h2>
            <p>只展示影响今日决策的关键数据。</p>
          </div>
        </div>
        <div className="list-stack">
          {(freshness.length ? freshness : [{ label: '补充交易数据', latest_update: null, status: 'waiting' }]).map((item, index) => {
            const latest = item.latest_update || item.latest_date;
            return (
              <div className="split-row" key={`${item.label || item.capability}-${index}`}>
                <span>{friendlyLabel(item.label || item.capability || '数据集')}</span>
                <Badge tone={item.status === 'normal' || item.status === 'fresh' ? 'good' : 'watch'}>{latest ? formatDate(latest) : statusText(item.status)}</Badge>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}

function friendlyLabel(label: string) {
  return label
    .replace('历史 K 线', '历史行情')
    .replace('当日快照', '今日行情');
}

function statusText(status?: string) {
  if (status === 'missing') return '待同步';
  if (status === 'stale') return '需更新';
  return '暂无数据';
}

function marketMetricNote(key: string, value: number | null) {
  if (value === null) return '同步今日数据后显示。';
  if (key === 'breadth_score') {
    if (value >= 70) return '上涨股票占比较高，市场承接较强。';
    if (value >= 45) return '上涨股票占比中性，适合精选个股。';
    return '上涨股票占比偏低，先控制仓位。';
  }
  if (key === 'limit_score') {
    if (value >= 70) return '涨停情绪偏热，注意分歧。';
    if (value >= 40) return '涨跌停情绪中性。';
    return '跌停压力偏高，少追高。';
  }
  if (key === 'turnover_score') {
    if (value >= 70) return '成交额明显放大，资金活跃。';
    if (value >= 40) return '成交额接近近期均值。';
    return '成交额偏弱，流动性不足。';
  }
  if (value >= 70) return '指数趋势偏强。';
  if (value >= 45) return '指数趋势震荡。';
  return '指数趋势偏弱。';
}
