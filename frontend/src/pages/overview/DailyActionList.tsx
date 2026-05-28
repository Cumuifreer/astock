import { AlertCircle, CheckCircle2, Database, PlayCircle } from 'lucide-react';
import type { DailyActionItem } from '../../api/market';
import { Badge } from '../../design/Badge';
import { EmptyState } from '../../design/EmptyState';

type DailyActionListProps = {
  items: DailyActionItem[];
};

export function DailyActionList({ items }: DailyActionListProps) {
  if (!items.length) {
    return <EmptyState title="暂无今日提示" description="当市场、候选或数据状态出现需要关注的变化时，这里会给出提示。" />;
  }
  return (
    <section className="surface pad">
      <div className="section-heading">
        <div>
          <h2>今日提示</h2>
          <p>只保留投资者能直接理解的机会、风险和数据提示。</p>
        </div>
      </div>
      <div className="list-stack">
        {items.slice(0, 3).map((item) => (
          <article className="rule-card" key={item.id}>
            <div className="rule-card-header">
              <div className="split-row" style={{ justifyContent: 'flex-start' }}>
                {iconFor(item.category)}
                <strong>{item.title}</strong>
              </div>
              <Badge tone={item.priority === 'high' ? 'risk' : item.priority === 'medium' ? 'watch' : 'info'}>{priorityLabel(item.priority)}</Badge>
            </div>
            <p className="card-copy">{item.description}</p>
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

function priorityLabel(priority: string) {
  if (priority === 'high') return '高';
  if (priority === 'medium') return '中';
  if (priority === 'low') return '低';
  return priority || '提示';
}
