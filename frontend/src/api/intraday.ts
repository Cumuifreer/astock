import type { IntradayTimeline } from '../types';
import { post, request } from './client';

export type IntradayCandidate = {
  code: string;
  name?: string;
  pct_chg?: number | null;
  amount_speed?: number | null;
  intraday_amount_speed?: number | null;
  amount_delta?: number | null;
  theme?: string | null;
  theme_sync_score?: number | null;
  score?: number | null;
  signal_tags?: string[];
  risk_tags?: string[];
  reasons?: string[];
};

export type ThemePulse = {
  name?: string;
  sector_name?: string;
  heat_score?: number | null;
  pct_chg?: number | null;
  net_amount?: number | null;
};

export type IntradayBoards = {
  sample_at?: string | null;
  sample_count?: number;
  anomaly?: IntradayCandidate[];
  pullback?: IntradayCandidate[];
  risk?: IntradayCandidate[];
  theme_pulse?: ThemePulse[];
};

export function getIntradayBoards(): Promise<IntradayBoards> {
  return request<IntradayBoards>('/api/intraday/boards');
}

export function startIntradaySnapshot(payload: Record<string, unknown> = {}): Promise<Record<string, unknown>> {
  return post('/api/tasks/intraday-snapshot', payload);
}

export function getIntradayTimeline(code: string, tradeDate?: string | null): Promise<IntradayTimeline> {
  const suffix = tradeDate ? `?trade_date=${encodeURIComponent(tradeDate)}` : '';
  return request<IntradayTimeline>(`/api/intraday/timeline/${encodeURIComponent(code)}${suffix}`);
}
