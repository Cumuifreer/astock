import { useEffect, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '../api/queryKeys';
import type { TaskRun } from '../types';

const terminalTaskStatuses = new Set(['completed_full', 'completed_partial', 'failed']);

export function useTaskTerminalInvalidation(recentRows: TaskRun[], recentRowsReady = true) {
  const queryClient = useQueryClient();
  const seenTerminalTaskIds = useRef(new Set<string>());
  const primedRecentTaskIds = useRef(false);

  useEffect(() => {
    if (!recentRowsReady) return;
    if (!primedRecentTaskIds.current) {
      for (const task of recentRows) {
        if (task.id && terminalTaskStatuses.has(String(task.status || ''))) {
          seenTerminalTaskIds.current.add(task.id);
        }
      }
      primedRecentTaskIds.current = true;
      return;
    }

    let refreshCommon = false;
    let refreshReports = false;
    let refreshBacktests = false;
    let refreshIntraday = false;
    const analysisRunIds = new Set<string>();
    const backtestRunIds = new Set<string>();
    const candidateSummaryKeys = new Set<string>();

    for (const task of recentRows) {
      if (!terminalTaskStatuses.has(String(task.status || ''))) continue;
      if (!task.id || seenTerminalTaskIds.current.has(task.id)) continue;
      seenTerminalTaskIds.current.add(task.id);
      refreshCommon = true;
      if (task.kind === 'analyze') {
        refreshReports = true;
        const runId = taskRunId(task);
        if (runId) analysisRunIds.add(runId);
      }
      if (task.kind === 'backtest') {
        refreshBacktests = true;
        const runId = taskRunId(task, 'backtest_run_id');
        if (runId) backtestRunIds.add(runId);
      }
      if (task.kind === 'intraday') {
        refreshIntraday = true;
      }
      if (String(task.kind) === 'candidate_ai_summary') {
        const runId = taskRunId(task);
        const code = String(task.summary?.code || '');
        if (runId && code) candidateSummaryKeys.add(`${runId}\n${code}`);
      }
    }

    if (refreshCommon) {
      void queryClient.invalidateQueries({ queryKey: queryKeys.bootstrap() });
      void queryClient.invalidateQueries({ queryKey: queryKeys.tasks.all() });
    }
    if (refreshReports) void queryClient.invalidateQueries({ queryKey: queryKeys.analysis.reports() });
    for (const runId of analysisRunIds) {
      void queryClient.invalidateQueries({ queryKey: queryKeys.analysis.report(runId) });
    }
    if (refreshBacktests) void queryClient.invalidateQueries({ queryKey: queryKeys.backtest.runs() });
    for (const runId of backtestRunIds) {
      void queryClient.invalidateQueries({ queryKey: queryKeys.backtest.signalEvaluation(runId) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.backtest.portfolio(runId) });
    }
    if (refreshIntraday) void queryClient.invalidateQueries({ queryKey: queryKeys.intraday.boards() });
    for (const key of candidateSummaryKeys) {
      const [runId, code] = key.split('\n');
      void queryClient.invalidateQueries({ queryKey: queryKeys.analysis.candidateAiSummary(runId, code) });
    }
  }, [queryClient, recentRows, recentRowsReady]);
}

function taskRunId(task: TaskRun, preferredKey?: string) {
  return String(
    (preferredKey ? task.summary?.[preferredKey] : undefined) ||
      task.summary?.analysis_run_id ||
      task.summary?.backtest_run_id ||
      task.summary?.run_id ||
      task.summary?.runId ||
      '',
  );
}
