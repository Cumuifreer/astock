import type {
  IndicatorDefinition,
  IndicatorLibrary,
  RuleAction,
  RuleOperator,
  StrategyConfig,
  StrategyResonance,
  StrategyRule,
} from '../types';
import { formatMoney, formatNumber } from './format';

export const ruleActionMeta: Record<RuleAction, { label: string; verb: string; note: string }> = {
  filter: { label: '硬筛', verb: '必须满足', note: '不满足直接剔除' },
  score: { label: '加分', verb: '命中加分', note: '参与排序分数' },
  risk: { label: '风险', verb: '命中扣分', note: '只做风险折减' },
  display: { label: '展示', verb: '候选展示', note: '不参与决策' },
};

export const ruleOperatorMeta: Record<RuleOperator, { label: string; summary: string }> = {
  gte: { label: '>=', summary: '不低于' },
  lte: { label: '<=', summary: '不高于' },
  gt: { label: '>', summary: '高于' },
  lt: { label: '<', summary: '低于' },
  between: { label: '区间', summary: '介于' },
  eq: { label: '=', summary: '等于' },
  neq: { label: '!=', summary: '不等于' },
  is_true: { label: '为真', summary: '为真' },
  recent: { label: '近期', summary: '近期出现' },
};

export const missingPolicyOptions = [
  { id: 'neutral', label: '缺失中性' },
  { id: 'skip', label: '缺失跳过' },
  { id: 'keep', label: '缺失保留' },
  { id: 'allow', label: '缺失允许' },
];

export const resonanceBonusOptions = [
  { value: 4, label: '+4' },
  { value: 8, label: '+8' },
  { value: 12, label: '+12' },
  { value: 16, label: '+16' },
];

export function composeStrategyConfig(
  config: StrategyConfig | null | undefined,
  rules: StrategyRule[],
  resonances: StrategyResonance[],
): StrategyConfig {
  const base = config ? { ...config } : ({} as StrategyConfig);
  const liveRuleIds = new Set(rules.map((rule) => rule.id));
  const executableResonances = resonances.map((resonance) => ({
    ...resonance,
    rule_ids: (resonance.rule_ids || []).filter((id) => liveRuleIds.has(id)),
  }));
  return {
    ...base,
    strategy_rules: rules,
    strategy_resonances: executableResonances,
  };
}

export function usableRuleIndicators(library?: IndicatorLibrary): IndicatorDefinition[] {
  return (library?.indicators || [])
    .filter((indicator) => indicator.kind === 'data' && indicator.status !== 'planned')
    .filter((indicator) => !indicator.paired_strategy_ids?.length)
    .filter((indicator) => indicator.operator_semantics !== 'market_context')
    .filter((indicator) => indicator.data_status !== 'display_only' || indicator.display_scope === 'candidate')
    .filter((indicator) => supportedRuleActions(indicator).length > 0)
    .sort((left, right) => `${left.group_label}${left.name}`.localeCompare(`${right.group_label}${right.name}`, 'zh-CN'));
}

export function supportedRuleActions(indicator: IndicatorDefinition): RuleAction[] {
  const actions = (indicator.supported_actions || []).filter((action): action is RuleAction => action in ruleActionMeta);
  return actions.length > 0 ? actions : ['display'];
}

export function supportedRuleOperators(indicator: IndicatorDefinition, action: RuleAction): RuleOperator[] {
  if (action === 'display') return [indicator.default_operator || 'gte'];
  const operators = (indicator.supported_operators || []).filter((operator): operator is RuleOperator => operator in ruleOperatorMeta);
  return operators.length > 0 ? operators : ['gte', 'lte', 'between'];
}

export function defaultOperatorForIndicator(indicator: IndicatorDefinition): RuleOperator {
  const operators = supportedRuleOperators(indicator, 'filter');
  return indicator.default_operator && operators.includes(indicator.default_operator) ? indicator.default_operator : operators[0] || 'gte';
}

export function defaultStrategyRule(indicator: IndicatorDefinition): StrategyRule {
  const actions = supportedRuleActions(indicator);
  const action = actions.includes('filter') ? 'filter' : actions[0] || 'display';
  const recommendation = (indicator.recommended_rules || []).find((item) => item.action === action) || (indicator.recommended_rules || [])[0];
  const operator = recommendation?.operator || defaultOperatorForIndicator(indicator);
  const missingPolicy = indicator.default_missing_policy === 'skip' ? 'skip' : indicator.default_missing_policy === 'allow' ? 'keep' : 'neutral';
  return {
    id: createRuleId(indicator.id),
    indicator_id: indicator.id,
    action,
    operator,
    value: recommendation?.value ?? defaultValueForIndicator(indicator),
    value2: recommendation?.value2 ?? (operator === 'between' ? indicator.range_hint?.max ?? '' : undefined),
    window_days: recommendation?.window_days,
    weight: recommendation?.weight ?? null,
    missing_policy: missingPolicy,
    enabled: true,
  };
}

export function defaultValueForIndicator(indicator: IndicatorDefinition) {
  const recommendation =
    (indicator.recommended_rules || []).find((item) => item.action === 'filter') ||
    (indicator.recommended_rules || []).find((item) => item.action === 'score') ||
    (indicator.recommended_rules || [])[0];
  if (recommendation?.value !== undefined) return recommendation.value;
  if (indicator.operator_semantics === 'event_state' && indicator.choice_options?.length) return indicator.choice_options[0].value;
  if (indicator.default_operator === 'between' && indicator.range_hint?.min !== undefined) return indicator.range_hint.min;
  return '';
}

export function createRuleId(indicatorId: string) {
  const random = typeof crypto !== 'undefined' && 'randomUUID' in crypto ? crypto.randomUUID() : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  return `rule-${indicatorId}-${random}`;
}

export function createResonanceId() {
  const random = typeof crypto !== 'undefined' && 'randomUUID' in crypto ? crypto.randomUUID() : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  return `resonance-${random}`;
}

export function isNumericIndicator(indicator: IndicatorDefinition) {
  return !['boolean', 'choice', 'event'].includes(String(indicator.value_type || 'number'));
}

export function ruleInputStep(indicator: IndicatorDefinition) {
  if (indicator.value_type === 'money') return '1000000';
  if (indicator.value_type === 'percent' || indicator.value_type === 'ratio' || indicator.value_type === 'multiple') return '0.01';
  return '1';
}

export function ruleValuePlaceholder(indicator: IndicatorDefinition) {
  const recommendation = (indicator.recommended_rules || [])[0];
  if (recommendation?.value !== undefined) return String(recommendation.value);
  if (indicator.range_hint?.min !== undefined) return String(indicator.range_hint.min);
  if (indicator.value_type === 'score') return '60';
  if (indicator.value_type === 'multiple') return '1.5';
  return '';
}

export function ruleSummary(rule: StrategyRule, indicator: IndicatorDefinition) {
  const action = rule.action in ruleActionMeta ? rule.action : 'display';
  if (action === 'display') return ruleActionMeta.display.verb;
  const operator = ruleOperatorMeta[rule.operator]?.summary || rule.operator;
  const unit = indicator.unit || '';
  const left = rule.value === null || rule.value === undefined || rule.value === '' ? '未设定' : `${rule.value}${unit}`;
  if (rule.operator === 'between') {
    const right = rule.value2 === null || rule.value2 === undefined || rule.value2 === '' ? '未设定' : `${rule.value2}${unit}`;
    return `${operator} ${left} - ${right}，${ruleActionMeta[action].verb}`;
  }
  if (rule.operator === 'is_true') return `${operator}，${ruleActionMeta[action].verb}`;
  return `${operator} ${left}，${ruleActionMeta[action].verb}`;
}

export function strategyRuleSelectLabel(rule: StrategyRule, indicatorById: Map<string, IndicatorDefinition>) {
  const indicator = indicatorById.get(rule.indicator_id);
  if (!indicator) return rule.indicator_id;
  const operator = ruleOperatorMeta[rule.operator]?.summary || rule.operator;
  const value =
    rule.operator === 'is_true'
      ? ''
      : rule.operator === 'between'
        ? ` ${rule.value ?? '-'} - ${rule.value2 ?? '-'}${indicator.unit || ''}`
        : ` ${rule.value ?? '-'}${indicator.unit || ''}`;
  return `${indicator.name} ${operator}${value} · ${ruleActionMeta[rule.action]?.label || rule.action}`;
}

export function strategySummary(strategy: StrategyConfig | null | undefined) {
  if (!strategy) return '尚未加载策略';
  const bits = [
    strategy.analysis_mode || 'score',
    `候选 ${formatNumber(strategy.candidate_limit || 0, 0)}`,
    `成交额 ${formatMoney(strategy.min_amount)}`,
  ];
  return bits.join(' · ');
}
