import type { StrategyConfig, StrategyRule } from '../../types';
import { Badge } from '../../design/Badge';
import { Progress } from '../../design/Progress';

type StrategySummaryProps = {
  name: string;
  config: StrategyConfig;
  rules: StrategyRule[];
};

export function StrategySummary({ name, config, rules }: StrategySummaryProps) {
  const activeRules = rules.filter((rule) => rule.enabled !== false);
  const parameterFilters = activeParameterCount(config);
  const filters = activeRules.filter((rule) => rule.action === 'filter').length + parameterFilters;
  const scores = activeRules.filter((rule) => rule.action === 'score').length;
  const risks = activeRules.filter((rule) => rule.action === 'risk').length;
  const combinations = (config.strategy_resonances || []).filter((item) => item.enabled !== false && (item.rule_ids || []).length >= 2).length;
  const enabledTotal = filters + scores + risks + combinations;
  return (
    <section className="surface pad">
      <div className="section-heading">
        <div>
          <h2>策略摘要</h2>
          <p>{name}</p>
        </div>
        <Badge tone="info">{modeLabel(config.analysis_mode)}</Badge>
      </div>
      <div className="list-stack">
        <SummaryRow label="硬筛" value={filters} />
        <SummaryRow label="加分" value={scores} />
        <SummaryRow label="风险" value={risks} />
        <SummaryRow label="组合加分" value={combinations} />
        <SummaryRow label="启用指标" value={enabledTotal} />
      </div>
      <div style={{ marginTop: 16 }}>
        <div className="split-row" style={{ marginBottom: 8 }}>
          <span className="metric-label">预计覆盖健康</span>
          <Badge tone={filters ? 'good' : 'watch'}>{filters ? '可运行' : '需补规则'}</Badge>
        </div>
        <Progress value={Math.min(100, Math.max(24, enabledTotal * 10))} />
      </div>
    </section>
  );
}

const activeParameterKeys = [
  'min_price',
  'min_amount',
  'min_float_market_value',
  'max_float_market_value',
  'min_turnover',
  'max_turnover',
  'min_rps20',
  'min_rps60',
  'min_rps120',
  'min_pct_chg',
  'max_pct_chg',
  'max_amplitude',
  'volume_ratio_min',
  'max_ma_distance',
  'include_bj',
  'exclude_star_board',
];

function activeParameterCount(config: StrategyConfig) {
  const values = config as unknown as Record<string, unknown>;
  return activeParameterKeys.filter((key) => {
    const value = values[key];
    return value !== null && value !== undefined && value !== false && value !== '' && value !== 0;
  }).length;
}

function modeLabel(mode?: string | null) {
  if (mode === 'strict') return '严格模式';
  if (mode === 'score') return '评分模式';
  return '综合模式';
}

function SummaryRow({ label, value }: { label: string; value: number }) {
  return (
    <div className="split-row">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
