import { useMemo, useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { Plus, Trash2 } from 'lucide-react';
import type { IndicatorDefinition, StrategyResonance, StrategyRule } from '../../types';
import { Badge } from '../../design/Badge';
import { Button } from '../../design/Button';
import { CheckTile } from '../../design/CheckTile';
import { EmptyState } from '../../design/EmptyState';
import { Select } from '../../design/Select';
import { createResonanceId, resonanceBonusOptions } from '../../utils/strategy';

type CombinationBonusPanelProps = {
  resonances: StrategyResonance[];
  selectableResonanceRules: StrategyRule[];
  indicators: Map<string, IndicatorDefinition>;
  onSetResonances: (resonances: StrategyResonance[]) => void;
};

export function CombinationBonusPanel({ resonances, selectableResonanceRules, indicators, onSetResonances }: CombinationBonusPanelProps) {
  const [open, setOpen] = useState(false);
  const [selectedRuleIds, setSelectedRuleIds] = useState<string[]>([]);
  const [bonus, setBonus] = useState('8');
  const availableIds = useMemo(() => new Set(selectableResonanceRules.map((rule) => rule.id)), [selectableResonanceRules]);
  const groupedRules = useMemo(() => groupSelectableRules(selectableResonanceRules, indicators), [selectableResonanceRules, indicators]);
  const selected = selectedRuleIds.filter((id) => availableIds.has(id));
  const enabledResonances = resonances.filter((item) => item.source !== 'legacy_unmatched');
  const addCombination = () => {
    if (selected.length < 2) return;
    const selectedRules = selected.map((ruleId) => selectableResonanceRules.find((rule) => rule.id === ruleId)).filter((rule): rule is StrategyRule => Boolean(rule));
    onSetResonances([
      ...resonances,
      {
        id: createResonanceId(),
        name: selectedRules.map((rule) => indicatorName(rule, indicators)).join(' + '),
        rule_ids: selected,
        bonus: Number(bonus),
        enabled: true,
        source: 'rule_ids',
      },
    ]);
    setSelectedRuleIds([]);
    setBonus('8');
    setOpen(false);
  };
  const updateResonance = (id: string, patch: Partial<StrategyResonance>) => {
    onSetResonances(resonances.map((item) => (item.id === id ? { ...item, ...patch } : item)));
  };
  const removeResonance = (id: string) => {
    onSetResonances(resonances.filter((item) => item.id !== id));
  };

  return (
    <section className="surface pad combination-panel">
      <div className="section-heading">
        <div>
          <h2>组合加分</h2>
          <p>从已启用的筛选或加分指标里选择两个以上，命中后给候选额外加分。</p>
        </div>
        <div className="button-row">
          <Badge tone="purple">{selectableResonanceRules.length} 个可选指标</Badge>
          <Button disabled={selectableResonanceRules.length < 2} icon={<Plus size={15} />} onClick={() => setOpen(true)} variant="secondary">
            添加组合加分
          </Button>
        </div>
      </div>
      {enabledResonances.length ? (
        <div className="combination-list">
          {enabledResonances.map((item) => (
            <article className={item.enabled === false ? 'combination-card disabled' : 'combination-card'} key={item.id}>
              <div>
                <strong>{combinationTitle(item, indicators, selectableResonanceRules)}</strong>
                <p className="card-copy">{combinationDetail(item, indicators, selectableResonanceRules)}</p>
              </div>
              <div className="button-row">
                <CheckTile checked={item.enabled !== false} label="启用" onCheckedChange={(checked) => updateResonance(item.id, { enabled: checked })} />
                <Select
                  label="加分"
                  value={String(item.bonus ?? 8)}
                  onChange={(value) => updateResonance(item.id, { bonus: Number(value) })}
                  options={resonanceBonusOptions.map((option) => ({ value: String(option.value), label: option.label }))}
                />
                <Button icon={<Trash2 size={14} />} onClick={() => removeResonance(item.id)} variant="ghost">
                  删除
                </Button>
              </div>
            </article>
          ))}
        </div>
      ) : (
        <EmptyState title="暂无组合加分" description="开启两个以上筛选或加分指标后，可以在这里创建组合。" />
      )}
      <Dialog.Root open={open} onOpenChange={setOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="drawer-overlay" />
          <Dialog.Content className="dialog-content combo-dialog">
            <Dialog.Title>选择组合指标</Dialog.Title>
            <Dialog.Description className="card-copy">只显示当前已启用、且能参与筛选或加分的指标。</Dialog.Description>
            {selectableResonanceRules.length >= 2 ? (
              <>
                <div className="combo-selected-row">
                  {selected.length ? (
                    selected.map((ruleId) => {
                      const rule = selectableResonanceRules.find((item) => item.id === ruleId);
                      return rule ? (
                        <span className="combo-selected-chip" key={rule.id}>
                          {indicatorName(rule, indicators)}
                        </span>
                      ) : null;
                    })
                  ) : (
                    <span className="field-readonly muted">至少选择两个指标</span>
                  )}
                </div>
                <div className="combo-choice-grid">
                  {groupedRules.map(([group, groupRules]) => (
                    <section className="combo-choice-section" key={group}>
                      <strong>{group}</strong>
                      <div className="combo-choice-list">
                        {groupRules.map((rule) => {
                          const active = selectedRuleIds.includes(rule.id);
                          return (
                            <button
                              className={active ? 'combo-choice active' : 'combo-choice'}
                              key={rule.id}
                              type="button"
                              onClick={() => setSelectedRuleIds((current) => (current.includes(rule.id) ? current.filter((id) => id !== rule.id) : [...current, rule.id]))}
                            >
                              <strong>{indicatorName(rule, indicators)}</strong>
                              <span>{rule.action === 'score' ? '加分排序' : '硬性筛选'}</span>
                            </button>
                          );
                        })}
                      </div>
                    </section>
                  ))}
                </div>
              </>
            ) : (
              <EmptyState title="可选指标不足" description="先开启两个硬筛或加分指标，再添加组合加分。" />
            )}
            <div className="split-row combo-dialog-footer">
              <Select label="加分" value={bonus} onChange={setBonus} options={resonanceBonusOptions.map((option) => ({ value: String(option.value), label: option.label }))} />
              <div className="button-row">
                <Dialog.Close asChild>
                  <Button variant="secondary">取消</Button>
                </Dialog.Close>
                <Button disabled={selected.length < 2} onClick={addCombination} variant="primary">
                  {selected.length < 2 ? '至少选择两个指标' : '保存组合'}
                </Button>
              </div>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </section>
  );
}

function indicatorName(rule: StrategyRule, indicators: Map<string, IndicatorDefinition>) {
  return indicators.get(rule.indicator_id)?.name || rule.indicator_id;
}

function groupSelectableRules(rules: StrategyRule[], indicators: Map<string, IndicatorDefinition>): Array<[string, StrategyRule[]]> {
  const groups = new Map<string, StrategyRule[]>();
  rules.forEach((rule) => {
    const indicator = indicators.get(rule.indicator_id);
    const group = indicator?.group_label || indicator?.category_id || '其他指标';
    groups.set(group, [...(groups.get(group) || []), rule]);
  });
  return [...groups.entries()].sort(([left], [right]) => left.localeCompare(right, 'zh-CN'));
}

function combinationTitle(item: StrategyResonance, indicators: Map<string, IndicatorDefinition>, rules: StrategyRule[]) {
  if (item.name) return item.name;
  return combinationNames(item, indicators, rules).join(' + ');
}

function combinationDetail(item: StrategyResonance, indicators: Map<string, IndicatorDefinition>, rules: StrategyRule[]) {
  const names = combinationNames(item, indicators, rules);
  return `${names.join(' + ')}：+${item.bonus ?? 8}`;
}

function combinationNames(item: StrategyResonance, indicators: Map<string, IndicatorDefinition>, rules: StrategyRule[]) {
  const byId = new Map(rules.map((rule) => [rule.id, rule] as const));
  return (item.rule_ids || []).map((ruleId) => {
    const rule = byId.get(ruleId);
    return rule ? indicatorName(rule, indicators) : '已停用指标';
  });
}
