import type { BacktestResult, BacktestRunsResponse, StrategyConfig } from '../types';
import { post, request } from './client';

export type BacktestJob = {
  task_id: string;
  run_id: string;
  status: string;
};

export function getBacktestRuns(): Promise<BacktestRunsResponse> {
  return request<BacktestRunsResponse>('/api/backtests');
}

export function getLatestBacktest(): Promise<BacktestResult> {
  return request<BacktestResult>('/api/backtests/latest?limit=500');
}

export function runLegacyBacktest(payload: Record<string, unknown>, config: StrategyConfig): Promise<Record<string, unknown>> {
  return post('/api/tasks/backtest', { ...payload, config });
}

export function runSignalEvaluation(payload: Record<string, unknown>): Promise<BacktestJob> {
  return post<BacktestJob>('/api/backtest/signal-evaluation', payload);
}

export function getSignalEvaluation(runId: string): Promise<BacktestResult> {
  return request<BacktestResult>(`/api/backtest/signal-evaluation/${encodeURIComponent(runId)}`);
}

export function runPortfolioBacktest(payload: Record<string, unknown>): Promise<BacktestJob> {
  return post<BacktestJob>('/api/backtest/portfolio', payload);
}

export function getPortfolioBacktest(runId: string): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>(`/api/backtest/portfolio/${encodeURIComponent(runId)}`);
}
