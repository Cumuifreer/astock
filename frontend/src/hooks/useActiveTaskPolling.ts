import { useMemo } from 'react';
import { queryKeys } from '../api/queryKeys';
import type { Bootstrap, TaskRun } from '../types';
import { usePolling } from './usePolling';

type TaskStatusSnapshot = Pick<
  Bootstrap,
  'update_status' | 'analyze_status' | 'backtest_status' | 'intraday_status' | 'brief_status'
>;

const activeTaskStatuses = new Set(['queued', 'running']);

export function useActiveTaskPolling(data?: TaskStatusSnapshot | null, extraTasks: Array<Pick<TaskRun, 'status'> | null | undefined> = [], intervalMs = 2600) {
  const taskActive = useMemo(() => {
    const tasks: Array<TaskRun | null | undefined> = [
      data?.update_status,
      data?.analyze_status,
      data?.backtest_status,
      data?.intraday_status,
      data?.brief_status,
    ];
    return [...tasks, ...extraTasks].some((task) => activeTaskStatuses.has(String(task?.status || '')));
  }, [data, extraTasks]);

  const keys = useMemo(
    () => [
      queryKeys.bootstrap(),
      queryKeys.runtimeHealth(),
      queryKeys.marketOverview(),
      queryKeys.tasks.all(),
      queryKeys.analysis.reports(),
      queryKeys.backtest.runs(),
      queryKeys.intraday.boards(),
    ],
    [],
  );
  usePolling(taskActive, keys, intervalMs);

  return taskActive;
}
