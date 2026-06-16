export type TaskStatus = 'queued' | 'running' | 'completed_full' | 'completed_partial' | 'failed' | 'skipped';

export interface TaskRun {
  id: string;
  kind: 'update' | 'analyze' | 'backtest' | 'intraday' | 'intraday_strategy_tracking' | 'brief' | 'candidate_ai_summary';
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

export interface StockRow {
  code: string;
  name: string;
  exchange: string;
  board: string;
  status_label: string;
  latest_price: number | null;
  pct_chg: number | null;
  amount: number | null;
  turnover_rate: number | null;
  float_market_value: number | null;
  volume_ratio: number | null;
  main_net_amount?: number | null;
  net_mf_amount?: number | null;
  latest_top_net_amount?: number | null;
  concept_count?: number | null;
  winner_rate?: number | null;
  history_days?: number | null;
  latest_history_date?: string | null;
  latest_limit_type?: string | null;
}

export interface StockListResponse {
  rows: StockRow[];
  total: number;
}

export interface StockDetail {
  basic: Record<string, unknown> | null;
  daily_basic?: Record<string, unknown> | null;
  factor?: Record<string, unknown> | null;
  moneyflow?: Record<string, unknown> | null;
  cyq_perf?: Record<string, unknown> | null;
  concepts?: Array<Record<string, unknown>>;
  limit_events?: Array<Record<string, unknown>>;
  top_events?: Array<Record<string, unknown>>;
}

export interface SourceDiagnostics {
  tushare_token_configured: boolean;
  tushare_realtime_enabled: boolean;
  tushare_history_enabled: boolean;
  tushare_enrichment_enabled: boolean;
  tushare_http_url_configured: boolean;
  tushare_http_url: string;
  last_tushare_error: string | null;
  last_snapshot_source: string | null;
  last_history_source: string | null;
  snapshot_source?: SourceContract;
  history_source?: SourceContract;
  realtime_status: string;
  history_status: string;
  enrichment_status: string;
  rows: Array<Record<string, unknown>>;
}

export interface SourceContract {
  expected_source: string;
  actual_source: string;
  status: string;
}

export interface IndicatorCategory {
  id: string;
  label: string;
  description: string;
}

export interface IndicatorDefinition {
  id: string;
  name: string;
  category_id: string;
  kind: 'data' | 'strategy_param';
  status: 'active' | 'available' | 'planned';
  source: string;
  formula: string;
  description: string;
  usage: string[];
  default_missing_policy: string;
  analysis_ready: boolean;
  paired_strategy_ids?: string[];
  strategy_key?: keyof StrategyConfig | string;
  control: IndicatorControl;
  group_id: string;
  group_label: string;
  value_type?: IndicatorValueType;
  unit?: string;
  range_hint?: { min?: number; max?: number };
  direction?: 'higher_better' | 'lower_better' | 'range_better' | 'neutral' | 'event' | string;
  supported_actions?: RuleAction[];
  supported_operators?: RuleOperator[];
  default_operator?: RuleOperator;
  recommended_rules?: IndicatorRecommendation[];
  choice_options?: Array<{ value: number | string | boolean; label: string }>;
  analysis_field?: string | null;
  data_status?: 'executable' | 'display_only' | 'planned' | 'parameter' | string;
  display_scope?: 'candidate' | 'warehouse' | 'planned' | string | null;
  hard_filter_allowed?: boolean;
  min_coverage_for_filter?: number | null;
  freshness_required?: boolean;
  coverage_group?: string | null;
  operator_semantics?: 'numeric' | 'boolean' | 'choice' | 'event_state' | 'days_since' | 'market_context' | string;
}

export type IndicatorValueType =
  | 'number'
  | 'money'
  | 'percent'
  | 'ratio'
  | 'multiple'
  | 'score'
  | 'boolean'
  | 'choice'
  | 'event'
  | string;

export type RuleAction = 'filter' | 'score' | 'risk' | 'display';
export type RuleOperator = 'gte' | 'lte' | 'gt' | 'lt' | 'between' | 'eq' | 'neq' | 'is_true' | 'recent';

export interface IndicatorRecommendation {
  label: string;
  action: RuleAction;
  operator: RuleOperator;
  value?: number | string | boolean;
  value2?: number | string;
  weight?: number;
  window_days?: number;
}

export interface IndicatorControl {
  type: 'readonly' | 'number' | 'money' | 'select' | 'boolean';
  unit?: string;
  allow_blank?: boolean;
  min?: number;
  max?: number;
  step?: number;
  options?: Array<{ value: string; label: string }>;
}

export interface IndicatorRule {
  id: string;
  name: string;
  kind: 'filter' | 'score' | 'risk' | 'interaction';
  indicator_ids: string[];
  expression: string;
  effect: { type: string; value: string | number };
  missing_policy: string;
  editable: boolean;
}

export interface SignalModeTemplate {
  id: string;
  name: string;
  description: string;
  note: string;
  runtime_signal_mode?: string;
  fields: SignalModeField[];
  rule_groups: Array<{
    id: string;
    label: string;
    rules: IndicatorRule[];
  }>;
}

export interface SignalModeField {
  indicator_id: string;
  role: 'filter' | 'score' | 'risk' | 'display' | string;
  group_id: string;
  group_label: string;
}

export interface StrategyRule {
  id: string;
  indicator_id: string;
  action: RuleAction;
  operator: RuleOperator;
  value?: number | string | boolean | null;
  value2?: number | string | null;
  window_days?: number;
  weight?: number | null;
  missing_policy: 'skip' | 'keep' | 'neutral' | 'allow' | string;
  enabled: boolean;
}

export interface StrategyRuleCondition {
  id?: string;
  indicator_id: string;
  operator: RuleOperator;
  value?: number | string | boolean | null;
  value2?: number | string | null;
  window_days?: number;
  missing_policy: 'skip' | 'keep' | 'neutral' | 'allow' | string;
}

export interface StrategyInteraction {
  id: string;
  name: string;
  conditions: StrategyRuleCondition[];
  multiplier: number;
  enabled: boolean;
}

export interface StrategyResonance {
  id: string;
  name: string;
  rule_ids: string[];
  bonus: number;
  enabled: boolean;
  source?: 'rule_ids' | 'legacy_unmatched' | string;
  migration_warning?: string;
  legacy_conditions?: StrategyRuleCondition[];
}

export interface IndicatorLibrary {
  categories: IndicatorCategory[];
  indicators: IndicatorDefinition[];
  signal_modes: SignalModeTemplate[];
  summary: {
    category_count: number;
    indicator_count: number;
    active_count: number;
    available_count: number;
    planned_count: number;
    strategy_param_count: number;
    signal_mode_count: number;
    interaction_rule_count: number;
  };
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

export interface StrategyMigrationInfo {
  from_version: number;
  migrated_at: string;
  preserved_fields: string[];
  dropped_fields: string[];
  warnings: string[];
}

export interface StrategyConfig {
  strategy_name?: string;
  name?: string;
  preset_name?: string;
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
  platform_breakout_clearance: number | null;
  platform_breakout_max_clearance: number | null;
  platform_breakout_max_clearance_mode: string;
  platform_breakout_first_mode: string;
  platform_min_bullish_ratio: number;
  platform_bullish_ratio_mode: string;
  platform_bullish_ratio_score: number;
  platform_bull_volume_advantage: number;
  platform_bull_volume_advantage_mode: string;
  platform_bull_volume_advantage_score: number;
  platform_breakout_volume_ratio: number | null;
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
  platform_setup_max_range: number | null;
  platform_setup_max_distance_to_high: number | null;
  platform_setup_max_recent_gain_5d: number | null;
  platform_setup_volume_contraction_max: number | null;
  platform_setup_bull_volume_advantage: number | null;
  platform_setup_ma_convergence_max: number | null;
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
  trend_max_ema_mid_distance: number | null;
  trend_max_recent_gain_10d: number | null;
  trend_stoch_overheat: number | null;
  macd_filter_enabled: boolean;
  macd_position: string;
  max_amplitude: number | null;
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
  min_topic_count: number | null;
  min_topic_heat: number | null;
  min_theme_limit_count: number | null;
  candidate_limit: number;
  sort_by: string;
  missing_float_market_value_policy: string;
  include_bj: boolean;
  exclude_star_board: boolean;
  analysis_engines?: string[];
  strategy_rules: StrategyRule[];
  strategy_interactions?: StrategyInteraction[];
  strategy_resonances?: StrategyResonance[];
  resonance_bonus_cap?: number;
  signal_profile?: SignalModeTemplate | null;
  migration?: StrategyMigrationInfo | null;
}

export interface Overview {
  stock_count: number;
  active_stock_count?: number;
  inactive_stock_count?: number;
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
  amount_ratio_status?: string | null;
  amount_delta: number | null;
  amount_delta_status?: string | null;
  volume_delta?: number | null;
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
    mode?: string;
    enabled_boards?: {
      anomaly?: boolean;
      pullback?: boolean;
      risk?: boolean;
    };
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
  daily_update_scheduler?: {
    enabled: boolean;
    timezone: string;
    now: string;
    is_weekend: boolean;
    poll_seconds: number;
    next_slot: RuntimeDailyUpdateSlot | null;
    slot_count: number;
    completed_count: number;
    remaining_count: number;
    latest_slot: RuntimeDailyUpdateSlot | null;
    slots: RuntimeDailyUpdateSlot[];
  };
  llm?: {
    configured: boolean;
    model: string;
    url_host: string;
  };
}

export interface RuntimeDailyUpdateSlot {
  time: string;
  scheduled_at: string;
  status: string;
  task_id: string | null;
  task_status: string | null;
  stage: string | null;
  error_message: string | null;
  finished_at: string | null;
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
  indicator_library: IndicatorLibrary;
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
