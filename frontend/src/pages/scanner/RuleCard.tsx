import type { IndicatorDefinition, StrategyRule } from '../../types';
import { Badge } from '../../design/Badge';
import { Button } from '../../design/Button';
import { CheckTile } from '../../design/CheckTile';
import { Select } from '../../design/Select';
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

const statusLabel: Record<string, string> = {
  executable: '可执行',
  display_only: '仅展示',
  planned: '待接入',
  partial: '部分可用',
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
        <Badge tone={actionTone[rule.action] || 'neutral'}>{ruleActionMeta[rule.action]?.label || '仅展示'}</Badge>
      </div>
      <p className="card-copy">
        {indicator ? ruleSummary(rule, indicator) : `${operator} ${rule.value ?? ''}`} · 缺失处理：{missingPolicyOptions.find((item) => item.id === rule.missing_policy)?.label || '缺失中性'} · 权重：{rule.weight ?? '未设置'}
      </p>
      <div className="rule-chip-grid">
        {indicator?.coverage_group ? <Badge>{indicator.coverage_group}</Badge> : null}
        {indicator?.data_status ? <Badge>{statusLabel[indicator.data_status] || indicator.data_status}</Badge> : null}
        <CheckTile checked={rule.enabled !== false} label={rule.enabled === false ? '停用' : '启用'} onCheckedChange={(checked) => onPatch({ enabled: checked })} />
      </div>
      <div className="rule-editor">
        <label>
          <span>动作</span>
          <Select
            label="动作"
            value={action}
            onChange={(value) => applyAction(value as StrategyRule['action'])}
            options={actions.map((item) => ({ value: item, label: ruleActionMeta[item].label }))}
          />
        </label>
        {!displayOnly ? (
          <>
            <label>
              <span>条件</span>
              <Select
                label="条件"
                value={operator}
                onChange={(value) => onPatch({ operator: value as StrategyRule['operator'] })}
                options={operators.map((item) => ({ value: item, label: ruleOperatorMeta[item]?.label || item }))}
              />
            </label>
            {operator !== 'is_true' ? (
              <label>
                <span>{operator === 'between' ? '下限' : '数值'}</span>
                {useChoiceValue ? (
                  <Select
                    label="数值"
                    value={String(rule.value ?? choiceOptions[0]?.value ?? '')}
                    onChange={(value) => onPatch({ value })}
                    options={choiceOptions.map((option) => ({ value: String(option.value), label: option.label }))}
                  />
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
          <Select
            label="缺失策略"
            value={rule.missing_policy || 'neutral'}
            onChange={(value) => onPatch({ missing_policy: value })}
            options={missingPolicyOptions.map((option) => ({ value: option.id, label: option.label }))}
          />
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
