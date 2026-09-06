import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getTasks, startUpdate } from '../../api/data';
import { queryKeys } from '../../api/queryKeys';
import { useHeavyTaskLock } from '../../hooks/useHeavyTaskLock';
import { Button } from '../../design/Button';
import { useToast } from '../../design/Toast';
import { ReviewDataStatus } from '../results/ReviewDataStatus';
import { TaskQueue } from '../status/TaskQueue';
import { normalizeRows } from '../../utils/metrics';
import type { TaskRun } from '../../types';

export function DataMapPage() {
  const client = useQueryClient();
  const { showToast } = useToast();
  const lock = useHeavyTaskLock();
  const [historyExpanded, setHistoryExpanded] = useState(false);
  const active = useQuery({ queryKey: queryKeys.tasks.active(), queryFn: () => getTasks({ status: 'queued,running', limit: 50 }) });
  const recent = useQuery({ queryKey: queryKeys.tasks.recent(), queryFn: () => getTasks({ status: 'completed_full,completed_partial,failed', limit: 50 }) });
  const update = useMutation({
    mutationFn: (mode: 'daily_light' | 'full') => startUpdate({ mode }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: queryKeys.tasks.all() });
      showToast('日线更新已排队', 'success');
    },
    onError: error => showToast(error.message, 'danger'),
  });
  const activeRows = normalizeRows<TaskRun>(active.data);
  const recentRows = normalizeRows<TaskRun>(recent.data).filter(task => ['update', 'analyze'].includes(task.kind));
  return <div className="page-grid">
    <ReviewDataStatus />
    <section className="surface pad">
      <div className="section-heading">
        <div><h2>更新收盘数据</h2><p>补齐缺失日线，已有完整数据会跳过。首次补齐较慢，进度保存在服务器。</p></div>
        <Button variant="primary" disabled={lock.locked || update.isPending} onClick={() => update.mutate('daily_light')}>更新日线</Button>
      </div>
      <p className="card-copy">数据更新完成后，到“策略选股”运行保存的策略，再回到“收盘复盘”查看报告。</p>
      <details><summary>补齐历史窗口</summary><p className="card-copy">首次切换到新版或长周期指标缺少历史数据时使用。重新获取整个股票池的分析窗口，可能需要较长时间。</p><Button variant="secondary" disabled={lock.locked || update.isPending} onClick={() => update.mutate('full')}>补齐全部历史日线</Button></details>
      {(active.isError || recent.isError) && <p role="alert">任务读取失败，请稍后刷新页面。</p>}
      <TaskQueue tasks={activeRows} title="当前任务" />
    </section>
    <section className="surface pad">
      <div className="section-heading"><h2>最近任务</h2><Button variant="ghost" onClick={() => setHistoryExpanded(!historyExpanded)}>{historyExpanded ? '收起' : '展开更多'}</Button></div>
      <TaskQueue tasks={recentRows.slice(0, historyExpanded ? 50 : 5)} emptyLabel="暂无任务记录" />
    </section>
  </div>;
}
