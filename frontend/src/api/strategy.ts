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

export type AnalysisTaskJob = {
  task_id: string;
  status: string;
};

export function getBootstrap(): Promise<Bootstrap> {
  return request<Bootstrap>('/api/bootstrap');
}

export function getIndicatorLibrary(): Promise<IndicatorLibrary> {
  return request<IndicatorLibrary>('/api/indicators');
}

export function runStrategy(config: StrategyConfig): Promise<AnalysisTaskJob> {
  const strategyName = config.strategy_name || config.name || config.preset_name;
  return post<AnalysisTaskJob>('/api/tasks/analyze', {
    config,
    strategy_name: strategyName,
    name: strategyName,
    preset_name: strategyName,
  });
}

export function getAnalysisReports(): Promise<AnalysisReportsResponse> {
  return request<AnalysisReportsResponse>('/api/analysis/reports');
}

export function getAnalysisReport(id: string): Promise<AnalysisReportDetail> {
  return request<AnalysisReportDetail>(`/api/analysis/reports/${encodeURIComponent(id)}?limit=300`);
}

export type CandidateAiSummary = {
  enabled?: boolean;
  summary: string;
  opportunities?: string[];
  risks?: string[];
  watch_plan?: string[];
  generated_at?: string | null;
  prompt_version?: string | null;
  fallback_reason?: 'missing_api_key' | 'llm_error' | 'invalid_response' | null;
  error_message?: string | null;
};

export function getCandidateAiSummary(runId: string, code: string, payload: Record<string, unknown>): Promise<CandidateAiSummary> {
  return post<CandidateAiSummary>(`/api/analysis/candidates/${encodeURIComponent(runId)}/${encodeURIComponent(code)}/ai-summary`, payload);
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
