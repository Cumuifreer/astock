import { useMemo, useState } from 'react';
import type { IndicatorDefinition, StrategyConfig, StrategyRule, StrategyResonance } from '../../types';
import { Badge } from '../../design/Badge';
import { Button } from '../../design/Button';
import { CheckTile } from '../../design/CheckTile';
import { EmptyState } from '../../design/EmptyState';
import { Select } from '../../design/Select';
import { createResonanceId, resonanceBonusOptions, strategyRuleSelectLabel } from '../../utils/strategy';
import { RuleCard } from './RuleCard';
import { Plus, Trash2 } from 'lucide-react';

type RuleCanvasProps = {
  rules: StrategyRule[];
  resonances: StrategyResonance[];
  indicators: Map<string, IndicatorDefinition>;
  config: StrategyConfig;
  focusedParameter?: string | null;
  selectableResonanceRules: StrategyRule[];
  onPatchConfig: (patch: Partial<StrategyConfig>) => void;
  onPatchRule: (ruleId: string, patch: Partial<StrategyRule>) => void;
  onRemoveRule: (ruleId: string) => void;
  onSetResonances: (resonances: StrategyResonance[]) => void;
};

const sections: Array<{ title: string; action?: string; copy: string }> = [
  { title: '硬性筛选', action: 'filter', copy: '必须满足的条件，不满足会直接剔除。' },
  { title: '评分因子', action: 'score', copy: '命中后增加排序分数，缺失字段不会偷加分。' },
  { title: '风险控制', action: 'risk', copy: '用于过热、炸板、筹码压力和异常换手。' },
  { title: '展示字段', action: 'display', copy: '只进入候选表和证据面板，不参与打分。' },
];

const nullableAdvancedNumberKeys = new Set(['volume_ratio_min']);

export function RuleCanvas({
  rules,
  resonances,
  indicators,
  config,
  focusedParameter,
  selectableResonanceRules,
  onPatchConfig,
  onPatchRule,
  onRemoveRule,
  onSetResonances,
}: RuleCanvasProps) {
  const [selectedResonanceRuleIds, setSelectedResonanceRuleIds] = useState<string[]>([]);
  const selectableRuleIds = useMemo(() => new Set(selectableResonanceRules.map((rule) => rule.id)), [selectableResonanceRules]);
  const selectedRuleIds = selectedResonanceRuleIds.filter((id) => selectableRuleIds.has(id));
  const updateResonance = (id: string, patch: Partial<StrategyResonance>) => {
    onSetResonances(resonances.map((item) => (item.id === id ? { ...item, ...patch } : item)));
  };
  const toggleSelectedRule = (ruleId: string) => {
    setSelectedResonanceRuleIds((current) => (current.includes(ruleId) ? current.filter((id) => id !== ruleId) : [...current, ruleId]));
  };
  const addResonance = () => {
    const initialRules = selectedRuleIds
      .map((ruleId) => selectableResonanceRules.find((rule) => rule.id === ruleId))
      .filter((rule): rule is StrategyRule => Boolean(rule));
    if (initialRules.length < 2) return;
    onSetResonances([
      ...resonances,
      {
        id: createResonanceId(),
        name: initialRules.map((rule) => indicators.get(rule.indicator_id)?.name || rule.indicator_id).join(' + '),
        rule_ids: initialRules.map((rule) => rule.id),
        bonus: 8,
        enabled: true,
        source: 'rule_ids',
      },
    ]);
    setSelectedResonanceRuleIds([]);
  };
  const removeResonance = (id: string) => onSetResonances(resonances.filter((item) => item.id !== id));
  const patchNumber = (key: keyof StrategyConfig, rawValue: string) => {
    const value = rawValue.trim() === '' ? (nullableAdvancedNumberKeys.has(String(key)) ? null : 0) : Number(rawValue);
    onPatchConfig({ [key]: value } as Partial<StrategyConfig>);
  };
  const patchBoolean = (key: keyof StrategyConfig, value: boolean) => {
    onPatchConfig({ [key]: value } as Partial<StrategyConfig>);
  };

  return (
    <div className="list-stack">
      <section className="surface pad">
        <div className="section-heading">
          <div>
            <h2>规则配置</h2>
            <p>规则配置会按硬性筛选、评分因子、风险控制和展示字段分组。</p>
          </div>
        </div>
        <div className="grid-2">
          {sections.map((section) => {
            const sectionRules = section.action ? rules.filter((rule) => rule.action === section.action) : [];
            return (
              <div className="rule-section" key={section.title}>
                <div>
                  <h3>{section.title}</h3>
                  <p className="card-copy">{section.copy}</p>
                </div>
                {sectionRules.length ? (
                  sectionRules.map((rule) => (
                    <RuleCard
                      indicator={indicators.get(rule.indicator_id)}
                      key={rule.id}
                      onPatch={(patch) => onPatchRule(rule.id, patch)}
                      onRemove={() => onRemoveRule(rule.id)}
                      rule={rule}
                    />
                  ))
                ) : (
                  <EmptyState title={`${section.title} 暂无规则`} description="从左侧指标库添加真实可执行指标。" />
                )}
              </div>
            );
          })}
        </div>
      </section>

      <section className="surface pad">
        <div className="section-heading">
          <div>
            <h2>组合加分</h2>
            <p>组合加分只引用已有硬性筛选或评分因子，使用固定加分，不重新填写阈值。</p>
          </div>
          <div className="button-row">
            <Badge tone="purple">{selectableResonanceRules.length} 个可引用规则</Badge>
            <Button disabled={selectedRuleIds.length < 2} icon={<Plus size={15} />} onClick={addResonance} variant="secondary">
              新建组合
            </Button>
          </div>
        </div>
        <div className="resonance-chip-grid">
          {selectableResonanceRules.map((rule) => (
            <button
              className={selectedRuleIds.includes(rule.id) ? 'chip-button active' : 'chip-button'}
              key={rule.id}
              type="button"
              onClick={() => toggleSelectedRule(rule.id)}
            >
              {indicators.get(rule.indicator_id)?.name || rule.indicator_id}
            </button>
          ))}
        </div>
        <div className="list-stack" style={{ marginTop: 12 }}>
          {resonances.length ? (
            resonances.map((item) => (
              <article className="rule-card" key={item.id}>
                <div className="rule-card-header">
                  <label className="rule-name-input">
                    <span>组合名称</span>
                    <input value={item.name || ''} onChange={(event) => updateResonance(item.id, { name: event.target.value })} />
                  </label>
                  <CheckTile checked={item.enabled !== false} label="启用" onCheckedChange={(checked) => updateResonance(item.id, { enabled: checked })} />
                </div>
                <div className="rule-editor resonance-editor">
                  {(item.rule_ids || []).map((ruleId, index) => (
                    <label key={`${item.id}-${index}`}>
                      <span>规则 {index + 1}</span>
                      <Select
                        label={`规则 ${index + 1}`}
                        value={ruleId}
                        onChange={(value) => {
                          const next = [...(item.rule_ids || [])];
                          next[index] = value;
                          updateResonance(item.id, { rule_ids: Array.from(new Set(next.filter(Boolean))) });
                        }}
                        options={selectableResonanceRules.map((rule) => ({ value: rule.id, label: strategyRuleSelectLabel(rule, indicators) }))}
                      />
                    </label>
                  ))}
                  <label>
                    <span>加分</span>
                    <Select
                      label="加分"
                      value={String(item.bonus ?? 8)}
                      onChange={(value) => updateResonance(item.id, { bonus: Number(value) })}
                      options={resonanceBonusOptions.map((option) => ({ value: String(option.value), label: option.label }))}
                    />
                  </label>
                </div>
                <div className="button-row">
                  <Button
                    disabled={(item.rule_ids || []).length >= selectableResonanceRules.length}
                    icon={<Plus size={14} />}
                    onClick={() => {
                      const used = new Set(item.rule_ids || []);
                      const nextRule = selectableResonanceRules.find((rule) => !used.has(rule.id));
                      if (nextRule) updateResonance(item.id, { rule_ids: [...(item.rule_ids || []), nextRule.id] });
                    }}
                    variant="ghost"
                  >
                    增加引用
                  </Button>
                  <Button icon={<Trash2 size={14} />} onClick={() => removeResonance(item.id)} variant="ghost">
                    删除组合
                  </Button>
                </div>
              </article>
            ))
          ) : (
            <EmptyState title="暂无组合加分" description="选择已有硬性筛选或评分因子后，可以形成可解释的固定加分。" />
          )}
        </div>
      </section>

      <section className="surface pad">
        <div className="section-heading">
          <div>
            <h2>高级参数</h2>
            <p>平台窗口、EMA、MACD、随机指标等参数可折叠编辑，避免主画布变成参数墙。</p>
          </div>
        </div>
        <details className="advanced-parameters">
          <summary>高级参数</summary>
          <div className="parameter-grid">
            <NumberField
              focused={focusedParameter === 'platform_lookback_days'}
              id="strategy-field-platform_lookback_days"
              label="平台窗口"
              onChange={(value) => patchNumber('platform_lookback_days', value)}
              step="1"
              value={config.platform_lookback_days}
            />
            <NumberField
              focused={focusedParameter === 'platform_max_range'}
              id="strategy-field-platform_max_range"
              label="平台振幅"
              onChange={(value) => patchNumber('platform_max_range', value)}
              step="0.01"
              unit="%"
              value={config.platform_max_range}
            />
            <NumberField
              focused={focusedParameter === 'pullback_tolerance'}
              id="strategy-field-pullback_tolerance"
              label="回踩容忍"
              onChange={(value) => patchNumber('pullback_tolerance', value)}
              step="0.01"
              unit="%"
              value={config.pullback_tolerance}
            />
            <NumberField
              focused={focusedParameter === 'ma_short_window'}
              id="strategy-field-ma_short_window"
              label="短均线"
              onChange={(value) => patchNumber('ma_short_window', value)}
              step="1"
              value={config.ma_short_window}
            />
            <NumberField
              focused={focusedParameter === 'ma_long_window'}
              id="strategy-field-ma_long_window"
              label="长均线"
              onChange={(value) => patchNumber('ma_long_window', value)}
              step="1"
              value={config.ma_long_window}
            />
            <NumberField
              focused={focusedParameter === 'trend_ema_fast_window'}
              id="strategy-field-trend_ema_fast_window"
              label="EMA 快线"
              onChange={(value) => patchNumber('trend_ema_fast_window', value)}
              step="1"
              value={config.trend_ema_fast_window}
            />
            <NumberField
              focused={focusedParameter === 'trend_ema_mid_window'}
              id="strategy-field-trend_ema_mid_window"
              label="EMA 中线"
              onChange={(value) => patchNumber('trend_ema_mid_window', value)}
              step="1"
              value={config.trend_ema_mid_window}
            />
            <NumberField
              focused={focusedParameter === 'trend_ema_long_window'}
              id="strategy-field-trend_ema_long_window"
              label="EMA 长线"
              onChange={(value) => patchNumber('trend_ema_long_window', value)}
              step="1"
              value={config.trend_ema_long_window}
            />
            <NumberField
              focused={focusedParameter === 'trend_macd_fast'}
              id="strategy-field-trend_macd_fast"
              label="MACD 快线"
              onChange={(value) => patchNumber('trend_macd_fast', value)}
              step="1"
              value={config.trend_macd_fast}
            />
            <NumberField
              focused={focusedParameter === 'trend_macd_slow'}
              id="strategy-field-trend_macd_slow"
              label="MACD 慢线"
              onChange={(value) => patchNumber('trend_macd_slow', value)}
              step="1"
              value={config.trend_macd_slow}
            />
            <NumberField
              focused={focusedParameter === 'trend_macd_signal'}
              id="strategy-field-trend_macd_signal"
              label="MACD 信号"
              onChange={(value) => patchNumber('trend_macd_signal', value)}
              step="1"
              value={config.trend_macd_signal}
            />
            <NumberField
              focused={focusedParameter === 'volume_ratio_min'}
              id="strategy-field-volume_ratio_min"
              label="量比门槛"
              onChange={(value) => patchNumber('volume_ratio_min', value)}
              step="0.1"
              value={config.volume_ratio_min}
            />
            <NumberField
              focused={focusedParameter === 'max_amplitude'}
              id="strategy-field-max_amplitude"
              label="最大振幅"
              onChange={(value) => patchNumber('max_amplitude', value)}
              step="0.1"
              unit="%"
              value={config.max_amplitude}
            />
            <div className="parameter-field">
              <span>平台突破收盘确认</span>
              <CheckTile
                checked={Boolean(config.platform_breakout_require_close_above)}
                id="strategy-field-platform_breakout_require_close_above"
                label="启用"
                onCheckedChange={(checked) => patchBoolean('platform_breakout_require_close_above', checked)}
              />
            </div>
          </div>
        </details>
      </section>
    </div>
  );
}

function NumberField({
  focused,
  id,
  label,
  onChange,
  step,
  unit,
  value,
}: {
  focused?: boolean;
  id: string;
  label: string;
  onChange: (value: string) => void;
  step: string;
  unit?: string;
  value: number | null | undefined;
}) {
  return (
    <label className={focused ? 'parameter-field highlight' : 'parameter-field'}>
      <span>{label}</span>
      <div className="input-with-unit">
        <input id={id} step={step} type="number" value={value ?? ''} onChange={(event) => onChange(event.target.value)} />
        {unit ? <em>{unit}</em> : null}
      </div>
    </label>
  );
}
