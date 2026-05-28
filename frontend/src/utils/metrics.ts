import type { Capability, TaskRun } from '../types';
import { toNumber } from './format';

const terminalTaskStatuses = new Set(['completed_full', 'completed_partial', 'failed', 'skipped']);
const terminalDagStatuses = new Set(['completed', 'skipped', 'partial', 'failed']);

export function taskProgress(processed?: number, total?: number): number | null {
  if (!total || total <= 0) return null;
  return Math.max(0, Math.min(100, ((processed || 0) / total) * 100));
}

export function isTerminalTaskStatus(status?: string | null): boolean {
  return terminalTaskStatuses.has(String(status || ''));
}

export function taskProgressValue(
  task: Pick<TaskRun, 'processed' | 'total' | 'status'>,
  override?: number | null,
): number | null {
  if (typeof override === 'number' && Number.isFinite(override)) return Math.max(0, Math.min(100, override));
  const value = taskProgress(task.processed, task.total);
  if (value !== null) return value;
  return isTerminalTaskStatus(task.status) ? 100 : null;
}

export function dagProgress(nodes: Array<{ status?: string | null }> | null | undefined): number | null {
  if (!nodes?.length) return null;
  const processed = nodes.filter((node) => terminalDagStatuses.has(String(node.status || ''))).length;
  return taskProgress(processed, nodes.length);
}

export function flowProgress(nodes: Array<{ status?: string | null }> | null | undefined): number | null {
  return dagProgress(nodes);
}

export function capabilityHealth(capability: Capability): 'normal' | 'stale' | 'low' | 'missing' | 'partial' {
  const coverage = toNumber(capability.coverage_count) || 0;
  const missing = toNumber(capability.missing_count) || 0;
  if (capability.last_failure_reason) return 'partial';
  if (coverage <= 0) return 'missing';
  if (missing > coverage * 0.2) return 'low';
  if (!capability.latest_update) return 'stale';
  return 'normal';
}

export function normalizeRows<T>(value: { rows?: T[]; nodes?: T[] } | T[] | null | undefined): T[] {
  if (Array.isArray(value)) return value;
  if (Array.isArray(value?.rows)) return value.rows;
  if (Array.isArray(value?.nodes)) return value.nodes;
  return [];
}

export function scoreTone(score?: number | null): 'good' | 'watch' | 'risk' | 'neutral' {
  if (score === null || score === undefined) return 'neutral';
  if (score >= 70) return 'good';
  if (score >= 45) return 'watch';
  return 'risk';
}
