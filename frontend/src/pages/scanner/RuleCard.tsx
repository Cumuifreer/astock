import type { IndicatorDefinition, StrategyRule } from '../../types';
import { Badge } from '../../design/Badge';
import { Button } from '../../design/Button';
import { CheckTile } from '../../design/CheckTile';
import {
  defaultOperatorForIndicator,
  defaultValueForIndicator,
  isNumericIndicator,
  missingPolicyOptions,
  ruleActionMeta,
  ruleInputStep,
  ruleOperatorMeta,
  ruleSummary,
  ruleValuePlaceholder,
  supportedRuleActions,
  supportedRuleOperators,
} from '../../utils/strategy';
import { Trash2 } from 'lucide-react';

const actionTone: Record<string, 'info' | 'good' | 'watch' | 'neutral'> = {
  filter: 'info',
  score: 'good',
  risk: 'watch',
  display: 'neutral',
};

type RuleCardProps = {
  rule: StrategyRule;
  indicator?: IndicatorDefinition;
  onPatch: (patch: Partial<StrategyRule>) => void;
  onRemove: () => void;
};

export function RuleCard({ rule, indicator, onPatch, onRemove }: RuleCardProps) {
  const name = indicator?.name || rule.indicator_id;
  const actions = indicator ? supportedRuleActions(indicator) : (['filter', 'score', 'risk', 'display'] as StrategyRule['action'][]);
  const action = actions.includes(rule.action) ? rule.action : actions[0] || 'display';
  const operators = indicator ? supportedRuleOperators(indicator, action) : (['gte', 'lte', 'between'] as StrategyRule['operator'][]);
  const operator = operators.includes(rule.operator) ? rule.operator : operators[0] || 'gte';
  const numeric = indicator ? isNumericIndicator(indicator) : true;
  const displayOnly = action === 'display';
  const choiceOptions = indicator?.choice_options || [];
  const useChoiceValue = indicator?.operator_semantics === 'event_state' && choiceOptions.length > 0 && operator !== 'is_true';
  const applyAction = (nextAction: StrategyRule['action']) => {
    if (!indicator) {
      onPatch({ action: nextAction });
      return;
    }
    onPatch({
      action: nextAction,
      operator: nextAction === 'display' ? operator : defaultOperatorForIndicator(indicator),
      value: nextAction === 'display' ? rule.value : defaultValueForIndicator(indicator),
      value2: undefined,
    });
  };
  const setValue = (key: 'value' | 'value2', value: string) => {
    onPatch({ [key]: value === '' ? null : numeric ? Number(value) : value } as Partial<StrategyRule>);
  };
  return (
    <article className="rule-card">
      <div className="rule-card-header">
        <strong>{name}</strong>
        <Badge tone={actionTone[rule.action] || 'neutral'}>{rule.action}</Badge>
      </div>
      <p className="card-copy">
        {indicator ? ruleSummary(rule, indicator) : `${operator} ${rule.value ?? ''}`} · 缺失策略：{rule.missing_policy || 'neutral'} · 权重：{rule.weight ?? '--'}
      </p>
      <div className="rule-chip-grid">
        {indicator?.coverage_group ? <Badge>{indicator.coverage_group}</Badge> : null}
        {indicator?.data_status ? <Badge>{indicator.data_status}</Badge> : null}
        <CheckTile checked={rule.enabled !== false} label={rule.enabled === false ? '停用' : '启用'} onCheckedChange={(checked) => onPatch({ enabled: checked })} />
      </div>
      <div className="rule-editor">
        <label>
          <span>动作</span>
          <select value={action} onChange={(event) => applyAction(event.target.value as StrategyRule['action'])}>
            {actions.map((item) => (
              <option key={item} value={item}>
                {ruleActionMeta[item].label}
              </option>
            ))}
          </select>
        </label>
        {!displayOnly ? (
          <>
            <label>
              <span>条件</span>
              <select value={operator} onChange={(event) => onPatch({ operator: event.target.value as StrategyRule['operator'] })}>
                {operators.map((item) => (
                  <option key={item} value={item}>
                    {ruleOperatorMeta[item]?.label || item}
                  </option>
                ))}
              </select>
            </label>
            {operator !== 'is_true' ? (
              <label>
                <span>{operator === 'between' ? '下限' : '数值'}</span>
                {useChoiceValue ? (
                  <select value={String(rule.value ?? choiceOptions[0]?.value ?? '')} onChange={(event) => onPatch({ value: event.target.value })}>
                    {choiceOptions.map((option) => (
                      <option key={String(option.value)} value={String(option.value)}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    type={numeric ? 'number' : 'text'}
                    step={indicator && numeric ? ruleInputStep(indicator) : undefined}
                    value={String(rule.value ?? '')}
                    onChange={(event) => setValue('value', event.target.value)}
                    placeholder={indicator ? ruleValuePlaceholder(indicator) : ''}
                  />
                )}
              </label>
            ) : null}
            {operator === 'between' ? (
              <label>
                <span>上限</span>
                <input
                  type={numeric ? 'number' : 'text'}
                  step={indicator && numeric ? ruleInputStep(indicator) : undefined}
                  value={String(rule.value2 ?? '')}
                  onChange={(event) => setValue('value2', event.target.value)}
                />
              </label>
            ) : null}
            {(action === 'score' || action === 'risk') ? (
              <label>
                <span>{action === 'risk' ? '扣分' : '权重'}</span>
                <input
                  type="number"
                  step="1"
                  value={rule.weight ?? ''}
                  onChange={(event) => onPatch({ weight: event.target.value === '' ? null : Number(event.target.value) })}
                />
              </label>
            ) : null}
          </>
        ) : null}
        <label>
          <span>缺失策略</span>
          <select value={rule.missing_policy || 'neutral'} onChange={(event) => onPatch({ missing_policy: event.target.value })}>
            {missingPolicyOptions.map((option) => (
              <option key={option.id} value={option.id}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="rule-card-actions">
        <Button icon={<Trash2 size={14} />} onClick={onRemove} variant="ghost">
          删除规则
        </Button>
      </div>
    </article>
  );
}
