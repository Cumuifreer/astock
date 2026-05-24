import type { AnalysisReportDetail, AnalysisReportsResponse, BacktestResult, BacktestRunsResponse, Bootstrap, IntradayRadarConfig, IntradayRadarResult, IntradayTimeline, RuntimeHealth, StrategyConfig, StrategyPreset, StrategyVersion, WatchlistResult } from './types';

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
  stocks: (limit: number, offset: number, search: string, filters: Record<string, string> = {}) => {
    const params = new URLSearchParams({ limit: String(limit), offset: String(offset), search });
    Object.entries(filters).forEach(([key, value]) => {
      if (value) params.set(key, value);
    });
    return request(`/api/data/stocks?${params.toString()}`);
  },
  startUpdate: (payload: Record<string, unknown>) =>
    request('/api/tasks/update', { method: 'POST', body: JSON.stringify(payload) }),
  startAnalyze: (config: StrategyConfig) =>
    request('/api/tasks/analyze', { method: 'POST', body: JSON.stringify({ config }) }),
  startBacktest: (payload: Record<string, unknown>) =>
    request('/api/tasks/backtest', { method: 'POST', body: JSON.stringify(payload) }),
  startIntradaySnapshot: (payload: Record<string, unknown> = {}) =>
    request('/api/tasks/intraday-snapshot', { method: 'POST', body: JSON.stringify(payload) }),
  intradayLatest: () => request<IntradayRadarResult>('/api/intraday?limit=300'),
  intradayTimeline: (code: string, tradeDate?: string | null) =>
    request<IntradayTimeline>(`/api/intraday/timeline/${encodeURIComponent(code)}${tradeDate ? `?trade_date=${encodeURIComponent(tradeDate)}` : ''}`),
  runtimeHealth: () => request<RuntimeHealth>('/api/runtime/health'),
  watchlist: () => request<WatchlistResult>('/api/watchlist'),
  addToWatchlist: (payload: Record<string, unknown>) =>
    request('/api/watchlist/items', { method: 'POST', body: JSON.stringify(payload) }),
  deleteWatchlistBatch: (id: string) =>
    request(`/api/watchlist/batches/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  updateWatchlistBatch: (id: string, payload: Record<string, unknown>) =>
    request(`/api/watchlist/batches/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  deleteWatchlistItem: (batchId: string, code: string) =>
    request(`/api/watchlist/batches/${encodeURIComponent(batchId)}/items/${encodeURIComponent(code)}`, { method: 'DELETE' }),
  updateWatchlistItem: (batchId: string, code: string, payload: Record<string, unknown>) =>
    request(`/api/watchlist/batches/${encodeURIComponent(batchId)}/items/${encodeURIComponent(code)}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
  saveIntradayConfig: (config: IntradayRadarConfig) =>
    request<{ config: IntradayRadarConfig }>('/api/intraday/config', { method: 'PUT', body: JSON.stringify({ config }) }),
  analysisReports: () => request<AnalysisReportsResponse>('/api/analysis/reports'),
  analysisReport: (id: string) => request<AnalysisReportDetail>(`/api/analysis/reports/${id}?limit=100`),
  backtestRuns: () => request<BacktestRunsResponse>('/api/backtests'),
  backtestLatest: () => request<BacktestResult>('/api/backtests/latest?limit=500'),
  backtestResult: (id: string) => request<BacktestResult>(`/api/backtests/${id}?limit=500`),
  saveStrategy: (payload: Record<string, unknown>) =>
    request<{ preset: StrategyPreset }>('/api/strategies', { method: 'POST', body: JSON.stringify(payload) }),
  strategyVersions: (id: string) =>
    request<{ rows: StrategyVersion[] }>(`/api/strategies/${encodeURIComponent(id)}/versions`),
  duplicateStrategy: (id: string) =>
    request<{ preset: StrategyPreset }>(`/api/strategies/${id}/duplicate`, { method: 'POST' }),
  deleteStrategy: (id: string) =>
    request(`/api/strategies/${id}`, { method: 'DELETE' }),
  setDefaultStrategy: (id: string) =>
    request(`/api/strategies/${id}/default`, { method: 'POST' }),
  resetSystemStrategies: () =>
    request('/api/strategies/system/reset', { method: 'POST' }),
};
