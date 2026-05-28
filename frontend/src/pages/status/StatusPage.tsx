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
      { header: 'job', accessorKey: 'job_id' },
      { header: 'capability', accessorKey: 'capability' },
      { header: 'batch', accessorKey: 'batch_key' },
      { header: 'status', accessorKey: 'status', cell: ({ row }) => <Badge>{row.original.status}</Badge> },
      { header: 'rows_written', accessorKey: 'rows_written' },
      { header: 'finished', accessorKey: 'finished_at', cell: ({ row }) => formatDateTime(row.original.finished_at) },
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
            <p>任务队列、今日已完成任务、失败任务、定时计划和开发者详情统一在这里。</p>
          </div>
          <Badge tone={activeTask ? 'info' : 'neutral'}>{activeTask?.id || 'idle'}</Badge>
        </div>
        <section className="task-status-grid">
          <TaskQueue emptyLabel="当前没有运行中的任务" title="当前运行" tasks={runningTasks} progressByTaskId={progressByTaskId} />
          <TaskQueue emptyLabel="等待队列为空" title="等待队列" tasks={queuedTasks} progressByTaskId={progressByTaskId} />
          <TaskQueue emptyLabel="暂无最近完成任务" title="最近完成" tasks={completedTasks.slice(0, 6)} />
          <TaskQueue emptyLabel="暂无失败任务" title="失败任务" tasks={failedTasks.slice(0, 6)} />
        </section>
      </section>

      <section className="grid-2">
        <div className="surface pad">
          <div className="section-heading">
            <div>
              <h2>数据更新 DAG 进度</h2>
              <p>展示每个 capability 的依赖、覆盖策略、请求策略和当前状态。</p>
            </div>
          </div>
          <div className="list-stack">
            {dagRows.map((node) => (
              <div className="split-row" key={node.id}>
                <span>{node.label || node.id}</span>
                <Badge>{node.status || 'queued'}</Badge>
              </div>
            ))}
            {!dagRows.length ? <p className="card-copy">暂无 DAG 数据。</p> : null}
          </div>
        </div>

        <div className="surface pad">
          <div className="section-heading">
            <div>
              <h2>checkpoint 列表</h2>
              <p>状态页读取 update_checkpoints，不只依赖 summary_json。</p>
            </div>
          </div>
          <DataTable data={checkpointRows} columns={checkpointColumns} />
        </div>
      </section>
    </div>
  );
}
