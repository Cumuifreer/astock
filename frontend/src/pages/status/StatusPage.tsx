import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getRuntimeHealth, getTaskFlow, getTaskProgressNodes, getTasks } from '../../api/data';
import { queryKeys } from '../../api/queryKeys';
import { Badge } from '../../design/Badge';
import { Button } from '../../design/Button';
import { DataTable } from '../../design/DataTable';
import { LoadingState } from '../../design/LoadingState';
import { Progress } from '../../design/Progress';
import { useTaskTerminalInvalidation } from '../../hooks/useTaskTerminalInvalidation';
import { dateTimeToMs, formatChinaDateTime, formatDateTime } from '../../utils/date';
import { flowProgress, normalizeRows, taskProgressValue } from '../../utils/metrics';
import type { ColumnDef } from '@tanstack/react-table';
import type { TaskRun } from '../../types';
import type { TaskFlowNode, TaskProgressNode } from '../../api/data';

const activeRefreshInterval = 2500;
const standbyRefreshInterval = 60_000;
const staleHeartbeatMs = 60_000;

export function StatusPage() {
  const [showMaintenance, setShowMaintenance] = useState(false);
  const activeTasks = useQuery({
    queryKey: queryKeys.tasks.active(),
    queryFn: () => getTasks({ status: 'queued,running', limit: 50 }),
    refetchInterval: (query) =>
      hasActiveRows(normalizeRows<TaskRun>(query.state.data as { rows?: TaskRun[] } | TaskRun[] | undefined)) ? activeRefreshInterval : standbyRefreshInterval,
  });
  const activeRows = normalizeRows<TaskRun>(activeTasks.data);
  const taskPollingActive = hasActiveRows(activeRows);
  const recentTasks = useQuery({
    queryKey: queryKeys.tasks.recent(),
    queryFn: () => getTasks({ status: 'completed_full,completed_partial,failed', limit: 50 }),
    refetchInterval: taskPollingActive ? activeRefreshInterval : standbyRefreshInterval,
  });
  const runtimeHealth = useQuery({
    queryKey: queryKeys.runtimeHealth(),
    queryFn: getRuntimeHealth,
    refetchInterval: taskPollingActive ? activeRefreshInterval : standbyRefreshInterval,
  });
  const recentRows = normalizeRows<TaskRun>(recentTasks.data);
  const effectiveActiveRows = activeRows;
  const runningTasks = effectiveActiveRows.filter((task) => task.status === 'running');
  const queuedTasks = effectiveActiveRows.filter((task) => task.status === 'queued');
  const failedTasks = recentRows.filter((task) => task.status === 'failed');
  const activeTask = runningTasks[0] || queuedTasks[0] || null;
  const scheduler = runtimeHealth.data?.scheduler;
  const llm = runtimeHealth.data?.llm;
  const taskFlow = useQuery({
    queryKey: queryKeys.tasks.flow(activeTask?.id),
    queryFn: () => getTaskFlow(activeTask?.id || ''),
    enabled: Boolean(activeTask?.id && activeTask.kind === 'update'),
    refetchInterval: activeTask?.kind === 'update' ? activeRefreshInterval : false,
  });
  const progressNodes = useQuery({
    queryKey: queryKeys.tasks.progressNodes(activeTask?.id),
    queryFn: () => getTaskProgressNodes(activeTask?.id || ''),
    enabled: Boolean(activeTask?.id && activeTask.kind === 'update'),
    refetchInterval: activeTask?.kind === 'update' ? activeRefreshInterval : false,
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
  useTaskTerminalInvalidation(recentRows, recentTasks.isFetched);

  if (activeTasks.isLoading) return <LoadingState label="读取任务状态" />;

  return (
    <div className="page-grid">
      <section className="surface pad">
        <div className="section-heading">
          <div>
            <h2>任务状态</h2>
            <p>查看当前任务、等待队列和定时计划。</p>
          </div>
          <Badge tone={effectiveActiveRows.length ? 'info' : 'neutral'}>{effectiveActiveRows.length ? '有任务' : '系统待命'}</Badge>
        </div>
        <div className="grid-3 status-summary-grid">
          <Metric label="系统状态" value={systemLabel(activeTask)} />
          <Metric label="任务队列" value={`运行 ${runningTasks.length} · 排队 ${queuedTasks.length}`} />
          <Metric label="AI 模型" value={llmLabel(llm)} tone={llm?.configured ? 'neutral' : 'risk'} />
        </div>
        <ScheduleStatusStrip scheduler={scheduler} />
        {effectiveActiveRows.length ? (
          <section className="task-status-list">
            <h3 className="subsection-title">运行中任务</h3>
            {effectiveActiveRows.map((task) => (
              <TaskStatusCard key={task.id} progressValue={progressByTaskId[task.id]} task={task} />
            ))}
          </section>
        ) : null}
        <div className="button-row" style={{ marginTop: 16 }}>
          <Button onClick={() => setShowMaintenance((value) => !value)} variant="secondary">
            {showMaintenance ? '收起维护信息' : '查看维护信息'}
          </Button>
        </div>
      </section>

      {showMaintenance ? (
      <section className="maintenance-details surface pad">
        {failedTasks.length ? (
          <article className="recent-failure-panel">
            <span>最近失败</span>
            <strong>{failedTasks[0]?.error_message || failedTasks[0]?.warning || '失败原因待记录'}</strong>
          </article>
        ) : null}
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

function TaskStatusCard({ task, progressValue }: { task: TaskRun; progressValue?: number | null }) {
  return (
    <article className="task-progress-card">
      <div className="rule-card-header">
        <strong>{kindLabel(task.kind)}</strong>
        <Badge tone={task.status === 'running' ? 'info' : 'watch'}>{taskStatusLabel(task.status)}</Badge>
      </div>
      <Progress label={`${kindLabel(task.kind)}进度`} state={task.status} value={taskProgressValue(task, progressValue)} />
      <p className="card-copy">
        {taskProgressCopy(task)}
      </p>
      <p className="card-copy">
        开始于 {formatDateTime(task.started_at)} · {heartbeatLabel(task)}
      </p>
    </article>
  );
}

function taskProgressCopy(task: TaskRun) {
  const stage = task.stage || '等待开始';
  const total = Number(task.total || 0);
  if (total <= 0) return `当前步骤：${stage} · 进度待返回`;
  return `当前步骤：${stage} · 已完成 ${task.processed || 0} / 共 ${total}`;
}

function heartbeatLabel(task: TaskRun) {
  const updated = dateTimeToMs(task.updated_at);
  const stale = Number.isFinite(updated) && task.status === 'running' && Date.now() - updated > staleHeartbeatMs;
  if (stale) return `可能仍在运行，最近更新于 ${formatDateTime(task.updated_at)}`;
  return `最近更新 ${formatDateTime(task.updated_at)}`;
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

type SchedulerHealth = {
  enabled?: boolean;
  next_slot?: { time?: string | null; sample_at?: string | null } | null;
  remaining_count?: number;
  latest_slot?: { sample_at?: string | null; status?: string | null } | null;
} | null;

function ScheduleStatusStrip({ scheduler }: { scheduler?: SchedulerHealth }) {
  const enabled = Boolean(scheduler?.enabled);
  const next = scheduler?.next_slot?.time || scheduler?.next_slot?.sample_at;
  const latest = scheduler?.latest_slot?.sample_at;
  const remaining = scheduler?.remaining_count ?? 0;
  const latestRawStatus = scheduler?.latest_slot?.status;
  const latestStatus = latestRawStatus ? taskStatusLabel(latestRawStatus) : latest ? '已记录' : '暂无';
  return (
    <article className="schedule-status-strip">
      <strong>定时计划</strong>
      <span>盘中采样：{enabled ? '已开启' : '未开启'}</span>
      <span>下一次：{enabled ? next || '待定' : '未开启'}</span>
      <span>今日剩余：{enabled ? `${remaining} 次` : '-'}</span>
      <span>最近一次：{latest ? `${formatChinaDateTime(latest)} · ${latestStatus}` : '暂无'}</span>
    </article>
  );
}

function llmLabel(llm?: { configured?: boolean; model?: string | null; url_host?: string | null } | null) {
  if (!llm?.configured) return '未配置';
  const marker = `${llm.model || ''} ${llm.url_host || ''}`.toLowerCase();
  if (marker.includes('deepseek')) return 'DeepSeek';
  return '已配置';
}

function systemLabel(task?: TaskRun | null) {
  if (!task || !['queued', 'running'].includes(task.status)) return '系统待命';
  if (task.kind === 'update') return task.status === 'queued' ? '等待同步' : '正在同步';
  if (task.kind === 'analyze') return task.status === 'queued' ? '等待分析' : '正在分析';
  if (task.kind === 'backtest') return task.status === 'queued' ? '等待回测' : '正在回测';
  if (String(task.kind) === 'candidate_ai_summary') return task.status === 'queued' ? '等待解释' : '正在解释';
  return task.status === 'queued' ? '等待任务' : '正在运行';
}

function hasActiveRows(rows: TaskRun[]) {
  return rows.some((task) => ['queued', 'running'].includes(task.status));
}

function kindLabel(kind?: string | null) {
  if (kind === 'update') return '同步今日数据';
  if (kind === 'analyze') return '运行策略';
  if (kind === 'backtest') return '回测';
  if (kind === 'intraday') return '盘中采样';
  if (kind === 'brief') return '市场简报';
  if (kind === 'candidate_ai_summary') return '候选解释';
  return kind || '任务';
}

function taskStatusLabel(status?: string | null) {
  if (status === 'queued') return '已排队';
  if (status === 'running') return '运行中';
  return status || '待更新';
}
