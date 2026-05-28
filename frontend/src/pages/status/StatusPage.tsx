import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getTaskFlow, getTaskProgressNodes, getTasks } from '../../api/data';
import { Badge } from '../../design/Badge';
import { Button } from '../../design/Button';
import { DataTable } from '../../design/DataTable';
import { LoadingState } from '../../design/LoadingState';
import { Progress } from '../../design/Progress';
import { useBootstrap } from '../../hooks/useBootstrap';
import { formatDateTime } from '../../utils/date';
import { flowProgress, normalizeRows, taskProgressValue } from '../../utils/metrics';
import type { ColumnDef } from '@tanstack/react-table';
import type { TaskRun } from '../../types';
import type { TaskFlowNode, TaskProgressNode } from '../../api/data';

export function StatusPage() {
  const [showMaintenance, setShowMaintenance] = useState(false);
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
  const activeTask = runningTasks[0] || queuedTasks[0] || fallbackTasks.find((task) => ['queued', 'running'].includes(task.status)) || fallbackTasks[0];
  const scheduler = bootstrap.data?.runtime_health?.scheduler;
  const llm = bootstrap.data?.runtime_health?.llm;
  const taskFlow = useQuery({
    queryKey: ['task-flow', activeTask?.id],
    queryFn: () => getTaskFlow(activeTask?.id || ''),
    enabled: Boolean(activeTask?.id),
  });
  const progressNodes = useQuery({
    queryKey: ['task-progress-nodes', activeTask?.id],
    queryFn: () => getTaskProgressNodes(activeTask?.id || ''),
    enabled: Boolean(activeTask?.id),
  });
  const progressRows = normalizeRows<TaskProgressNode>(progressNodes.data);
  const flowRows = normalizeRows<TaskFlowNode>(taskFlow.data);
  const progressByTaskId = useMemo(() => {
    if (!activeTask || activeTask.kind !== 'update') return {};
    if (!['queued', 'running'].includes(activeTask.status)) return {};
    return { [activeTask.id]: flowProgress(flowRows) };
  }, [activeTask, flowRows]);
  const progressColumns = useMemo<Array<ColumnDef<TaskProgressNode, unknown>>>(
    () => [
      { header: '节点', accessorKey: 'job_id' },
      { header: '数据类别', accessorKey: 'capability' },
      { header: '批次', accessorKey: 'batch_key' },
      { header: '状态', accessorKey: 'status', cell: ({ row }) => <Badge>{progressStatusLabel(row.original.status)}</Badge> },
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
            <h2>任务状态</h2>
            <p>查看当前任务、等待队列、定时计划和最近失败原因。</p>
          </div>
          <Badge tone={activeTask ? 'info' : 'neutral'}>{activeTask ? '有任务' : '系统待命'}</Badge>
        </div>
        <div className="grid-4 status-summary-grid">
          <Metric label="系统状态" value={systemLabel(activeTask)} />
          <Metric label="任务队列" value={`运行 ${runningTasks.length} · 排队 ${queuedTasks.length}`} />
          <Metric label="定时计划" value={schedulerLabel(scheduler)} />
          <Metric label="AI 模型" value={llmLabel(llm)} tone={llm?.configured ? 'neutral' : 'risk'} />
          <Metric label="最近失败" value={failedTasks[0]?.error_message || failedTasks[0]?.warning || '无'} tone={failedTasks.length ? 'risk' : 'neutral'} />
        </div>
        {activeTask && ['queued', 'running'].includes(activeTask.status) ? (
          <article className="task-progress-card" style={{ marginTop: 16 }}>
            <div className="rule-card-header">
              <strong>当前任务：{kindLabel(activeTask.kind)}</strong>
              <Badge tone={activeTask.status === 'running' ? 'info' : 'watch'}>{taskStatusLabel(activeTask.status)}</Badge>
            </div>
            <Progress label="当前任务进度" state={activeTask.status} value={taskProgressValue(activeTask, progressByTaskId[activeTask.id])} />
            <p className="card-copy">
              当前步骤：{activeTask.stage || '等待开始'} · 已完成 {activeTask.processed} / 共 {activeTask.total || progressRows.length || 0}
            </p>
          </article>
        ) : null}
        <div className="button-row" style={{ marginTop: 16 }}>
          <Button onClick={() => setShowMaintenance((value) => !value)} variant="secondary">
            {showMaintenance ? '收起维护信息' : '查看维护信息'}
          </Button>
        </div>
      </section>

      {showMaintenance ? (
      <section className="maintenance-details surface pad">
        <section className="grid-2" style={{ marginTop: 16 }}>
          <div>
            <div className="section-heading">
              <div>
                <h2>同步流程节点</h2>
                <p>展示每个数据节点的依赖、覆盖策略、请求策略和当前状态。</p>
              </div>
            </div>
            <div className="list-stack">
              {flowRows.map((node) => (
                <div className="split-row" key={node.id}>
                  <span>{node.label || node.id}</span>
                  <Badge>{progressStatusLabel(node.status)}</Badge>
                </div>
              ))}
              {!flowRows.length ? <p className="card-copy">暂无流程数据。</p> : null}
            </div>
          </div>

          <div>
            <div className="section-heading">
              <div>
                <h2>进度节点列表</h2>
                <p>读取真实进度节点，不只依赖任务摘要。</p>
              </div>
            </div>
            <DataTable data={progressRows} columns={progressColumns} />
          </div>
        </section>
      </section>
      ) : null}
    </div>
  );
}

function progressStatusLabel(status?: string | null) {
  if (status === 'queued') return '排队中';
  if (status === 'running') return '运行中';
  if (status === 'completed') return '已完成';
  if (status === 'partial') return '部分完成';
  if (status === 'failed') return '失败';
  if (status === 'skipped') return '已跳过';
  return status || '待更新';
}

function Metric({ label, value, tone = 'neutral' }: { label: string; value: string; tone?: 'neutral' | 'risk' }) {
  return (
    <article className={tone === 'risk' ? 'metric-pill status-metric-card risk' : 'metric-pill status-metric-card'}>
      <span className="metric-label">{label}</span>
      <div className={tone === 'risk' ? 'metric-value text-risk' : 'metric-value'}>{value}</div>
    </article>
  );
}

function schedulerLabel(scheduler?: { enabled?: boolean; next_slot?: { time?: string | null; sample_at?: string | null } | null; remaining_count?: number; latest_slot?: { sample_at?: string | null; status?: string | null } | null } | null) {
  if (!scheduler?.enabled) return '未开启';
  const next = scheduler.next_slot?.time || scheduler.next_slot?.sample_at;
  const latest = scheduler.latest_slot?.sample_at;
  const remaining = scheduler.remaining_count ?? 0;
  return `${latest ? `最近 ${formatDateTime(latest)}` : '最近暂无'} · ${next ? `下次 ${next}` : '下次待定'} · 今日还剩 ${remaining} 次`;
}

function llmLabel(llm?: { configured?: boolean; model?: string | null; url_host?: string | null } | null) {
  if (!llm?.configured) return '未配置';
  return `${llm.model || '已配置'} · ${llm.url_host || '兼容接口'}`;
}

function systemLabel(task?: TaskRun | null) {
  if (!task || !['queued', 'running'].includes(task.status)) return '系统待命';
  if (task.kind === 'update') return task.status === 'queued' ? '等待同步' : '正在同步';
  if (task.kind === 'analyze') return task.status === 'queued' ? '等待分析' : '正在分析';
  if (task.kind === 'backtest') return task.status === 'queued' ? '等待回测' : '正在回测';
  return task.status === 'queued' ? '等待任务' : '正在运行';
}

function kindLabel(kind?: string | null) {
  if (kind === 'update') return '同步今日数据';
  if (kind === 'analyze') return '运行策略';
  if (kind === 'backtest') return '回测';
  if (kind === 'intraday') return '盘中采样';
  if (kind === 'brief') return '市场简报';
  return kind || '任务';
}

function taskStatusLabel(status?: string | null) {
  if (status === 'queued') return '已排队';
  if (status === 'running') return '运行中';
  return status || '待更新';
}
