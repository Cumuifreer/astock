export const queryKeys = {
  bootstrap: () => ['bootstrap'] as const,
  runtimeHealth: () => ['runtime-health'] as const,
  marketOverview: () => ['market-overview'] as const,
  tasks: {
    all: () => ['tasks'] as const,
    active: () => ['tasks', 'queued,running'] as const,
    recent: () => ['tasks', 'recent'] as const,
    flow: (taskId?: string) => ['task-flow', taskId] as const,
    progressNodes: (taskId?: string) => ['task-progress-nodes', taskId] as const,
  },
  analysis: {
    reports: () => ['result-reports'] as const,
    report: (runId?: string) => ['result-report', runId] as const,
    candidateAiSummary: (runId?: string, code?: string) => ['candidate-ai-summary', runId, code] as const,
  },
  backtest: {
    runs: () => ['backtest-runs'] as const,
    signalEvaluation: (runId?: string) => ['signal-evaluation', runId] as const,
    portfolio: (runId?: string) => ['portfolio-backtest', runId] as const,
  },
  intraday: {
    boards: () => ['intraday-boards'] as const,
    strategyTracking: () => ['intraday-strategy-tracking'] as const,
    timeline: (code?: string, tradeDate?: string | null) => ['intraday-timeline', code, tradeDate] as const,
  },
};
