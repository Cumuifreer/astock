import type { TaskRun } from '../../types';
import { Badge } from '../../design/Badge';
import { Progress } from '../../design/Progress';
import { formatDateTime } from '../../utils/date';
import { taskProgressValue } from '../../utils/metrics';

type TaskQueueProps = {
  tasks: TaskRun[];
  progressByTaskId?: Record<string, number | null | undefined>;
  title?: string;
  emptyLabel?: string;
};

export function TaskQueue({ tasks, progressByTaskId = {}, title, emptyLabel = '暂无运行任务' }: TaskQueueProps) {
  if (!tasks.length) {
    return (
      <div className="empty-state">
        {title ? <strong>{title}</strong> : null}
        <div>{emptyLabel}</div>
      </div>
    );
  }
  return (
    <div className="list-stack">
      {title ? <h3 className="subsection-title">{title}</h3> : null}
      {tasks.map((task) => (
        <article className="rule-card" key={task.id}>
          <div className="rule-card-header">
            <strong>{task.kind}</strong>
            <Badge tone={task.status === 'failed' ? 'risk' : task.status === 'running' ? 'info' : 'good'}>{task.status}</Badge>
          </div>
          <p className="card-copy">
            {task.stage || '等待阶段'} · {task.source || '本地仓库'} · 心跳 {formatDateTime(task.updated_at)}
          </p>
          <Progress label={`${task.kind} ${task.status}`} state={task.status} value={taskProgressValue(task, progressByTaskId[task.id])} />
          <div className="rule-chip-grid">
            <Badge>processed {task.processed}</Badge>
            <Badge>success {task.success}</Badge>
            <Badge>failed {task.failed}</Badge>
            <Badge>skipped {task.skipped}</Badge>
          </div>
        </article>
      ))}
    </div>
  );
}
