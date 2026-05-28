import { useEffect } from 'react';
import type { QueryKey } from '@tanstack/react-query';
import { useQueryClient } from '@tanstack/react-query';

export function usePolling(enabled: boolean, keys: QueryKey[], intervalMs = 2500) {
  const queryClient = useQueryClient();
  useEffect(() => {
    if (!enabled) return undefined;
    const timer = window.setInterval(() => {
      for (const key of keys) {
        void queryClient.invalidateQueries({ queryKey: key });
      }
    }, intervalMs);
    return () => window.clearInterval(timer);
  }, [enabled, intervalMs, keys, queryClient]);
}
