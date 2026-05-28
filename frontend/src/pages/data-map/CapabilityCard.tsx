import type { Capability } from '../../types';
import { Badge } from '../../design/Badge';
import { Button } from '../../design/Button';
import { formatDate } from '../../utils/date';
import { capabilityHealth } from '../../utils/metrics';

export function CapabilityCard({
  capability,
  onBackfill,
  backfilling,
}: {
  capability: Capability;
  onBackfill?: (capability: Capability) => void;
  backfilling?: boolean;
}) {
  const health = capabilityHealth(capability);
  return (
    <article className="card">
      <div className="split-row">
        <h3 className="card-title">{capability.capability}</h3>
        <Badge tone={health === 'normal' ? 'good' : health === 'missing' || health === 'partial' ? 'risk' : 'watch'}>{labelFor(health)}</Badge>
      </div>
      <p className="card-copy">
        最新：{formatDate(capability.latest_update)} · 覆盖 {capability.coverage_count} · 缺失 {capability.missing_count}
      </p>
      <div className="rule-chip-grid" style={{ marginTop: 12 }}>
        {capability.participates_in_analysis ? <Badge tone="info">参与分析</Badge> : <Badge>上下文/事件</Badge>}
        {capability.can_backfill ? <Badge tone="purple">可补齐</Badge> : null}
        {capability.actual_sources.slice(0, 2).map((source) => (
          <Badge key={source}>{source}</Badge>
        ))}
      </div>
      {capability.last_failure_reason ? <p className="card-copy" style={{ marginTop: 12, color: 'var(--danger)' }}>{capability.last_failure_reason}</p> : null}
      {capability.can_backfill ? (
        <div className="rule-card-actions">
          <Button disabled={backfilling || !onBackfill} onClick={() => onBackfill?.(capability)} variant="ghost">
            {backfilling ? '已加入队列' : '补齐'}
          </Button>
        </div>
      ) : null}
    </article>
  );
}

function labelFor(health: ReturnType<typeof capabilityHealth>) {
  if (health === 'normal') return '正常';
  if (health === 'missing') return '缺失';
  if (health === 'low') return '低覆盖';
  if (health === 'partial') return '部分完成';
  return '过期';
}
