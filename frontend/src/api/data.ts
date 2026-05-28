import type { Capability, RuntimeHealth, SourceDiagnostics, StockDetail, StockListResponse, TaskRun } from '../types';
import { post, request } from './client';

export type TaskDagNode = {
  id: string;
  label: string;
  capability: string;
  target_date?: string;
  dependencies?: string[];
  freshness_policy?: string;
  coverage_policy?: Record<string, unknown>;
  request_policy?: Record<string, unknown>;
  status?: string;
  reason?: string;
};

export type UpdateCheckpoint = {
  id: string;
  task_id: string;
  job_id: string;
  capability: string;
  target_date?: string;
  batch_key?: string;
  status: string;
  rows_written?: number;
  started_at?: string;
  finished_at?: string | null;
  error_message?: string | null;
  payload?: Record<string, unknown>;
};

export function getCapabilities(): Promise<{ rows?: Capability[] } | Capability[]> {
  return request<{ rows?: Capability[] } | Capability[]>('/api/data/capabilities');
}

export function getDataOverview(): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>('/api/data/overview');
}

export function getStocks(params: Record<string, string | number>): Promise<StockListResponse> {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== '' && value !== undefined && value !== null) search.set(key, String(value));
  });
  return request<StockListResponse>(`/api/data/stocks?${search.toString()}`);
}

export function getStockDetail(code: string): Promise<StockDetail> {
  return request<StockDetail>(`/api/data/stocks/${encodeURIComponent(code)}`);
}

export function getSourceDiagnostics(): Promise<SourceDiagnostics> {
  return request<SourceDiagnostics>('/api/data/source-diagnostics');
}

export function getRuntimeHealth(): Promise<RuntimeHealth> {
  return request<RuntimeHealth>('/api/runtime/health');
}

export function syncToday(): Promise<{ task: TaskRun } | TaskRun | Record<string, unknown>> {
  return post('/api/tasks/sync-today', {});
}

export function startUpdate(payload: Record<string, unknown>): Promise<Record<string, unknown>> {
  return post('/api/tasks/update', payload);
}

export function getTasks(params: { status?: string; limit?: number } = {}): Promise<{ rows?: TaskRun[] } | TaskRun[]> {
  const search = new URLSearchParams();
  if (params.status) search.set('status', params.status);
  if (params.limit) search.set('limit', String(params.limit));
  const path = search.toString() ? `/api/tasks?${search.toString()}` : '/api/tasks';
  return request<{ rows?: TaskRun[] } | TaskRun[]>(path);
}

export function getTaskDag(taskId: string): Promise<{ nodes?: TaskDagNode[] } | TaskDagNode[]> {
  return request<{ nodes?: TaskDagNode[] } | TaskDagNode[]>(`/api/tasks/${encodeURIComponent(taskId)}/dag`);
}

export function getTaskCheckpoints(taskId: string): Promise<{ rows?: UpdateCheckpoint[] } | UpdateCheckpoint[]> {
  return request<{ rows?: UpdateCheckpoint[] } | UpdateCheckpoint[]>(`/api/tasks/${encodeURIComponent(taskId)}/checkpoints`);
}
