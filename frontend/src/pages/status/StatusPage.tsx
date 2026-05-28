import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getTaskCheckpoints, getTaskDag, getTasks } from '../../api/data';
import { Badge } from '../../design/Badge';
import { DataTable } from '../../design/DataTable';
import { LoadingState } from '../../design/LoadingState';
import { useBootstrap } from '../../hooks/useBootstrap';
import { formatDateTime } from '../../utils/date';
import { dagProgress, normalizeRows } from '../../utils/metrics';
import { TaskQueue } from './TaskQueue';
import type { ColumnDef } from '@tanstack/react-table';
import type { TaskRun } from '../../types';
import type { TaskDagNode, UpdateCheckpoint } from '../../api/data';

export function StatusPage() {
  const bootstrap = useBootstrap();
  const activeTasks = useQuery({
    queryKey: ['tasks', 'queued,running'],
    queryFn: () => getTasks({ status: 'queued,running', limit: 50 }),
  });
  const recentTasks = useQuery({
    queryKey: ['tasks', 'recent'],
    queryFn: () => getTasks({ status: 'completed_full,completed_partial,failed', limit: 50 }),
  });
  const fallbackTasks = [bootstrap.data?.update_status, bootstrap.data?.analyze_status, bootstrap.data?.backtest_status, bootstrap.data?.intraday_status, bootstrap.data?.brief_status].filter(Boolean) as TaskRun[];
  const activeRows = normalizeRows<TaskRun>(activeTasks.data);
  const recentRows = normalizeRows<TaskRun>(recentTasks.data);
  const effectiveActiveRows = activeRows.length ? activeRows : fallbackTasks.filter((task) => ['queued', 'running'].includes(task.status));
  const runningTasks = effectiveActiveRows.filter((task) => task.status === 'running');
  const queuedTasks = effectiveActiveRows.filter((task) => task.status === 'queued');
  const failedTasks = recentRows.filter((task) => task.status === 'failed');
  const completedTasks = recentRows.filter((task) => task.status !== 'failed');
  const activeTask = runningTasks[0] || queuedTasks[0] || fallbackTasks.find((task) => ['queued', 'running'].includes(task.status)) || fallbackTasks[0];
  const dag = useQuery({
    queryKey: ['task-dag', activeTask?.id],
    queryFn: () => getTaskDag(activeTask?.id || ''),
    enabled: Boolean(activeTask?.id),
  });
  const checkpoints = useQuery({
    queryKey: ['task-checkpoints', activeTask?.id],
    queryFn: () => getTaskCheckpoints(activeTask?.id || ''),
    enabled: Boolean(activeTask?.id),
  });
  const checkpointRows = normalizeRows<UpdateCheckpoint>(checkpoints.data);
  const dagRows = normalizeRows<TaskDagNode>(dag.data);
  const progressByTaskId = useMemo(() => {
    if (!activeTask || activeTask.kind !== 'update') return {};
    if (!['queued', 'running'].includes(activeTask.status)) return {};
    return { [activeTask.id]: dagProgress(dagRows) };
  }, [activeTask, dagRows]);
  const checkpointColumns = useMemo<Array<ColumnDef<UpdateCheckpoint, unknown>>>(
    () => [
      { header: '节点', accessorKey: 'job_id' },
      { header: '数据类别', accessorKey: 'capability' },
      { header: '批次', accessorKey: 'batch_key' },
      { header: '状态', accessorKey: 'status', cell: ({ row }) => <Badge>{checkpointStatusLabel(row.original.status)}</Badge> },
      { header: '写入行数', accessorKey: 'rows_written' },
      { header: '完成时间', accessorKey: 'finished_at', cell: ({ row }) => formatDateTime(row.original.finished_at) },
    ],
    [],
  );

  if (bootstrap.isLoading || activeTasks.isLoading) return <LoadingState label="读取任务状态" />;

  return (
    <div className="page-grid">
      <section className="surface pad">
        <div className="section-heading">
          <div>
            <h2>当前运行任务</h2>
            <p>任务队列、今日已完成任务、失败任务和定时计划统一在这里。</p>
          </div>
          <Badge tone={activeTask ? 'info' : 'neutral'}>{activeTask ? '有任务' : '系统待命'}</Badge>
        </div>
        <section className="task-status-grid">
          <TaskQueue emptyLabel="当前没有运行中的任务" title="当前运行" tasks={runningTasks} progressByTaskId={progressByTaskId} />
          <TaskQueue emptyLabel="等待队列为空" title="等待队列" tasks={queuedTasks} progressByTaskId={progressByTaskId} />
          <TaskQueue emptyLabel="暂无最近完成任务" title="最近完成" tasks={completedTasks.slice(0, 6)} />
          <TaskQueue emptyLabel="暂无失败任务" title="失败任务" tasks={failedTasks.slice(0, 6)} />
        </section>
      </section>

      <details className="developer-details surface pad">
        <summary>开发者详情</summary>
        <section className="grid-2" style={{ marginTop: 16 }}>
          <div>
            <div className="section-heading">
              <div>
                <h2>同步流程节点</h2>
                <p>展示每个数据节点的依赖、覆盖策略、请求策略和当前状态。</p>
              </div>
            </div>
            <div className="list-stack">
              {dagRows.map((node) => (
                <div className="split-row" key={node.id}>
                  <span>{node.label || node.id}</span>
                  <Badge>{checkpointStatusLabel(node.status)}</Badge>
                </div>
              ))}
              {!dagRows.length ? <p className="card-copy">暂无流程数据。</p> : null}
            </div>
          </div>

          <div>
            <div className="section-heading">
              <div>
                <h2>进度节点列表</h2>
                <p>读取真实进度节点，不只依赖任务摘要。</p>
              </div>
            </div>
            <DataTable data={checkpointRows} columns={checkpointColumns} />
          </div>
        </section>
      </details>
    </div>
  );
}

function checkpointStatusLabel(status?: string | null) {
  if (status === 'queued') return '排队中';
  if (status === 'running') return '运行中';
  if (status === 'completed') return '已完成';
  if (status === 'partial') return '部分完成';
  if (status === 'failed') return '失败';
  if (status === 'skipped') return '已跳过';
  return status || '待更新';
}
