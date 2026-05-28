import type { Capability, RuntimeHealth, TaskRun } from '../types';
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

export function getRuntimeHealth(): Promise<RuntimeHealth> {
  return request<RuntimeHealth>('/api/runtime/health');
}

export function syncToday(): Promise<{ task: TaskRun } | TaskRun | Record<string, unknown>> {
  return post('/api/tasks/sync-today', {});
}

export function startUpdate(payload: Record<string, unknown>): Promise<Record<string, unknown>> {
  return post('/api/tasks/update', payload);
}

export function getTaskDag(taskId: string): Promise<{ nodes?: TaskDagNode[] } | TaskDagNode[]> {
  return request<{ nodes?: TaskDagNode[] } | TaskDagNode[]>(`/api/tasks/${encodeURIComponent(taskId)}/dag`);
}

export function getTaskCheckpoints(taskId: string): Promise<{ rows?: UpdateCheckpoint[] } | UpdateCheckpoint[]> {
  return request<{ rows?: UpdateCheckpoint[] } | UpdateCheckpoint[]>(`/api/tasks/${encodeURIComponent(taskId)}/checkpoints`);
}
