import { useQuery } from '@tanstack/react-query';
import type { QueryKey } from '@tanstack/react-query';

const activeTaskStatuses = new Set(['queued', 'running']);

type TaskResultQueryOptions<TData> = {
  queryKey: QueryKey;
  queryFn: () => Promise<TData>;
  enabled: boolean;
  initialStatus?: string | null;
  getResultStatus: (data: TData | undefined) => string | null | undefined;
  intervalMs?: number;
};

export function useTaskResultQuery<TData>({
  queryKey,
  queryFn,
  enabled,
  initialStatus,
  getResultStatus,
  intervalMs = 2600,
}: TaskResultQueryOptions<TData>) {
  return useQuery<TData>({
    queryKey,
    queryFn,
    enabled,
    refetchInterval: (query) => {
      const data = query.state.data as TData | undefined;
      const resultStatus = getResultStatus(data);
      if (activeTaskStatuses.has(String(initialStatus || ''))) return intervalMs;
      if (activeTaskStatuses.has(String(resultStatus || ''))) return intervalMs;
      if (!data) return intervalMs;
      return false;
    },
  });
}
