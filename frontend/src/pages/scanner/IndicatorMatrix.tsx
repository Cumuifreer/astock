import { useMemo, useState } from 'react';
import type { IndicatorDefinition, RuleAction, StrategyConfig, StrategyRule } from '../../types';
import { Badge } from '../../design/Badge';
import { Button } from '../../design/Button';
import { Switch } from '../../design/Switch';
import {
  defaultStrategyRule,
  defaultValueForIndicator,
  indicatorParameterKeys,
  indicatorParameterScope,
  ruleActionMeta,
  ruleSummary,
  supportedRuleActions,
} from '../../utils/strategy';
import { formatNumber } from '../../utils/format';

type IndicatorMatrixProps = {
  indicators: IndicatorDefinition[];
  rules: StrategyRule[];
  config: StrategyConfig;
  onAddRule: (indicator: IndicatorDefinition) => void;
  onPatchRule: (ruleId: string, patch: Partial<StrategyRule>) => void;
  onPatchConfig: (patch: Partial<StrategyConfig>) => void;
  onFocusParameter: (indicator: IndicatorDefinition) => void;
};

const preferredGroups = [
  '股票池',
  '行情流动性',
  '技术强弱',
  '平台形态',
  '趋势动能',
  '题材板块',
  '资金流向',
  '涨停与事件',
  '筹码成本',
  '风险过滤',
  '展示字段',
  '待接入',
];

export function IndicatorMatrix({
  indicators,
  rules,
  config,
  onAddRule,
  onPatchRule,
  onPatchConfig,
  onFocusParameter,
}: IndicatorMatrixProps) {
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(() => new Set(preferredGroups));
  const ruleByIndicator = useMemo(() => {
    const map = new Map<string, StrategyRule>();
    rules.forEach((rule) => {
      if (!map.has(rule.indicator_id)) map.set(rule.indicator_id, rule);
    });
    return map;
  }, [rules]);
  const groups = useMemo(() => groupIndicators(indicators), [indicators]);

  return (
    <section className="surface pad indicator-matrix">
      <div className="section-heading">
        <div>
          <h2>全指标矩阵</h2>
          <p>全部指标默认可见，启用后自动进入筛选、加分、风险或展示配置。</p>
        </div>
        <Badge tone="info">{indicators.length} 个指标</Badge>
      </div>
      <div className="list-stack">
        {groups.map(([group, rows]) => {
          const expanded = expandedGroups.has(group);
          return (
            <section className="indicator-group" key={group}>
              <button
                className="indicator-group-header"
                type="button"
                onClick={() =>
                  setExpandedGroups((current) => {
                    const next = new Set(current);
                    if (next.has(group)) next.delete(group);
                    else next.add(group);
                    return next;
                  })
                }
              >
                <span>{group}</span>
                <Badge>{rows.length} 项</Badge>
              </button>
              {expanded ? (
                <div className="indicator-table" role="table" aria-label={`${group}指标`}>
                  <div className="indicator-row indicator-row-head" role="row">
                    <span>启用</span>
                    <span>指标名</span>
                    <span>用途</span>
                    <span>条件 / 参数</span>
                    <span>权重</span>
                    <span>数据状态</span>
                    <span>操作</span>
                  </div>
                  {rows.map((indicator) => {
                    const rule = ruleByIndicator.get(indicator.id);
                    const parameterKeys = indicatorParameterKeys(indicator);
                    const isParameter = parameterKeys.length > 0;
                    const enabled = isParameter ? parameterEnabled(config, parameterKeys) : Boolean(rule?.enabled);
                    const disabled = indicator.status === 'planned' || indicator.data_status === 'planned';
                    return (
                      <div className="indicator-row" role="row" key={indicator.id}>
                        <span>
                          <Switch
                            checked={enabled}
                            disabled={disabled}
                            label={enabled ? '开启' : '关闭'}
                            onCheckedChange={(checked) => {
                              if (isParameter) {
                                onPatchConfig(parameterPatch(indicator, config, checked));
                              } else if (rule) {
                                onPatchRule(rule.id, { enabled: checked });
                              } else if (checked) {
                                onAddRule(indicator);
                              }
                            }}
                          />
                        </span>
                        <span>
                          <strong>{indicator.name}</strong>
                          <small>{indicator.group_label || indicator.category_id || group}</small>
                        </span>
                        <span>{purposeLabel(indicator, rule)}</span>
                        <span>{conditionLabel(indicator, rule, config)}</span>
                        <span>{weightLabel(rule)}</span>
                        <span>
                          <Badge tone={statusTone(indicator)}>{statusLabel(indicator)}</Badge>
                        </span>
                        <span>
                          <Button disabled={!isParameter} onClick={() => onFocusParameter(indicator)} variant="ghost">
                            {isParameter ? '调整参数' : '说明'}
                          </Button>
                        </span>
                      </div>
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

function groupIndicators(indicators: IndicatorDefinition[]): Array<[string, IndicatorDefinition[]]> {
  const buckets = new Map<string, IndicatorDefinition[]>();
  indicators.forEach((indicator) => {
    const group = indicator.group_label || indicator.category_id || (indicator.status === 'planned' ? '待接入' : '展示字段');
    buckets.set(group, [...(buckets.get(group) || []), indicator]);
  });
  return [...buckets.entries()].sort(([left], [right]) => {
    const leftOrder = preferredGroups.indexOf(left);
    const rightOrder = preferredGroups.indexOf(right);
    return (leftOrder < 0 ? 99 : leftOrder) - (rightOrder < 0 ? 99 : rightOrder) || left.localeCompare(right, 'zh-CN');
  });
}

function parameterEnabled(config: StrategyConfig, keys: string[]) {
  return keys.some((key) => {
    const value = (config as unknown as Record<string, unknown>)[key];
    return value !== null && value !== undefined && value !== false && value !== 0 && value !== '';
  });
}

function parameterPatch(indicator: IndicatorDefinition, config: StrategyConfig, checked: boolean): Partial<StrategyConfig> {
  const patch: Record<string, unknown> = {};
  indicatorParameterKeys(indicator).forEach((key) => {
    const current = (config as unknown as Record<string, unknown>)[key];
    patch[key] = checked ? current || defaultParameterValue(indicator) : offValue(key, current);
  });
  return patch as Partial<StrategyConfig>;
}

function defaultParameterValue(indicator: IndicatorDefinition) {
  if (indicator.control?.type === 'boolean') return true;
  if (indicator.control?.type === 'select') return indicator.control.options?.[0]?.value || defaultValueForIndicator(indicator);
  return defaultValueForIndicator(indicator) || indicator.range_hint?.min || 1;
}

function offValue(key: string, current: unknown) {
  if (typeof current === 'boolean' || key.startsWith('include_') || key.startsWith('exclude_')) return false;
  if (key.startsWith('max_')) return null;
  return 0;
}

function purposeLabel(indicator: IndicatorDefinition, rule?: StrategyRule) {
  if (rule) return ruleActionMeta[rule.action as RuleAction]?.label || '展示';
  if (indicatorParameterKeys(indicator).length) return indicatorParameterScope(indicator);
  const actions = supportedRuleActions(indicator);
  return actions.map((action) => ruleActionMeta[action]?.label || '展示').join(' / ');
}

function conditionLabel(indicator: IndicatorDefinition, rule: StrategyRule | undefined, config: StrategyConfig) {
  if (rule) return ruleSummary(rule, indicator);
  const keys = indicatorParameterKeys(indicator);
  if (!keys.length) return indicator.data_status === 'planned' ? '待接入规则' : '无需参数';
  const values = keys.map((key) => {
    const value = (config as unknown as Record<string, unknown>)[key];
    if (value === null || value === undefined || value === false || value === '') return '未启用';
    if (typeof value === 'number') return `${formatNumber(value, value > 100 ? 0 : 2)}${indicator.unit || ''}`;
    return String(value);
  });
  return values.join(' / ');
}

function weightLabel(rule?: StrategyRule) {
  if (!rule) return '无';
  if (rule.action === 'score') return rule.weight ? `+${rule.weight}` : '加分';
  if (rule.action === 'risk') return rule.weight ? `${rule.weight}` : '扣分';
  return '无';
}

function statusLabel(indicator: IndicatorDefinition) {
  if (indicator.data_status === 'planned' || indicator.status === 'planned') return '待接入';
  if (indicator.data_status === 'display_only') return '仅展示';
  if (indicator.data_status === 'partial') return '缺失较多';
  return '可用';
}

function statusTone(indicator: IndicatorDefinition): 'good' | 'watch' | 'neutral' {
  if (indicator.data_status === 'planned' || indicator.status === 'planned') return 'neutral';
  if (indicator.data_status === 'partial') return 'watch';
  return 'good';
}
