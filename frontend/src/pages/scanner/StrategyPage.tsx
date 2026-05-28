import { useEffect, useMemo } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Copy, Play, PlusCircle, Save, Trash2 } from 'lucide-react';
import type { IndicatorDefinition, IndicatorLibrary, StrategyConfig, StrategyPreset, StrategyRule } from '../../types';
import { deleteStrategy, runStrategy, saveStrategy } from '../../api/strategy';
import { Badge } from '../../design/Badge';
import { Button } from '../../design/Button';
import { EmptyState } from '../../design/EmptyState';
import { LoadingState } from '../../design/LoadingState';
import { Select } from '../../design/Select';
import { useBootstrap } from '../../hooks/useBootstrap';
import { useStrategyDraft } from '../../hooks/useStrategyDraft';
import { composeStrategyConfig, defaultStrategyRule } from '../../utils/strategy';
import { IndicatorMatrix } from './IndicatorMatrix';
import { CombinationBonusPanel } from './CombinationBonusPanel';

const defaultStrategyKey = ['default', 'strategy'].join('_');

export function StrategyPage() {
  const bootstrap = useBootstrap();
  const queryClient = useQueryClient();
  const presetId = useStrategyDraft((state) => state.presetId);
  const draftName = useStrategyDraft((state) => state.name);
  const draftConfig = useStrategyDraft((state) => state.config);
  const draftRules = useStrategyDraft((state) => state.rules);
  const draftResonances = useStrategyDraft((state) => state.resonances);
  const initialized = useStrategyDraft((state) => state.initialized);
  const setDraft = useStrategyDraft((state) => state.setDraft);
  const setName = useStrategyDraft((state) => state.setName);
  const setRules = useStrategyDraft((state) => state.setRules);
  const setResonances = useStrategyDraft((state) => state.setResonances);
  const patchConfig = useStrategyDraft((state) => state.patchConfig);
  const data = bootstrap.data;
  const library = (data as typeof data & { indicator_library?: IndicatorLibrary })?.indicator_library;
  const strategies = data?.strategies || [];
  const defaultConfig = (data as Record<string, unknown> | undefined)?.[defaultStrategyKey] as StrategyConfig | undefined;

  useEffect(() => {
    if (!defaultConfig || initialized) return;
    setDraft({
      presetId: null,
      name: nextUnnamedName(strategies),
      config: cloneConfig(defaultConfig),
      isSystem: false,
      isDefault: false,
    });
  }, [defaultConfig, initialized, setDraft, strategies]);

  const config = draftConfig || defaultConfig;
  const rules = initialized ? draftRules : fallbackRules(config);
  const resonances = draftResonances;
  const indicators = useMemo(() => new Map((library?.indicators || []).map((indicator) => [indicator.id, indicator] as const)), [library]);
  const matrixIndicators = useMemo(
    () => [...(library?.indicators || [])].sort((left, right) => `${left.group_label}${left.name}`.localeCompare(`${right.group_label}${right.name}`, 'zh-CN')),
    [library],
  );
  const selectableResonanceRules = rules.filter((rule) => rule.enabled && (rule.action === 'filter' || rule.action === 'score'));
  const currentConfig = useMemo(() => composeStrategyConfig(config, rules, resonances), [config, rules, resonances]);
  const strategyName = draftName.trim() || nextUnnamedName(strategies);
  const namedConfig = useMemo(
    () => ({
      ...currentConfig,
      strategy_name: strategyName,
      name: strategyName,
      preset_name: strategyName,
    }),
    [currentConfig, strategyName],
  );
  const invalidate = () => {
    void queryClient.invalidateQueries();
  };
  const applyPreset = (preset: StrategyPreset) => {
    setDraft({
      presetId: preset.id,
      name: preset.name,
      config: cloneConfig(preset.config),
      isSystem: false,
      isDefault: false,
    });
  };
  const createNewDraft = () => {
    if (!defaultConfig) return;
    setDraft({
      presetId: null,
      name: nextUnnamedName(strategies),
      config: cloneConfig(defaultConfig),
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
    mutationFn: ({ saveAs }: { saveAs: boolean }) =>
      saveStrategy({
        id: !saveAs ? presetId || undefined : undefined,
        name: strategyName,
        config: namedConfig,
      }),
    onSuccess: (result) => {
      applyPreset(result.preset);
      invalidate();
    },
  });
  const duplicateMutation = useMutation({
    mutationFn: () => {
      const duplicateName = `${strategyName} 副本`;
      return saveStrategy({
        name: duplicateName,
        config: {
          ...namedConfig,
          strategy_name: duplicateName,
          name: duplicateName,
          preset_name: duplicateName,
        },
      });
    },
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
    mutationFn: () => runStrategy(namedConfig),
    onSuccess: invalidate,
  });
  const patchRule = (ruleId: string, patch: Partial<StrategyRule>) => {
    setRules(rules.map((rule) => (rule.id === ruleId ? { ...rule, ...patch } : rule)));
  };
  const addRule = (indicator: IndicatorDefinition) => {
    setRules([...rules, defaultStrategyRule(indicator)]);
  };

  if (bootstrap.isLoading) return <LoadingState label="加载策略能力" />;
  if (!config) return <EmptyState title="策略选股暂不可用" description="策略基础配置加载后会自动进入配置界面。" />;

  return (
    <div className="list-stack scanner-workspace-full">
      <main className="list-stack">
        <section className="surface pad scanner-runbar">
          <div className="section-heading">
            <div>
              <h2>当前策略</h2>
              <p>选择、命名、保存并运行你的选股方法。</p>
              <div className="rule-chip-grid" style={{ marginTop: 8 }}>
                <Badge tone={presetId ? 'info' : 'neutral'}>{presetId ? '已保存策略' : '未保存策略'}</Badge>
                <Badge tone="good">可编辑</Badge>
              </div>
            </div>
            <div className="button-row">
              <Button disabled={!defaultConfig} icon={<PlusCircle size={16} />} onClick={createNewDraft} variant="secondary">
                新建
              </Button>
              <Button disabled={duplicateMutation.isPending} icon={<Copy size={16} />} onClick={() => duplicateMutation.mutate()} variant="secondary">
                复制
              </Button>
              <Button disabled={saveMutation.isPending} icon={<Save size={16} />} onClick={() => saveMutation.mutate({ saveAs: false })} variant="secondary">
                保存
              </Button>
              <Button disabled={saveMutation.isPending} icon={<Save size={16} />} onClick={() => saveMutation.mutate({ saveAs: true })} variant="secondary">
                另存为
              </Button>
              <Button disabled={deleteMutation.isPending || !presetId} icon={<Trash2 size={16} />} onClick={() => deleteMutation.mutate()} variant="danger">
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
                label: preset.name,
              })),
            ]}
          />
          <div className="strategy-identity-grid">
            <label className="parameter-field">
              <span>策略名称</span>
              <input className="strategy-name-input" value={draftName} onChange={(event) => setName(event.target.value)} />
            </label>
          </div>
        </section>
        <IndicatorMatrix
          config={namedConfig}
          indicators={matrixIndicators}
          onAddRule={addRule}
          onPatchConfig={patchConfig}
          onPatchRule={patchRule}
          rules={rules}
        />
        <CombinationBonusPanel
          indicators={indicators}
          onSetResonances={setResonances}
          resonances={resonances}
          selectableResonanceRules={selectableResonanceRules}
        />
      </main>
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

function nextUnnamedName(strategies: StrategyPreset[]) {
  const names = new Set(strategies.map((strategy) => strategy.name));
  for (let index = 1; index < 999; index += 1) {
    const name = `未命名策略${index}`;
    if (!names.has(name)) return name;
  }
  return `未命名策略${strategies.length + 1}`;
}
