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
            <strong>{kindLabel(task.kind)}</strong>
            <Badge tone={task.status === 'failed' ? 'risk' : task.status === 'running' ? 'info' : 'good'}>{statusLabel(task.status)}</Badge>
          </div>
          <p className="card-copy">
            {task.stage || '等待阶段'} · 最近心跳 {formatDateTime(task.updated_at)}
          </p>
          <Progress label={`${kindLabel(task.kind)} ${statusLabel(task.status)}`} state={task.status} value={taskProgressValue(task, progressByTaskId[task.id])} />
          <div className="rule-chip-grid">
            <Badge>已处理 {task.processed}</Badge>
            <Badge>成功 {task.success}</Badge>
            <Badge>失败 {task.failed}</Badge>
            <Badge>跳过 {task.skipped}</Badge>
          </div>
        </article>
      ))}
    </div>
  );
}

function kindLabel(kind?: string | null) {
  if (kind === 'update') return '同步今日数据';
  if (kind === 'analyze') return '运行策略';
  if (kind === 'backtest') return '回测';
  if (kind === 'intraday') return '盘中采样';
  if (kind === 'brief') return '市场简报';
  return kind || '任务';
}

function statusLabel(status?: string | null) {
  if (status === 'queued') return '排队中';
  if (status === 'running') return '运行中';
  if (status === 'completed_full') return '已完成';
  if (status === 'completed_partial') return '部分完成';
  if (status === 'failed') return '失败';
  if (status === 'skipped') return '已跳过';
  return status || '未知';
}
