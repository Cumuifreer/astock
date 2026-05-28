import type {
  AnalysisReportsResponse,
  AnalysisReportDetail,
  Bootstrap,
  IndicatorLibrary,
  StrategyConfig,
  StrategyPreset,
  StrategyVersion,
} from '../types';
import { del, post, request } from './client';

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

export function getAnalysisReport(id: string): Promise<AnalysisReportDetail> {
  return request<AnalysisReportDetail>(`/api/analysis/reports/${encodeURIComponent(id)}?limit=300`);
}

export function saveStrategy(payload: Record<string, unknown>): Promise<{ preset: StrategyPreset }> {
  return post<{ preset: StrategyPreset }>('/api/strategies', payload);
}

export function duplicateStrategy(id: string): Promise<{ preset: StrategyPreset }> {
  return post<{ preset: StrategyPreset }>(`/api/strategies/${encodeURIComponent(id)}/duplicate`, {});
}

export function deleteStrategy(id: string): Promise<{ ok: boolean }> {
  return del<{ ok: boolean }>(`/api/strategies/${encodeURIComponent(id)}`);
}

export function getStrategyVersions(id: string): Promise<{ rows: StrategyVersion[] }> {
  return request<{ rows: StrategyVersion[] }>(`/api/strategies/${encodeURIComponent(id)}/versions`);
}
