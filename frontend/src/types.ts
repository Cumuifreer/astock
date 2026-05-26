export type TaskStatus = 'queued' | 'running' | 'completed_full' | 'completed_partial' | 'failed' | 'skipped';

export interface TaskRun {
  id: string;
  kind: 'update' | 'analyze' | 'backtest' | 'intraday' | 'brief';
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
  latest_version_id: string | null;
  latest_version_number: number | null;
  latest_version_summary: string | null;
  created_at: string;
  updated_at: string;
}

export interface StrategyVersion {
  id: string;
  preset_id: string;
  strategy_name: string;
  version_number: number;
  config_hash: string;
  summary: string;
  created_at: string;
  config: StrategyConfig;
}

export interface StrategyConfig {
  min_price: number;
  min_amount: number;
  min_float_market_value: number | null;
  max_float_market_value: number | null;
  ma_short_window: number;
  ma_long_window: number;
  trend_filter: string;
  analysis_mode: string;
  signal_mode: string;
  breakout_pullback_direction: string;
  breakout_lookback: number;
  pullback_tolerance: number;
  platform_lookback_days: number;
  platform_max_range: number;
  platform_max_range_mode: string;
  platform_range_basis: string;
  platform_breakout_require_close_above: boolean;
  platform_breakout_clearance_mode: string;
  platform_breakout_clearance: number;
  platform_breakout_max_clearance: number;
  platform_breakout_max_clearance_mode: string;
  platform_breakout_first_mode: string;
  platform_min_bullish_ratio: number;
  platform_bullish_ratio_mode: string;
  platform_bullish_ratio_score: number;
  platform_bull_volume_advantage: number;
  platform_bull_volume_advantage_mode: string;
  platform_bull_volume_advantage_score: number;
  platform_breakout_volume_ratio: number;
  platform_breakout_volume_ratio_mode: string;
  platform_breakout_pct_chg_min: number;
  platform_breakout_pct_chg_mode: string;
  platform_breakout_bullish_mode: string;
  platform_body_strength_min: number;
  platform_body_strength_mode: string;
  platform_ma_trend_enabled: boolean;
  platform_ma_bullish_mode: string;
  platform_ma_rising_required: boolean;
  platform_ma_rising_mode: string;
  platform_macd_filter_mode: string;
  platform_setup_lookback_days: number;
  platform_setup_max_range: number;
  platform_setup_max_distance_to_high: number;
  platform_setup_max_recent_gain_5d: number;
  platform_setup_volume_contraction_max: number;
  platform_setup_bull_volume_advantage: number;
  platform_setup_ma_convergence_max: number;
  platform_setup_require_ma_turning: boolean;
  platform_setup_macd_mode: string;
  trend_ema_fast_window: number;
  trend_ema_mid_window: number;
  trend_ema_long_window: number;
  trend_macd_fast: number;
  trend_macd_slow: number;
  trend_macd_signal: number;
  trend_stoch_window: number;
  trend_stoch_k_smooth: number;
  trend_stoch_d_smooth: number;
  trend_entry_signal: string;
  trend_require_price_above_ema_long: boolean;
  trend_require_ema_long_rising: boolean;
  trend_require_ema_fast_above_mid: boolean;
  trend_macd_mode: string;
  trend_stoch_mode: string;
  trend_max_ema_mid_distance: number;
  trend_max_recent_gain_10d: number;
  trend_stoch_overheat: number;
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
  latest_brief: DailyBrief | null;
  warnings: Array<Record<string, unknown>>;
}

export interface BriefItem {
  title: string;
  url: string;
  source: string;
  summary: string;
  importance: number;
}

export interface BriefArticle {
  title: string;
  url: string;
  source: string;
  category: string;
  summary: string;
  published_at: string;
}

export interface DailyBrief {
  id: string;
  brief_date: string;
  status: string;
  hero_headline: string;
  daily_overview: string;
  tech_briefs: BriefItem[];
  finance_briefs: BriefItem[];
  politics_briefs: BriefItem[];
  editor_note: string;
  keywords: string[];
  article_count: number;
  source_count: number;
  llm_model: string | null;
  generated_at: string | null;
  error_message: string | null;
  article_flow: {
    tech: BriefArticle[];
    finance: BriefArticle[];
    politics: BriefArticle[];
  };
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

export interface AnalysisReportSummary extends AnalysisRun {}

export interface AnalysisReportGroup {
  signal_mode: string;
  reports: AnalysisReportSummary[];
}

export interface CandidateBundle {
  run_id: string | null;
  rows: Candidate[];
  funnel: FunnelStep[];
  zero_reason: string | null;
}

export interface AnalysisReportsResponse {
  groups: AnalysisReportGroup[];
}

export interface AnalysisReportDetail {
  analysis: AnalysisRun;
  candidates: CandidateBundle;
}

export interface BacktestRun {
  id: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  summary: Record<string, unknown>;
  config: StrategyConfig;
  error_message: string | null;
}

export interface BacktestSignal {
  run_id: string;
  as_of_date: string;
  rank: number;
  code: string;
  name: string;
  latest_price: number | null;
  signal_type: string;
  signal_score: number | null;
  reasons: string[];
  metrics: Record<string, unknown>;
  entry_date: string | null;
  entry_price: number | null;
  return_5d: number | null;
  return_10d: number | null;
  return_20d: number | null;
  max_return_10d: number | null;
  max_drawdown_10d: number | null;
  hit_5pct_10d: boolean | null;
  hit_8pct_10d: boolean | null;
  hit_stop_5pct_10d: boolean | null;
}

export interface BacktestResult {
  run: BacktestRun | null;
  signals: BacktestSignal[];
}

export interface BacktestRunsResponse {
  rows: BacktestRun[];
}

export interface IntradayRadarConfig {
  enabled: boolean;
  platform_lookback_days: number;
  platform_max_range: number;
  near_upper_distance: number;
  breakout_min_clearance: number;
  breakout_max_clearance: number;
  min_pct_chg: number;
  max_pct_chg: number;
  min_amount: number;
  min_intraday_amount_ratio: number;
  platform_min_bullish_ratio: number;
  platform_bull_amount_advantage: number;
  first_breakout_lookback_days: number;
  first_breakout_max_clearance: number;
  near_upper_recent_days: number;
  near_upper_recent_distance: number;
  max_recent_gain_5d: number;
  candidate_limit: number;
  require_ma_bullish: boolean;
  require_macd_strong: boolean;
  include_bj: boolean;
  exclude_star_board: boolean;
}

export interface IntradayRadarCandidate {
  sample_at: string;
  trade_date: string;
  rank: number;
  radar_mode: 'strict' | 'score';
  code: string;
  name: string;
  status: string;
  radar_score: number | null;
  latest_price: number | null;
  pct_chg: number | null;
  amount: number | null;
  volume: number | null;
  distance_to_upper: number | null;
  breakout_clearance: number | null;
  amount_delta: number | null;
  volume_delta: number | null;
  amount_ratio: number | null;
  price_change: number | null;
  source: string | null;
  reasons: string[];
  metrics: Record<string, unknown>;
  chart_url: string;
}

export interface IntradayRadarResult {
  config: IntradayRadarConfig;
  sample_at: string | null;
  sample_count: number;
  summary: Record<string, unknown>;
  rows: IntradayRadarCandidate[];
  strict_rows: IntradayRadarCandidate[];
  score_rows: IntradayRadarCandidate[];
}

export interface IntradayTimelineRow {
  sample_at: string;
  trade_date: string;
  latest_price: number | null;
  pct_chg: number | null;
  amount: number | null;
  volume: number | null;
  strict_status: string | null;
  strict_score: number | null;
  score_status: string | null;
  score_score: number | null;
  distance_to_upper: number | null;
  breakout_clearance: number | null;
  amount_ratio: number | null;
  amount_delta: number | null;
  platform_upper: number | null;
  platform_range: number | null;
  reasons: string[];
}

export interface IntradayTimeline {
  code: string;
  name: string;
  trade_date: string | null;
  rows: IntradayTimelineRow[];
}

export interface WatchlistItem {
  batch_id: string;
  code: string;
  name: string;
  entry_date: string;
  entry_price: number | null;
  source_type: string;
  source_label: string;
  source_ref: string | null;
  signal_score: number | null;
  signal_type: string | null;
  chart_url: string;
  note: string;
  review_status: string;
  reasons: string[];
  metrics: Record<string, unknown>;
  days: number;
  latest_date: string | null;
  latest_close: number | null;
  return_latest: number | null;
  return_1d: number | null;
  return_3d: number | null;
  return_5d: number | null;
  return_10d: number | null;
  max_return: number | null;
  max_drawdown: number | null;
}

export interface WatchlistBatch {
  id: string;
  batch_date: string;
  source_type: string;
  source_label: string;
  source_ref: string | null;
  source_summary: string | null;
  note: string;
  review_status: string;
  name: string;
  status: string;
  item_count: number;
  avg_return_latest: number | null;
  avg_return_1d: number | null;
  avg_return_3d: number | null;
  avg_return_5d: number | null;
  avg_return_10d: number | null;
  positive_count: number;
  positive_rate: number | null;
  hit_5pct_count: number;
  hit_8pct_count: number;
  hit_5pct_rate: number | null;
  hit_8pct_rate: number | null;
  worst_drawdown: number | null;
  best_item: WatchlistSummaryItem | null;
  worst_item: WatchlistSummaryItem | null;
  created_at: string;
  updated_at: string;
  items: WatchlistItem[];
}

export interface WatchlistSummaryItem {
  code: string;
  name: string;
  return_latest: number | null;
  return_5d: number | null;
  max_return: number | null;
  max_drawdown: number | null;
}

export interface WatchlistResult {
  summary: {
    batch_count: number;
    item_count: number;
    avg_return_latest: number | null;
    avg_return_1d: number | null;
    avg_return_3d: number | null;
    avg_return_5d: number | null;
    avg_return_10d: number | null;
    positive_count: number;
    positive_rate: number | null;
    hit_5pct_count: number;
    hit_8pct_count: number;
    hit_5pct_rate: number | null;
    hit_8pct_rate: number | null;
    worst_drawdown: number | null;
    best_item: WatchlistSummaryItem | null;
    worst_item: WatchlistSummaryItem | null;
  };
  batches: WatchlistBatch[];
}

export interface RuntimeSlot {
  time: string;
  sample_at: string;
  status: string;
  task_id: string | null;
  task_status: string | null;
  stage: string | null;
  error_message: string | null;
  sample_count: number;
  strict_count: number;
  score_count: number;
  finished_at: string | null;
}

export interface RuntimeHealth {
  data: {
    latest_history_date: string | null;
    latest_snapshot_date: string | null;
    latest_intraday_sample: string | null;
    latest_brief_date: string | null;
    stock_count: number;
  };
  tasks: {
    queued: number;
    running: number;
    latest_update: TaskRun | null;
    latest_analyze: TaskRun | null;
    latest_intraday: TaskRun | null;
    latest_brief: TaskRun | null;
  };
  scheduler: {
    enabled: boolean;
    timezone: string;
    now: string;
    is_weekend: boolean;
    poll_seconds: number;
    catchup_minutes: number;
    next_slot: RuntimeSlot | null;
    slot_count: number;
    completed_count: number;
    remaining_count: number;
    latest_slot: RuntimeSlot | null;
    slots: RuntimeSlot[];
  };
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
  metrics: Record<string, unknown>;
  chart_url: string;
}

export interface Bootstrap {
  overview: Overview;
  capabilities: Capability[];
  strategies: StrategyPreset[];
  default_strategy: StrategyConfig;
  update_status: TaskRun | null;
  analyze_status: TaskRun | null;
  backtest_status: TaskRun | null;
  intraday_status: TaskRun | null;
  brief_status: TaskRun | null;
  latest_analysis: AnalysisRun | null;
  latest_backtest: BacktestRun | null;
  backtest_reports?: BacktestRun[];
  candidates: CandidateBundle;
  backtest: BacktestResult;
  intraday: IntradayRadarResult;
  daily_brief: DailyBrief | null;
  watchlist: WatchlistResult;
  runtime_health: RuntimeHealth;
}
