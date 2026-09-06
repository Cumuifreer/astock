import { useEffect, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import type { TaskRun } from '../types';

export function useTaskTerminalInvalidation(rows: TaskRun[], ready = true) {
  const client = useQueryClient();
  const seen = useRef<Set<string> | null>(null);
  useEffect(() => {
    if (!ready) return;
    if (seen.current === null) { seen.current = new Set(rows.map(row => row.id)); return; }
    for (const task of rows) {
      if (seen.current.has(task.id)) continue;
      seen.current.add(task.id);
      void client.invalidateQueries({ queryKey: ['review-overview'] });
      if (task.kind === 'analyze') {
        void client.invalidateQueries({ queryKey: ['result-reports'] });
      }
      if (task.kind === 'update') {
        void client.invalidateQueries({ queryKey: ['watchlist'] });
        void client.invalidateQueries({ queryKey: ['data-stocks'] });
      }
    }
  }, [client, rows, ready]);
}
