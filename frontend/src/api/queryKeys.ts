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
  },
};
