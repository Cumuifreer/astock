import { useMemo, useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import type { IndicatorDefinition, RuleAction, StrategyConfig, StrategyRule } from '../../types';
import { Badge } from '../../design/Badge';
import { Select } from '../../design/Select';
import { Switch } from '../../design/Switch';
import {
  defaultValueForIndicator,
  indicatorParameterKeys,
  ruleInputStep,
  ruleOperatorMeta,
  supportedRuleActions,
  supportedRuleOperators,
} from '../../utils/strategy';

type IndicatorMatrixProps = {
  indicators: IndicatorDefinition[];
  rules: StrategyRule[];
  config: StrategyConfig;
  onAddRule: (indicator: IndicatorDefinition) => void;
  onPatchRule: (ruleId: string, patch: Partial<StrategyRule>) => void;
  onPatchConfig: (patch: Partial<StrategyConfig>) => void;
};

const sectionOrder = [
  '基础股票池',
  '流动性与成交',
  '相对强弱',
  '平台与突破',
  '趋势动能',
  '题材与板块',
  '资金流向',
  '涨停与事件',
  '筹码成本',
  '风险过滤',
  '候选展示',
  '待接入',
];

const alwaysOnKeys = new Set(['candidate_limit', 'sort_by', 'analysis_mode', 'signal_mode', 'rps_window']);

export function IndicatorMatrix({ indicators, rules, config, onAddRule, onPatchRule, onPatchConfig }: IndicatorMatrixProps) {
  const parameterByKey = useMemo(() => buildParameterMap(indicators), [indicators]);
  const displayIndicators = useMemo(() => dedupeIndicators(indicators), [indicators]);
  const groups = useMemo(() => groupIndicators(displayIndicators), [displayIndicators]);
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(() => new Set());
  const expandedGroups = useMemo(() => new Set(groups.map(([group]) => group).filter((group) => !collapsedGroups.has(group))), [collapsedGroups, groups]);
  const ruleByIndicator = useMemo(() => {
    const map = new Map<string, StrategyRule>();
    rules.forEach((rule) => {
      if (!map.has(rule.indicator_id)) map.set(rule.indicator_id, rule);
    });
    return map;
  }, [rules]);
  const enabledIndicators = displayIndicators.filter((indicator) => {
    const parameterKeys = indicatorParameterKeys(indicator);
    const rule = ruleByIndicator.get(indicator.id);
    return parameterKeys.length ? parameterEnabled(config, parameterKeys, parameterByKey) : Boolean(rule?.enabled);
  });

  return (
    <section className="surface pad indicator-matrix">
      <div className="section-heading">
        <div>
          <h2>指标配置矩阵</h2>
          <p>直接开启需要的指标，并在卡片里填写条件、分值或风险阈值。</p>
        </div>
        <Badge tone="info">{displayIndicators.length} 个指标</Badge>
      </div>
      <div className="indicator-active-strip" aria-label="已启用指标">
        <strong>已启用指标</strong>
        <div className="indicator-active-list">
          {enabledIndicators.length ? (
            enabledIndicators.slice(0, 18).map((indicator) => (
              <span className="indicator-active-chip" key={indicator.id}>
                {indicator.name}
              </span>
            ))
          ) : (
            <span className="field-readonly muted">点击左侧开启</span>
          )}
        </div>
      </div>
      <div className="list-stack">
        {groups.map(([group, rows]) => {
          const expanded = expandedGroups.has(group);
          return (
            <section className="indicator-group" key={group}>
              <div className="indicator-group-header">
                <button
                  aria-expanded={expanded}
                  className="indicator-group-toggle"
                  type="button"
                  onClick={() =>
                    setCollapsedGroups((current) => {
                      const next = new Set(current);
                      if (next.has(group)) next.delete(group);
                      else next.add(group);
                      return next;
                    })
                  }
                >
                  {expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                  <span>{group}</span>
                </button>
                <Badge>{rows.length} 项</Badge>
              </div>
              {expanded ? (
                <div className="indicator-card-grid">
                  {rows.map((indicator) => {
                    const rule = ruleByIndicator.get(indicator.id);
                    const parameterKeys = indicatorParameterKeys(indicator);
                    const isParameter = parameterKeys.length > 0;
                    const enabled = isParameter ? parameterEnabled(config, parameterKeys, parameterByKey) : Boolean(rule?.enabled);
                    const disabled = indicator.status === 'planned' || indicator.data_status === 'planned';
                    const alwaysOn = parameterKeys.length > 0 && parameterKeys.every((key) => alwaysOnKeys.has(key));
                    const booleanOnly = isSingleBooleanParameter(parameterKeys, parameterByKey);
                    return (
                      <article className={enabled || alwaysOn ? 'indicator-card active' : 'indicator-card'} key={indicator.id}>
                        <div className="indicator-card-head">
                          <Switch
                            checked={enabled || alwaysOn}
                            disabled={disabled || alwaysOn}
                            label={(enabled || alwaysOn) ? '开' : '关'}
                            onCheckedChange={(checked) => {
                              if (isParameter) {
                                onPatchConfig(parameterPatch(indicator, config, checked, parameterByKey));
                              } else if (rule) {
                                onPatchRule(rule.id, { enabled: checked });
                              } else if (checked) {
                                onAddRule(indicator);
                              }
                            }}
                          />
                          <div>
                            <small>开关</small>
                            <strong>{indicator.name}</strong>
                            <small>{sectionForIndicator(indicator)}</small>
                          </div>
                          <Badge tone={statusTone(indicator)}>{statusLabel(indicator)}</Badge>
                        </div>
                        <div className="indicator-card-body">
                          {isParameter && booleanOnly ? (
                            <span className="field-readonly muted">左侧开关控制</span>
                          ) : isParameter && (enabled || alwaysOn) ? (
                            <ParameterControls config={config} indicator={indicator} keys={parameterKeys} onPatchConfig={onPatchConfig} parameterByKey={parameterByKey} />
                          ) : isParameter ? (
                            <span className="field-readonly muted">点击左侧开启</span>
                          ) : enabled ? (
                            <RuleControls indicator={indicator} onPatchRule={onPatchRule} rule={rule} />
                          ) : (
                            <span className="field-readonly muted">点击左侧开启</span>
                          )}
                        </div>
                        <p className="indicator-note">{indicator.description || inputHint(indicator)}</p>
                      </article>
                    );
                  })}
                </div>
              ) : null}
            </section>
          );
        })}
      </div>
    </section>
  );
}

function ParameterControls({
  keys,
  indicator,
  config,
  parameterByKey,
  onPatchConfig,
}: {
  keys: string[];
  indicator: IndicatorDefinition;
  config: StrategyConfig;
  parameterByKey: Map<string, IndicatorDefinition>;
  onPatchConfig: (patch: Partial<StrategyConfig>) => void;
}) {
  return (
    <div className="matrix-control-stack">
      {keys.map((key) => {
        const parameter = parameterByKey.get(key) || indicator;
        return <ParameterInput config={config} indicator={parameter} key={key} name={parameter.name || indicator.name} onPatchConfig={onPatchConfig} parameterKey={key} />;
      })}
    </div>
  );
}

function ParameterInput({
  parameterKey,
  name,
  indicator,
  config,
  onPatchConfig,
}: {
  parameterKey: string;
  name: string;
  indicator: IndicatorDefinition;
  config: StrategyConfig;
  onPatchConfig: (patch: Partial<StrategyConfig>) => void;
}) {
  const control = indicator.control || { type: 'number' };
  const value = (config as unknown as Record<string, unknown>)[parameterKey];
  const patchValue = (nextValue: unknown) => onPatchConfig({ [parameterKey]: nextValue } as Partial<StrategyConfig>);
  const moneyHint = control.type === 'money' ? formatChineseMoneyUnit(value) : '';
  if (control.type === 'boolean') {
    return <span className="field-readonly muted">{name}由左侧开关控制</span>;
  }
  if (control.type === 'select' && control.options?.length) {
    const options = control.options.map((option) => ({ value: String(option.value), label: option.label }));
    const currentValue = value === null || value === undefined ? options[0]?.value || '' : String(value);
    return (
      <label className="compact-field">
        <span>{name}</span>
        <Select label={name} value={currentValue} onChange={(raw) => patchValue(coerceSelectValue(raw, value))} options={options} />
      </label>
    );
  }
  return (
    <label className="compact-field">
      <span>{name}</span>
      <div className="input-with-unit">
        <input
          id={`strategy-field-${parameterKey}`}
          min={control.min}
          max={control.max}
          step={control.step || (control.type === 'money' ? 1000000 : 0.01)}
          type="number"
          value={value === null || value === undefined ? '' : String(value)}
          onChange={(event) => patchValue(event.target.value.trim() === '' ? (control.allow_blank ? null : 0) : Number(event.target.value))}
        />
        {control.unit || indicator.unit ? <em>{control.unit || indicator.unit}</em> : null}
      </div>
      {moneyHint ? <span className="money-unit-hint">{moneyHint}</span> : null}
    </label>
  );
}

function formatChineseMoneyUnit(value: unknown) {
  const amount = Number(value);
  if (!Number.isFinite(amount) || amount <= 0) return '';
  const abs = Math.abs(amount);
  const unit = abs >= 100_000_000 ? { divisor: 100_000_000, label: '亿' } : { divisor: 10_000, label: '万' };
  const converted = amount / unit.divisor;
  const formatted = Number.isInteger(converted)
    ? String(converted)
    : converted >= 100
      ? converted.toFixed(0)
      : converted >= 10
        ? converted.toFixed(1).replace(/\.0$/, '')
        : converted.toFixed(2).replace(/\.?0+$/, '');
  return `约 ${formatted}${unit.label}`;
}

function RuleControls({
  indicator,
  rule,
  onPatchRule,
}: {
  indicator: IndicatorDefinition;
  rule?: StrategyRule;
  onPatchRule: (ruleId: string, patch: Partial<StrategyRule>) => void;
}) {
  if (!rule) {
    return <span className="field-readonly muted">点击左侧开启</span>;
  }
  const actions = supportedRuleActions(indicator);
  if (!actions.length) {
    return <span className="field-readonly muted">由系统自动展示</span>;
  }
  const action = actions.includes(rule.action) ? rule.action : actions[0] || 'filter';
  const operators = supportedRuleOperators(indicator, action);
  const operator = operators.includes(rule.operator) ? rule.operator : operators[0] || 'gte';
  const patch = (change: Partial<StrategyRule>) => onPatchRule(rule.id, change);
  return (
    <div className="matrix-control-stack">
      <div className="matrix-control-inline">
        <Select label="使用方式" value={action} onChange={(value) => patch({ action: value as RuleAction })} options={actions.map((item) => ({ value: item, label: actionLabel(item) }))} />
        <Select label="条件" value={operator} onChange={(value) => patch({ operator: value as StrategyRule['operator'] })} options={operators.map((item) => ({ value: item, label: ruleOperatorMeta[item]?.label || item }))} />
        <RuleValueInput indicator={indicator} onPatch={patch} rule={{ ...rule, action, operator }} />
        {action === 'score' || action === 'risk' ? (
          <label className="compact-field tiny">
            <span>{action === 'score' ? '加分' : '降权'}</span>
            <input step="1" type="number" value={rule.weight ?? 5} onChange={(event) => patch({ weight: Number(event.target.value) })} />
          </label>
        ) : null}
      </div>
    </div>
  );
}

function RuleValueInput({ indicator, rule, onPatch }: { indicator: IndicatorDefinition; rule: StrategyRule; onPatch: (change: Partial<StrategyRule>) => void }) {
  if (rule.operator === 'is_true') return <span className="field-readonly">满足即可</span>;
  if (indicator.choice_options?.length) {
    return (
      <Select
        label="取值"
        value={String(rule.value ?? indicator.choice_options[0]?.value ?? '')}
        onChange={(value) => onPatch({ value })}
        options={indicator.choice_options.map((option) => ({ value: String(option.value), label: option.label }))}
      />
    );
  }
  return (
    <span className="matrix-control-inline">
      <label className="compact-field tiny">
        <span>{rule.operator === 'between' ? '下限' : '数值'}</span>
        <input step={ruleInputStep(indicator)} type="number" value={rule.value === null || rule.value === undefined ? '' : String(rule.value)} onChange={(event) => onPatch({ value: event.target.value.trim() === '' ? null : Number(event.target.value) })} />
      </label>
      {rule.operator === 'between' ? (
        <label className="compact-field tiny">
          <span>上限</span>
          <input step={ruleInputStep(indicator)} type="number" value={rule.value2 === null || rule.value2 === undefined ? '' : String(rule.value2)} onChange={(event) => onPatch({ value2: event.target.value.trim() === '' ? null : Number(event.target.value) })} />
        </label>
      ) : null}
    </span>
  );
}

function buildParameterMap(indicators: IndicatorDefinition[]) {
  const map = new Map<string, IndicatorDefinition>();
  indicators.forEach((indicator) => {
    indicatorParameterKeys(indicator).forEach((key) => {
      if (indicator.kind === 'strategy_param' || !map.has(key)) map.set(key, indicator);
    });
  });
  return map;
}

function isSingleBooleanParameter(keys: string[], parameterByKey: Map<string, IndicatorDefinition>) {
  if (keys.length !== 1) return false;
  return parameterByKey.get(keys[0])?.control?.type === 'boolean';
}

function dedupeIndicators(indicators: IndicatorDefinition[]) {
  const reservedParameterKeys = new Set<string>();
  const output: IndicatorDefinition[] = [];
  const shouldShow = (indicator: IndicatorDefinition) => indicator.status !== 'planned' && indicator.data_status !== 'planned' && (indicatorParameterKeys(indicator).length > 0 || supportedRuleActions(indicator).length > 0);
  indicators.forEach((indicator) => {
    const keys = indicatorParameterKeys(indicator);
    if (indicator.kind === 'data' && keys.length && shouldShow(indicator)) {
      keys.forEach((key) => reservedParameterKeys.add(key));
      output.push(indicator);
    }
  });
  indicators.forEach((indicator) => {
    if (indicator.kind === 'data' && !indicatorParameterKeys(indicator).length && shouldShow(indicator)) output.push(indicator);
  });
  indicators.forEach((indicator) => {
    if (indicator.kind !== 'strategy_param') return;
    const keys = indicatorParameterKeys(indicator);
    if (shouldShow(indicator) && !keys.some((key) => reservedParameterKeys.has(key))) output.push(indicator);
  });
  const seen = new Set<string>();
  return output.filter((indicator) => {
    const key = indicatorParameterKeys(indicator).join('|') || indicator.id;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function groupIndicators(indicators: IndicatorDefinition[]): Array<[string, IndicatorDefinition[]]> {
  const buckets = new Map<string, IndicatorDefinition[]>();
  indicators.forEach((indicator) => {
    const group = sectionForIndicator(indicator);
    buckets.set(group, [...(buckets.get(group) || []), indicator]);
  });
  return [...buckets.entries()]
    .sort(([left], [right]) => sectionIndex(left) - sectionIndex(right) || left.localeCompare(right, 'zh-CN'))
    .map(([group, rows]) => [
      group,
      rows.sort((left, right) => {
        const leftRank = indicatorRank(left);
        const rightRank = indicatorRank(right);
        return leftRank - rightRank || left.name.localeCompare(right.name, 'zh-CN');
      }),
    ]);
}

function sectionForIndicator(indicator: IndicatorDefinition) {
  const id = indicator.group_id || indicator.category_id || indicator.group_label;
  if (indicator.status === 'planned' || indicator.data_status === 'planned') return '待接入';
  if (id === 'stock_pool' || indicator.category_id === 'stock_pool' || indicator.group_label === '基础股票池') return '基础股票池';
  if (['price_volume', 'quote'].includes(id) || indicator.category_id === 'quote') return '流动性与成交';
  if (['strength_trend', 'technical'].includes(id)) return '相对强弱';
  if (['breakout_pullback', 'platform_range', 'platform_breakout', 'platform_ma', 'platform_setup', 'platform'].includes(id) || indicator.category_id === 'platform') return '平台与突破';
  if (['trend_ema', 'trend_macd', 'trend_stoch', 'trend_risk', 'trend'].includes(id)) return '趋势动能';
  if (indicator.category_id === 'theme' || id === 'theme_strength') return '题材与板块';
  if (indicator.category_id === 'capital_flow') return '资金流向';
  if (indicator.category_id === 'event') return '涨停与事件';
  if (indicator.category_id === 'chips') return '筹码成本';
  if (indicator.category_id === 'risk') return '风险过滤';
  return indicator.group_label || '候选展示';
}

function sectionIndex(section: string) {
  const index = sectionOrder.indexOf(section);
  return index >= 0 ? index : sectionOrder.length;
}

function indicatorRank(indicator: IndicatorDefinition) {
  const keys = indicatorParameterKeys(indicator);
  const firstKey = keys[0] || indicator.id;
  const ranks = [
    'min_price',
    'min_amount',
    'min_float_market_value',
    'max_float_market_value',
    'include_bj',
    'exclude_star_board',
    'missing_turnover_policy',
    'missing_float_market_value_policy',
    'candidate_limit',
    'sort_by',
    'min_turnover',
    'max_turnover',
    'min_pct_chg',
    'max_pct_chg',
    'volume_ratio_min',
    'rps_window',
    'min_rps20',
    'min_rps60',
    'min_rps120',
  ];
  const index = ranks.indexOf(firstKey);
  return index >= 0 ? index : 200;
}

function parameterEnabled(config: StrategyConfig, keys: string[], parameterByKey: Map<string, IndicatorDefinition>) {
  if (keys.every((key) => alwaysOnKeys.has(key))) return true;
  const selectKeys = keys.filter((key) => parameterByKey.get(key)?.control?.type === 'select');
  if (selectKeys.length && selectKeys.every((key) => isOffValue((config as unknown as Record<string, unknown>)[key]))) {
    return false;
  }
  return keys.some((key) => {
    if (alwaysOnKeys.has(key)) return false;
    const value = (config as unknown as Record<string, unknown>)[key];
    const control = parameterByKey.get(key)?.control;
    if (control?.type === 'select') return value !== null && value !== undefined && !isOffValue(value);
    return value !== null && value !== undefined && value !== false && value !== 0 && value !== '';
  });
}

function isOffValue(value: unknown) {
  return ['', 'off', 'none'].includes(String(value ?? ''));
}

function parameterPatch(indicator: IndicatorDefinition, config: StrategyConfig, checked: boolean, parameterByKey: Map<string, IndicatorDefinition>): Partial<StrategyConfig> {
  const patch: Record<string, unknown> = {};
  indicatorParameterKeys(indicator).forEach((key) => {
    const parameter = parameterByKey.get(key) || indicator;
    const current = (config as unknown as Record<string, unknown>)[key];
    patch[key] = checked ? onValue(parameter, current) : offValue(key, current, parameter);
  });
  return patch as Partial<StrategyConfig>;
}

function onValue(indicator: IndicatorDefinition, current: unknown) {
  if (current !== null && current !== undefined && current !== '' && current !== false && current !== 0 && !['off', 'none'].includes(String(current))) return current;
  if (indicator.control?.type === 'boolean') return true;
  if (indicator.control?.type === 'select') {
    return indicator.control.options?.find((option) => !['off', 'none'].includes(String(option.value)))?.value || indicator.control.options?.[0]?.value || '';
  }
  const recommended = defaultValueForIndicator(indicator);
  return recommended === '' ? indicator.range_hint?.min ?? 1 : recommended;
}

function offValue(key: string, current: unknown, indicator: IndicatorDefinition) {
  if (alwaysOnKeys.has(key)) return current;
  if (indicator.control?.type === 'boolean' || typeof current === 'boolean') return false;
  if (indicator.control?.type === 'select') {
    const option = indicator.control.options?.find((item) => ['off', 'none'].includes(String(item.value)));
    return option?.value ?? current;
  }
  if (indicator.control?.allow_blank || key.startsWith('min_') || key.startsWith('max_')) return null;
  return 0;
}

function coerceSelectValue(raw: string, previous: unknown) {
  if (typeof previous === 'number') return Number(raw);
  return raw;
}

function actionLabel(action: RuleAction) {
  if (action === 'filter') return '硬性筛选';
  if (action === 'score') return '加分排序';
  if (action === 'risk') return '风险降权';
  return '展示字段';
}

function inputHint(indicator: IndicatorDefinition) {
  if (indicator.range_hint?.min !== undefined && indicator.range_hint?.max !== undefined) return `建议填写 ${indicator.range_hint.min} 到 ${indicator.range_hint.max}`;
  if (indicator.range_hint?.min !== undefined) return `建议不低于 ${indicator.range_hint.min}`;
  return '按你的策略偏好填写。';
}

function statusLabel(indicator: IndicatorDefinition) {
  if (indicator.data_status === 'planned' || indicator.status === 'planned') return '待接入';
  if (indicator.data_status === 'display_only') return '自动展示';
  if (indicator.data_status === 'partial') return '覆盖较少';
  return '可用';
}

function statusTone(indicator: IndicatorDefinition): 'good' | 'watch' | 'neutral' {
  if (indicator.data_status === 'planned' || indicator.status === 'planned') return 'neutral';
  if (indicator.data_status === 'partial') return 'watch';
  return 'good';
}
