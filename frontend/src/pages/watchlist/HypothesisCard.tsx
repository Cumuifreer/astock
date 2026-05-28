import type { WatchlistItem } from '../../types';
import { Badge } from '../../design/Badge';
import { Button } from '../../design/Button';
import { formatPercent } from '../../utils/format';

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
        <Badge tone={statusTone(item.review_status)}>{item.review_status || '观察中'}</Badge>
      </div>
      <p className="card-copy">{item.hypothesis || item.note || '等待补充交易假设'}</p>
      <div className="grid-2">
        <div>
          <span className="metric-label">失效条件</span>
          <p className="card-copy">{item.invalidation_rule || '未设置'}</p>
        </div>
        <div>
          <span className="metric-label">后验收益</span>
          <p className="card-copy">
            T+1 {formatPercent(item.return_1d)} · T+5 {formatPercent(item.return_5d)} · 最新 {formatPercent(item.return_latest)}
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

function statusTone(status: string): 'good' | 'watch' | 'risk' | 'neutral' {
  if (status === '有效') return 'good';
  if (status === '误报' || status === '已放弃') return 'risk';
  if (status === '归档') return 'neutral';
  return 'watch';
}
