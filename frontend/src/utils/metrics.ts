import type { Capability } from '../types';
import { toNumber } from './format';

export function taskProgress(processed?: number, total?: number): number | null {
  if (!total || total <= 0) return null;
  return Math.max(0, Math.min(100, ((processed || 0) / total) * 100));
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
