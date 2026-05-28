import type { IndicatorDefinition, StrategyRule } from '../../types';
import { Badge } from '../../design/Badge';
import { formatNumber } from '../../utils/format';

const actionTone: Record<string, 'info' | 'good' | 'watch' | 'neutral'> = {
  filter: 'info',
  score: 'good',
  risk: 'watch',
  display: 'neutral',
};

export function RuleCard({ rule, indicator }: { rule: StrategyRule; indicator?: IndicatorDefinition }) {
  const name = indicator?.name || rule.indicator_id;
  const operator = rule.operator === 'between' ? `${formatNumber(rule.value, 2)} - ${formatNumber(rule.value2, 2)}` : `${rule.operator} ${rule.value ?? ''}`;
  return (
    <article className="rule-card">
      <div className="rule-card-header">
        <strong>{name}</strong>
        <Badge tone={actionTone[rule.action] || 'neutral'}>{rule.action}</Badge>
      </div>
      <p className="card-copy">
        {operator || '展示列'} · 缺失策略：{rule.missing_policy || 'neutral'} · 权重：{rule.weight ?? '--'}
      </p>
      <div className="rule-chip-grid">
        {indicator?.coverage_group ? <Badge>{indicator.coverage_group}</Badge> : null}
        {indicator?.data_status ? <Badge>{indicator.data_status}</Badge> : null}
        {rule.enabled === false ? <Badge tone="risk">停用</Badge> : <Badge tone="good">启用</Badge>}
      </div>
    </article>
  );
}
