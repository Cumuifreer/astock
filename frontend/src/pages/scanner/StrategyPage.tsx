import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Copy, Play, PlusCircle, Save, Star, Trash2 } from 'lucide-react';
import type { IndicatorDefinition, IndicatorLibrary, StrategyConfig, StrategyPreset, StrategyRule } from '../../types';
import { deleteStrategy, duplicateStrategy, runStrategy, saveStrategy } from '../../api/strategy';
import { Badge } from '../../design/Badge';
import { Button } from '../../design/Button';
import { EmptyState } from '../../design/EmptyState';
import { LoadingState } from '../../design/LoadingState';
import { Select } from '../../design/Select';
import { useBootstrap } from '../../hooks/useBootstrap';
import { useStrategyDraft } from '../../hooks/useStrategyDraft';
import { composeStrategyConfig, defaultStrategyRule, indicatorParameterKeys, usableRuleIndicators } from '../../utils/strategy';
import { UniversePanel } from './UniversePanel';
import { RuleCanvas } from './RuleCanvas';
import { FactorPicker } from './FactorPicker';
import { StrategySummary } from './StrategySummary';

const scannerSections = [
  'Universe',
  'Filters',
  'Scores',
  'Risks',
  'Display',
  'Resonance',
  'Advanced',
];

const resonanceChipGridClass = 'resonance-chip-grid';

export function StrategyPage() {
  const bootstrap = useBootstrap();
  const queryClient = useQueryClient();
  const presetId = useStrategyDraft((state) => state.presetId);
  const draftName = useStrategyDraft((state) => state.name);
  const draftConfig = useStrategyDraft((state) => state.config);
  const draftRules = useStrategyDraft((state) => state.rules);
  const draftResonances = useStrategyDraft((state) => state.resonances);
  const isSystem = useStrategyDraft((state) => state.isSystem);
  const isDefault = useStrategyDraft((state) => state.isDefault);
  const initialized = useStrategyDraft((state) => state.initialized);
  const setDraft = useStrategyDraft((state) => state.setDraft);
  const setName = useStrategyDraft((state) => state.setName);
  const setRules = useStrategyDraft((state) => state.setRules);
  const setResonances = useStrategyDraft((state) => state.setResonances);
  const patchConfig = useStrategyDraft((state) => state.patchConfig);
  const [focusedParameter, setFocusedParameter] = useState<string | null>(null);
  const data = bootstrap.data;
  const library = (data as typeof data & { indicator_library?: IndicatorLibrary })?.indicator_library;
  const strategies = data?.strategies || [];

  useEffect(() => {
    if (!data?.default_strategy || initialized) return;
    setDraft({
      presetId: null,
      name: '未命名策略',
      config: cloneConfig(data.default_strategy),
      isSystem: false,
      isDefault: false,
    });
  }, [data, initialized, setDraft]);

  const config = draftConfig || data?.default_strategy;
  const rules = initialized ? draftRules : fallbackRules(config);
  const resonances = draftResonances;
  const indicators = useMemo(() => new Map((library?.indicators || []).map((indicator) => [indicator.id, indicator] as const)), [library]);
  const usableIndicators = useMemo(() => usableRuleIndicators(library, { includePaired: true }), [library]);
  const selectableResonanceRules = rules.filter((rule) => rule.action === 'filter' || rule.action === 'score');
  const currentConfig = useMemo(() => composeStrategyConfig(config, rules, resonances), [config, rules, resonances]);
  const invalidate = () => {
    void queryClient.invalidateQueries();
  };
  const applyPreset = (preset: StrategyPreset) => {
    setDraft({
      presetId: preset.id,
      name: preset.name,
      config: cloneConfig(preset.config),
      isSystem: preset.is_system,
      isDefault: preset.is_default,
    });
  };
  const createNewDraft = () => {
    if (!data?.default_strategy) return;
    setDraft({
      presetId: null,
      name: '未命名策略',
      config: cloneConfig(data.default_strategy),
      isSystem: false,
      isDefault: false,
    });
  };
  const selectPreset = (value: string) => {
    if (value === 'draft-new') {
      createNewDraft();
      return;
    }
    const preset = strategies.find((item) => item.id === value);
    if (preset) applyPreset(preset);
  };
  const saveMutation = useMutation({
    mutationFn: ({ setDefault, saveAs }: { setDefault: boolean; saveAs: boolean }) =>
      saveStrategy({
        id: !saveAs && !isSystem ? presetId || undefined : undefined,
        name: draftName || '未命名策略',
        config: currentConfig,
        set_default: setDefault,
      }),
    onSuccess: (result) => {
      applyPreset(result.preset);
      invalidate();
    },
  });
  const duplicateMutation = useMutation({
    mutationFn: () =>
      presetId && isSystem
        ? duplicateStrategy(presetId)
        : saveStrategy({
            name: `${draftName || '未命名策略'} 副本`,
            config: currentConfig,
          }),
    onSuccess: (result) => {
      applyPreset(result.preset);
      invalidate();
    },
  });
  const deleteMutation = useMutation({
    mutationFn: () => deleteStrategy(presetId || ''),
    onSuccess: () => {
      createNewDraft();
      invalidate();
    },
  });
  const runMutation = useMutation({
    mutationFn: () => runStrategy(currentConfig),
    onSuccess: invalidate,
  });
  const patchRule = (ruleId: string, patch: Partial<StrategyRule>) => {
    setRules(rules.map((rule) => (rule.id === ruleId ? { ...rule, ...patch } : rule)));
  };
  const removeRule = (ruleId: string) => {
    setRules(rules.filter((rule) => rule.id !== ruleId));
    setResonances(resonances.map((item) => ({ ...item, rule_ids: (item.rule_ids || []).filter((id) => id !== ruleId) })));
  };
  const addRule = (indicator: IndicatorDefinition) => {
    setRules([...rules, defaultStrategyRule(indicator)]);
  };
  const focusIndicatorParameter = (indicator: IndicatorDefinition) => {
    const key = indicatorParameterKeys(indicator)[0];
    if (!key) return;
    setFocusedParameter(key);
    window.setTimeout(() => {
      document.getElementById(`strategy-field-${key}`)?.focus();
    }, 0);
  };

  if (bootstrap.isLoading) return <LoadingState label="加载 Scanner 合同" />;
  if (!config) return <EmptyState title="Scanner 暂无默认策略" description="保留旧策略兼容逻辑；当 bootstrap 返回默认策略后会自动进入规则画布。" />;

  return (
    <div className="grid-aside">
      <main className="list-stack">
        <section className="surface pad scanner-runbar">
          <div className="section-heading">
            <div>
              <h2>当前 Scanner</h2>
              <p>选择预设、复制为自定义策略，或保存当前画布 draft 后运行。</p>
              <div className="rule-chip-grid" style={{ marginTop: 8 }}>
                <Badge tone={presetId ? 'info' : 'neutral'}>{presetId || 'new-draft'}</Badge>
                {isSystem ? <Badge tone="watch">系统策略只能复制</Badge> : <Badge tone="good">自定义可保存</Badge>}
                {isDefault ? <Badge tone="purple">默认策略</Badge> : null}
              </div>
            </div>
            <div className="button-row">
              <Button disabled={!data?.default_strategy} icon={<PlusCircle size={16} />} onClick={createNewDraft} variant="secondary">
                新建
              </Button>
              <Button disabled={duplicateMutation.isPending} icon={<Copy size={16} />} onClick={() => duplicateMutation.mutate()} variant="secondary">
                复制
              </Button>
              <Button disabled={saveMutation.isPending || isSystem} icon={<Save size={16} />} onClick={() => saveMutation.mutate({ setDefault: false, saveAs: false })} variant="secondary">
                保存策略
              </Button>
              <Button disabled={saveMutation.isPending} icon={<Save size={16} />} onClick={() => saveMutation.mutate({ setDefault: false, saveAs: true })} variant="secondary">
                另存为
              </Button>
              <Button disabled={saveMutation.isPending} icon={<Star size={16} />} onClick={() => saveMutation.mutate({ setDefault: true, saveAs: isSystem })} variant="secondary">
                保存为默认
              </Button>
              <Button disabled={deleteMutation.isPending || isSystem || !presetId} icon={<Trash2 size={16} />} onClick={() => deleteMutation.mutate()} variant="danger">
                删除
              </Button>
              <Button disabled={runMutation.isPending} icon={<Play size={16} />} onClick={() => runMutation.mutate()} variant="primary">
                运行当前策略
              </Button>
            </div>
          </div>
          <Select
            label="当前策略"
            value={presetId || 'draft-new'}
            onChange={selectPreset}
            options={[
              { value: 'draft-new', label: '未命名策略' },
              ...strategies.map((preset) => ({
                value: preset.id,
                label: `${preset.name}${preset.is_system ? ' · 系统' : ''}${preset.is_default ? ' · 默认' : ''}`,
              })),
            ]}
          />
          <input className="strategy-name-input" value={draftName} onChange={(event) => setName(event.target.value)} />
        </section>
        <UniversePanel config={currentConfig} focusedParameter={focusedParameter} onPatchConfig={patchConfig} />
        <RuleCanvas
          config={currentConfig}
          focusedParameter={focusedParameter}
          indicators={indicators}
          onPatchConfig={patchConfig}
          onPatchRule={patchRule}
          onRemoveRule={removeRule}
          onSetResonances={setResonances}
          resonances={resonances}
          rules={rules}
          selectableResonanceRules={selectableResonanceRules}
        />
      </main>
      <aside className="list-stack">
        <StrategySummary config={currentConfig} name={draftName} rules={rules} />
        <FactorPicker indicators={usableIndicators} onAddRule={addRule} onEditParameter={focusIndicatorParameter} />
        <section className="surface pad">
          <div className="section-heading">
            <div>
              <h2>画布分区</h2>
              <p>这些分区对应策略合同，不创建后端不会执行的假规则。</p>
            </div>
          </div>
          <div className={`rule-chip-grid ${resonanceChipGridClass}`}>
            {scannerSections.map((section) => (
              <span className="chip-button active" key={section}>
                {section}
              </span>
            ))}
          </div>
        </section>
      </aside>
    </div>
  );
}

function cloneConfig(config: StrategyConfig): StrategyConfig {
  return JSON.parse(JSON.stringify(config)) as StrategyConfig;
}

function fallbackRules(config: StrategyConfig | null | undefined): StrategyRule[] {
  if (!config?.strategy_rules?.length) return [];
  return config.strategy_rules;
}

export function groupRulesByAction(rules: StrategyRule[]): Record<string, StrategyRule[]> {
  return rules.reduce<Record<string, StrategyRule[]>>((acc, rule) => {
    acc[rule.action] = [...(acc[rule.action] || []), rule];
    return acc;
  }, {});
}

export function executableIndicators(library?: IndicatorLibrary): IndicatorDefinition[] {
  return (library?.indicators || []).filter((indicator) => indicator.data_status === 'executable');
}
