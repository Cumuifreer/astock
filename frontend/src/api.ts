import type { AnalysisReportDetail, AnalysisReportsResponse, BacktestResult, Bootstrap, StrategyConfig, StrategyPreset } from './types';

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    let message = response.statusText;
    try {
      const body = await response.json();
      message = body.detail || message;
    } catch {
      // keep status text
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export const api = {
  bootstrap: () => request<Bootstrap>('/api/bootstrap'),
  dataOverview: () => request('/api/data/overview'),
  capabilities: () => request('/api/data/capabilities'),
  probeSources: () => request('/api/data/probe', { method: 'POST', body: JSON.stringify({}) }),
  stocks: (limit: number, offset: number, search: string) =>
    request(`/api/data/stocks?limit=${limit}&offset=${offset}&search=${encodeURIComponent(search)}`),
  startUpdate: (payload: Record<string, unknown>) =>
    request('/api/tasks/update', { method: 'POST', body: JSON.stringify(payload) }),
  startAnalyze: (config: StrategyConfig) =>
    request('/api/tasks/analyze', { method: 'POST', body: JSON.stringify({ config }) }),
  startBacktest: (payload: Record<string, unknown>) =>
    request('/api/tasks/backtest', { method: 'POST', body: JSON.stringify(payload) }),
  analysisReports: () => request<AnalysisReportsResponse>('/api/analysis/reports'),
  analysisReport: (id: string) => request<AnalysisReportDetail>(`/api/analysis/reports/${id}?limit=100`),
  backtestLatest: () => request<BacktestResult>('/api/backtests/latest?limit=500'),
  saveStrategy: (payload: Record<string, unknown>) =>
    request<{ preset: StrategyPreset }>('/api/strategies', { method: 'POST', body: JSON.stringify(payload) }),
  duplicateStrategy: (id: string) =>
    request<{ preset: StrategyPreset }>(`/api/strategies/${id}/duplicate`, { method: 'POST' }),
  deleteStrategy: (id: string) =>
    request(`/api/strategies/${id}`, { method: 'DELETE' }),
  setDefaultStrategy: (id: string) =>
    request(`/api/strategies/${id}/default`, { method: 'POST' }),
  resetSystemStrategies: () =>
    request('/api/strategies/system/reset', { method: 'POST' }),
};
