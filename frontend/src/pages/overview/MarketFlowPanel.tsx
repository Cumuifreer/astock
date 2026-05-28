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
            <h2>市场状态</h2>
            <p>市场环境拆解为宽度、成交、指数和题材扩散。</p>
          </div>
        </div>
        <div className="metric-row">
          {pulseLabels.map(([key, label]) => (
            <div className="metric-pill" key={key}>
              <span className="metric-label">{label}</span>
              <div className="metric-value">{pulse?.[key] === null || pulse?.[key] === undefined ? '待同步' : formatNumber(pulse?.[key], 0)}</div>
            </div>
          ))}
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
    .replace('当日快照', '今日行情')
    .replace('Tushare 增强', '补充交易数据');
}

function statusText(status?: string) {
  if (status === 'missing') return '待同步';
  if (status === 'stale') return '需更新';
  return '暂无数据';
}
