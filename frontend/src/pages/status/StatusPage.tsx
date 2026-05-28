import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getTaskCheckpoints, getTaskDag } from '../../api/data';
import { Badge } from '../../design/Badge';
import { DataTable } from '../../design/DataTable';
import { LoadingState } from '../../design/LoadingState';
import { useBootstrap } from '../../hooks/useBootstrap';
import { formatDateTime } from '../../utils/date';
import { normalizeRows } from '../../utils/metrics';
import { TaskQueue } from './TaskQueue';
import type { ColumnDef } from '@tanstack/react-table';
import type { TaskRun } from '../../types';
import type { TaskDagNode, UpdateCheckpoint } from '../../api/data';

export function StatusPage() {
  const bootstrap = useBootstrap();
  const tasks = [bootstrap.data?.update_status, bootstrap.data?.analyze_status, bootstrap.data?.backtest_status, bootstrap.data?.intraday_status, bootstrap.data?.brief_status].filter(Boolean) as TaskRun[];
  const activeTask = tasks.find((task) => ['queued', 'running'].includes(task.status)) || tasks[0];
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

  if (bootstrap.isLoading) return <LoadingState label="读取任务状态" />;

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
        <TaskQueue tasks={tasks} />
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
