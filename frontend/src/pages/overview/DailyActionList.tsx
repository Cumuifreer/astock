import { AlertCircle, CheckCircle2, Database, PlayCircle } from 'lucide-react';
import type { DailyActionItem } from '../../api/market';
import { Badge } from '../../design/Badge';
import { EmptyState } from '../../design/EmptyState';

type DailyActionListProps = {
  items: DailyActionItem[];
};

export function DailyActionList({ items }: DailyActionListProps) {
  if (!items.length) {
    return <EmptyState title="今日行动清单为空" description="当候选、新风险、观察池到期或数据异常出现时，这里会给出可执行动作。" />;
  }
  return (
    <section className="surface pad">
      <div className="section-heading">
        <div>
          <h2>今日行动清单</h2>
          <p>只保留需要处理的机会、风险、观察池和数据问题。</p>
        </div>
      </div>
      <div className="list-stack">
        {items.map((item) => (
          <article className="rule-card" key={item.id}>
            <div className="rule-card-header">
              <div className="split-row" style={{ justifyContent: 'flex-start' }}>
                {iconFor(item.category)}
                <strong>{item.title}</strong>
              </div>
              <Badge tone={item.priority === 'high' ? 'risk' : item.priority === 'medium' ? 'watch' : 'info'}>{item.priority}</Badge>
            </div>
            <p className="card-copy">{item.description}</p>
            <div className="rule-chip-grid">
              <Badge>{item.category}</Badge>
              <Badge>{item.target_type || 'system'}</Badge>
              {item.action ? <Badge tone="purple">{item.action}</Badge> : null}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function iconFor(category: string) {
  if (category === 'risk') return <AlertCircle size={16} color="var(--danger)" />;
  if (category === 'data') return <Database size={16} color="var(--accent)" />;
  if (category === 'strategy') return <PlayCircle size={16} color="var(--purple)" />;
  return <CheckCircle2 size={16} color="var(--success)" />;
}
