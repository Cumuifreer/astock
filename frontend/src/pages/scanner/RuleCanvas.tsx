import type { IndicatorDefinition, StrategyRule, StrategyResonance } from '../../types';
import { Badge } from '../../design/Badge';
import { Button } from '../../design/Button';
import { EmptyState } from '../../design/EmptyState';
import { createResonanceId, resonanceBonusOptions, strategyRuleSelectLabel } from '../../utils/strategy';
import { RuleCard } from './RuleCard';
import { Plus, Trash2 } from 'lucide-react';

type RuleCanvasProps = {
  rules: StrategyRule[];
  resonances: StrategyResonance[];
  indicators: Map<string, IndicatorDefinition>;
  selectableResonanceRules: StrategyRule[];
  onPatchRule: (ruleId: string, patch: Partial<StrategyRule>) => void;
  onRemoveRule: (ruleId: string) => void;
  onSetResonances: (resonances: StrategyResonance[]) => void;
};

const sections: Array<{ title: string; action?: string; copy: string }> = [
  { title: 'Filters', action: 'filter', copy: '硬筛规则必须有足够覆盖率，缺失处理明确。' },
  { title: 'Scores', action: 'score', copy: '加分规则只在字段命中时生效，不让缺失字段偷加分。' },
  { title: 'Risks', action: 'risk', copy: '风险规则用于过热、炸板、筹码压力和异常换手。' },
  { title: 'Display', action: 'display', copy: '展示列不参与运算，只进入候选表和证据面板。' },
];

export function RuleCanvas({ rules, resonances, indicators, selectableResonanceRules, onPatchRule, onRemoveRule, onSetResonances }: RuleCanvasProps) {
  const updateResonance = (id: string, patch: Partial<StrategyResonance>) => {
    onSetResonances(resonances.map((item) => (item.id === id ? { ...item, ...patch } : item)));
  };
  const addResonance = () => {
    const initialRules = selectableResonanceRules.slice(0, 2);
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
  };
  const removeResonance = (id: string) => onSetResonances(resonances.filter((item) => item.id !== id));

  return (
    <div className="list-stack">
      <section className="surface pad">
        <div className="section-heading">
          <div>
            <h2>Rule Canvas</h2>
            <p>Universe / Filters / Scores / Risks / Display / Resonance / Advanced</p>
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
            <h2>Resonance</h2>
            <p>共振只引用已有 filter/score 规则，固定 bonus，不重新填写阈值。</p>
          </div>
          <div className="button-row">
            <Badge tone="purple">{selectableResonanceRules.length} 个可引用规则</Badge>
            <Button disabled={selectableResonanceRules.length < 2} icon={<Plus size={15} />} onClick={addResonance} variant="secondary">
              新建共振
            </Button>
          </div>
        </div>
        <div className="resonance-chip-grid">
          {selectableResonanceRules.map((rule) => (
            <span className="chip-button active" key={rule.id}>
              {indicators.get(rule.indicator_id)?.name || rule.indicator_id}
            </span>
          ))}
        </div>
        <div className="list-stack" style={{ marginTop: 12 }}>
          {resonances.length ? (
            resonances.map((item) => (
              <article className="rule-card" key={item.id}>
                <div className="rule-card-header">
                  <label className="rule-name-input">
                    <span>共振名称</span>
                    <input value={item.name || ''} onChange={(event) => updateResonance(item.id, { name: event.target.value })} />
                  </label>
                  <label className="mini-toggle">
                    <input checked={item.enabled !== false} type="checkbox" onChange={(event) => updateResonance(item.id, { enabled: event.target.checked })} />
                    启用
                  </label>
                </div>
                <div className="rule-editor resonance-editor">
                  {(item.rule_ids || []).map((ruleId, index) => (
                    <label key={`${item.id}-${index}`}>
                      <span>规则 {index + 1}</span>
                      <select
                        value={ruleId}
                        onChange={(event) => {
                          const next = [...(item.rule_ids || [])];
                          next[index] = event.target.value;
                          updateResonance(item.id, { rule_ids: Array.from(new Set(next.filter(Boolean))) });
                        }}
                      >
                        {selectableResonanceRules.map((rule) => (
                          <option key={rule.id} value={rule.id}>
                            {strategyRuleSelectLabel(rule, indicators)}
                          </option>
                        ))}
                      </select>
                    </label>
                  ))}
                  <label>
                    <span>Bonus</span>
                    <select value={String(item.bonus ?? 8)} onChange={(event) => updateResonance(item.id, { bonus: Number(event.target.value) })}>
                      {resonanceBonusOptions.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
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
                    删除共振
                  </Button>
                </div>
              </article>
            ))
          ) : (
            <EmptyState title="暂无共振规则" description="选择已有硬筛或加分规则后，可以形成可解释的固定加分。" />
          )}
        </div>
      </section>

      <section className="surface pad">
        <div className="section-heading">
          <div>
            <h2>Advanced</h2>
            <p>平台窗口、EMA、MACD、随机指标等内部参数默认折叠，避免主画布变成参数墙。</p>
          </div>
        </div>
        <div className="metric-row">
          <Metric label="平台窗口" value="platform_lookback_days" />
          <Metric label="平台振幅" value="platform_max_range" />
          <Metric label="EMA 周期" value="ma_short / ma_long" />
          <Metric label="回踩容忍" value="pullback_tolerance" />
        </div>
      </section>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric-pill">
      <span className="metric-label">{label}</span>
      <div className="metric-value" style={{ fontSize: 14 }}>
        {value}
      </div>
    </div>
  );
}
