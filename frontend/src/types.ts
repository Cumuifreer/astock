export type TaskStatus = 'running' | 'completed_full' | 'completed_partial' | 'failed' | 'skipped';

export interface TaskRun {
  id: string;
  kind: 'update' | 'analyze';
  status: TaskStatus;
  stage: string | null;
  source: string | null;
  current_stock: string | null;
  total: number;
  processed: number;
  success: number;
  failed: number;
  skipped: number;
  warning: string | null;
  summary: Record<string, unknown>;
  started_at: string;
  updated_at: string;
  finished_at: string | null;
  error_message: string | null;
}

export interface Capability {
  capability: string;
  actual_sources: string[];
  fallback_sources: string[];
  coverage_count: number;
  missing_count: number;
  latest_update: string | null;
  last_failure_reason: string | null;
  uses_cache: boolean;
  can_backfill: boolean;
  participates_in_analysis: boolean;
}

export interface StrategyPreset {
  id: string;
  name: string;
  config: StrategyConfig;
  is_system: boolean;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export interface StrategyConfig {
  min_price: number;
  min_amount: number;
  min_float_market_value: number | null;
  max_float_market_value: number | null;
  ma_short_window: number;
  ma_long_window: number;
  trend_filter: string;
  signal_mode: string;
  breakout_lookback: number;
  pullback_tolerance: number;
  platform_lookback_days: number;
  platform_max_range: number;
  platform_min_bullish_ratio: number;
  platform_bull_volume_advantage: number;
  platform_breakout_volume_ratio: number;
  platform_breakout_pct_chg_min: number;
  platform_body_strength_min: number;
  platform_ma_trend_enabled: boolean;
  platform_ma_rising_required: boolean;
  macd_filter_enabled: boolean;
  macd_position: string;
  max_amplitude: number;
  rps_window: number;
  min_rps20: number | null;
  min_rps60: number | null;
  min_rps120: number | null;
  min_turnover: number | null;
  max_turnover: number | null;
  missing_turnover_policy: string;
  min_pct_chg: number | null;
  max_pct_chg: number | null;
  volume_ratio_min: number | null;
  max_ma_distance: number | null;
  candidate_limit: number;
  sort_by: string;
  missing_float_market_value_policy: string;
  include_bj: boolean;
  exclude_star_board: boolean;
}

export interface Overview {
  stock_count: number;
  history_rows: number;
  snapshot_rows: number;
  latest_history_date: string | null;
  latest_snapshot_date: string | null;
  turnover_coverage: { count: number; total: number; percent: number };
  latest_analysis: AnalysisRun | null;
  latest_update: TaskRun | null;
  warnings: Array<Record<string, unknown>>;
}

export interface FunnelStep {
  step_name: string;
  before_count: number;
  after_count: number;
  removed_count: number;
  note: string | null;
}

export interface AnalysisRun {
  id: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  summary: Record<string, unknown>;
  config: StrategyConfig;
  funnel?: FunnelStep[];
  error_message: string | null;
}

export interface Candidate {
  rank: number;
  code: string;
  name: string;
  latest_price: number | null;
  pct_chg: number | null;
  amount: number | null;
  volume: number | null;
  turnover_rate: number | null;
  amplitude: number | null;
  rps20: number | null;
  rps60: number | null;
  rps120: number | null;
  ma_short: number | null;
  ma_long: number | null;
  float_market_value: number | null;
  signal_type: string;
  signal_score: number | null;
  data_sources: Record<string, string | null>;
  reasons: string[];
  chart_url: string;
}

export interface Bootstrap {
  overview: Overview;
  capabilities: Capability[];
  strategies: StrategyPreset[];
  default_strategy: StrategyConfig;
  update_status: TaskRun | null;
  analyze_status: TaskRun | null;
  latest_analysis: AnalysisRun | null;
  candidates: {
    run_id: string | null;
    rows: Candidate[];
    funnel: FunnelStep[];
    zero_reason: string | null;
  };
}
