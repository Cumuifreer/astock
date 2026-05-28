import type {
  AnalysisReportsResponse,
  Bootstrap,
  IndicatorLibrary,
  StrategyConfig,
  StrategyPreset,
  StrategyVersion,
} from '../types';
import { post, request } from './client';

export function getBootstrap(): Promise<Bootstrap> {
  return request<Bootstrap>('/api/bootstrap');
}

export function getIndicatorLibrary(): Promise<IndicatorLibrary> {
  return request<IndicatorLibrary>('/api/indicators');
}

export function runStrategy(config: StrategyConfig): Promise<unknown> {
  return post('/api/tasks/analyze', { config });
}

export function getAnalysisReports(): Promise<AnalysisReportsResponse> {
  return request<AnalysisReportsResponse>('/api/analysis/reports');
}

export function getAnalysisReport(id: string): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>(`/api/analysis/reports/${encodeURIComponent(id)}?limit=300`);
}

export function saveStrategy(payload: Record<string, unknown>): Promise<{ preset: StrategyPreset }> {
  return post<{ preset: StrategyPreset }>('/api/strategies', payload);
}

export function getStrategyVersions(id: string): Promise<{ rows: StrategyVersion[] }> {
  return request<{ rows: StrategyVersion[] }>(`/api/strategies/${encodeURIComponent(id)}/versions`);
}
