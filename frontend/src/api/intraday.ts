import type { IntradayTimeline } from '../types';
import { post, put, request } from './client';

export type IntradayCandidate = {
  rank?: number;
  code: string;
  name?: string;
  latest_price?: number | null;
  pct_chg?: number | null;
  amount?: number | null;
  amount_speed?: number | null;
  intraday_amount_speed?: number | null;
  amount_delta?: number | null;
  intraday_drawdown?: number | null;
  open_strength?: number | null;
  theme?: string | null;
  theme_sync_score?: number | null;
  strong_theme_name?: string | null;
  strong_theme_heat?: number | null;
  score?: number | null;
  signal_tags?: string[];
  risk_tags?: string[];
  reasons?: string[];
  chart_url?: string | null;
  metrics?: Record<string, unknown>;
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

export type IntradayStrategyTrackingRow = IntradayCandidate & {
  signal_score?: number | null;
  signal_type?: string | null;
  tracking_status?: string | null;
  turnover_rate?: number | null;
  amplitude?: number | null;
  rps20?: number | null;
  rps60?: number | null;
  rps120?: number | null;
  ma_short?: number | null;
  ma_long?: number | null;
  float_market_value?: number | null;
};

export type IntradayStrategyTracking = {
  config?: {
    strategy_preset_id?: string | null;
    strategy_status?: string | null;
    persisted?: boolean;
    updated_at?: string | null;
  };
  strategy?: {
    id?: string;
    name?: string;
    is_default?: boolean;
    is_system?: boolean;
    latest_version_number?: number | null;
    summary?: string | null;
  } | null;
  sample_at?: string | null;
  summary?: {
    candidate_count?: number;
    new_count?: number;
    continued_count?: number;
    dropped_count?: number;
    zero_reason?: string | null;
  };
  rows?: IntradayStrategyTrackingRow[];
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

export function getIntradayStrategyTracking(): Promise<IntradayStrategyTracking> {
  return request<IntradayStrategyTracking>('/api/intraday/strategy-tracking');
}

export function saveIntradayStrategyTrackingConfig(strategyPresetId: string): Promise<{ config: IntradayStrategyTracking['config']; strategy_tracking: IntradayStrategyTracking }> {
  return put<{ config: IntradayStrategyTracking['config']; strategy_tracking: IntradayStrategyTracking }>('/api/intraday/strategy-tracking/config', { strategy_preset_id: strategyPresetId });
}
