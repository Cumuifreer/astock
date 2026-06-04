import { useQuery } from '@tanstack/react-query';
import { getTasks } from '../api/data';
import { queryKeys } from '../api/queryKeys';
import type { TaskRun } from '../types';
import { normalizeRows } from '../utils/metrics';

const heavyTaskKinds = new Set(['update', 'analyze', 'backtest', 'intraday', 'intraday_strategy_tracking']);
const activeTaskStatuses = new Set(['queued', 'running']);
const activeRefreshInterval = 2600;
const standbyRefreshInterval = 60_000;

export function useHeavyTaskLock(activeRows?: TaskRun[]) {
  const query = useQuery({
    queryKey: queryKeys.tasks.active(),
    queryFn: () => getTasks({ status: 'queued,running', limit: 50 }),
    enabled: !activeRows,
    refetchInterval: (result) =>
      hasHeavyTaskRows(normalizeRows<TaskRun>(result.state.data as { rows?: TaskRun[] } | TaskRun[] | undefined)) ? activeRefreshInterval : standbyRefreshInterval,
  });
  const rows = activeRows || normalizeRows<TaskRun>(query.data);
  const activeHeavyTasks = rows.filter((task) => heavyTaskKinds.has(String(task.kind || '')) && activeTaskStatuses.has(String(task.status || '')));
  return {
    locked: activeHeavyTasks.length > 0,
    activeTask: activeHeavyTasks[0] || null,
    activeHeavyTasks,
  };
}

function hasHeavyTaskRows(rows: TaskRun[]) {
  return rows.some((task) => heavyTaskKinds.has(String(task.kind || '')) && activeTaskStatuses.has(String(task.status || '')));
}
