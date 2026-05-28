import type { WatchlistItem } from '../../types';
import { Badge } from '../../design/Badge';
import { Button } from '../../design/Button';
import { formatDate } from '../../utils/date';
import { formatNumber, formatPercent, toNumber } from '../../utils/format';

export type HypothesisItem = WatchlistItem & {
  hypothesis?: string | null;
  invalidation_rule?: string | null;
  trigger_rules?: string[];
  tags?: string[];
};

type HypothesisCardProps = {
  item: HypothesisItem;
  onEdit: (item: HypothesisItem, field: 'note' | 'invalidation_rule' | 'review_status') => void;
  onDelete: (item: HypothesisItem) => void;
};

export function HypothesisCard({ item, onEdit, onDelete }: HypothesisCardProps) {
  return (
    <article className="rule-card">
      <div className="rule-card-header">
        <strong>
          {item.code} · {item.name}
        </strong>
        <Badge tone={statusTone(normalizeStatus(item.review_status))}>{normalizeStatus(item.review_status)}</Badge>
      </div>
      <p className="card-copy">{item.hypothesis || item.note || '等待补充交易假设'}</p>
      <div className="metric-row">
        <Metric label="加入日期" value={formatDate(item.entry_date)} />
        <Metric label="加入价" value={formatNumberStatus(item.entry_price, '待确认')} />
        <Metric label="当前价" value={formatNumberStatus(item.latest_close, '待更新')} />
        <Metric label="触发来源" value={sourceLabel(item.source_type, item.source_label)} />
      </div>
      <div className="grid-2">
        <div>
          <span className="metric-label">失效条件</span>
          <p className="card-copy">{item.invalidation_rule || '未设置'}</p>
        </div>
        <div>
          <span className="metric-label">后验收益</span>
          <p className="card-copy">
            T+1 {formatPercentStatus(item.return_1d)} · T+3 {formatPercentStatus(item.return_3d)} · T+5 {formatPercentStatus(item.return_5d)} · 最新{' '}
            {formatPercentStatus(item.return_latest)}
          </p>
        </div>
      </div>
      <div className="rule-chip-grid">
        {(item.trigger_rules || item.reasons || []).slice(0, 4).map((rule) => (
          <Badge key={rule} tone="info">
            {rule}
          </Badge>
        ))}
        {(item.tags || []).map((tag) => (
          <Badge key={tag} tone="purple">
            {tag}
          </Badge>
        ))}
      </div>
      <div className="rule-card-actions">
        <Button onClick={() => onEdit(item, 'note')} variant="ghost">
          编辑备注
        </Button>
        <Button onClick={() => onEdit(item, 'invalidation_rule')} variant="ghost">
          编辑失效条件
        </Button>
        <Button onClick={() => onEdit(item, 'review_status')} variant="ghost">
          编辑状态
        </Button>
        <Button onClick={() => onDelete(item)} variant="danger">
          删除
        </Button>
      </div>
    </article>
  );
}

function normalizeStatus(status?: string | null) {
  if (status === '有效' || status === '误报' || status === '已归档') return status;
  if (status === '归档' || status === '已放弃' || status === '已验证' || status === '已错过') return '已归档';
  return '观察中';
}

function statusTone(status: string): 'good' | 'watch' | 'risk' | 'neutral' {
  if (status === '有效') return 'good';
  if (status === '误报') return 'risk';
  if (status === '已归档') return 'neutral';
  return 'watch';
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric-pill">
      <span className="metric-label">{label}</span>
      <div className="card-copy">{value}</div>
    </div>
  );
}

function formatNumberStatus(value: unknown, fallback: string) {
  return toNumber(value) === null ? fallback : formatNumber(value, 2);
}

function formatPercentStatus(value: unknown) {
  return toNumber(value) === null ? '待复盘' : formatPercent(value);
}

function sourceLabel(sourceType?: string | null, sourceLabel?: string | null) {
  const label = String(sourceLabel || '').trim();
  if (/scanner/i.test(label)) return '策略选股候选';
  if (label) return label;
  if (sourceType === 'intraday') return '盘中雷达';
  if (sourceType === 'manual') return '手动';
  return '策略选股';
}
