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
import { Segmented } from '../../design/Segmented';
import { useToast } from '../../design/Toast';
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
  const draftIsSystem = useStrategyDraft((state) => state.isSystem);
  const initialized = useStrategyDraft((state) => state.initialized);
  const setDraft = useStrategyDraft((state) => state.setDraft);
  const setName = useStrategyDraft((state) => state.setName);
  const setRules = useStrategyDraft((state) => state.setRules);
  const setResonances = useStrategyDraft((state) => state.setResonances);
  const patchConfig = useStrategyDraft((state) => state.patchConfig);
  const { showToast } = useToast();
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
  const patchBootstrapStrategies = (updater: (rows: StrategyPreset[]) => StrategyPreset[]) => {
    queryClient.setQueryData(['bootstrap'], (current: unknown) => {
      const record = current as { strategies?: StrategyPreset[] } | undefined;
      if (!record) return current;
      return { ...record, strategies: updater(record.strategies || []) };
    });
  };
  const applyPreset = (preset: StrategyPreset) => {
    setDraft({
      presetId: preset.id,
      name: preset.name,
      config: cloneConfig(preset.config),
      isSystem: Boolean(preset.is_system),
      isDefault: Boolean(preset.is_default),
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
      patchBootstrapStrategies((rows) => {
        const existing = rows.filter((item) => item.id !== result.preset.id);
        return [result.preset, ...existing];
      });
      applyPreset(result.preset);
      invalidate();
      showToast('策略已保存', 'success');
    },
    onError: (error) => showToast(error instanceof Error ? error.message : '策略保存失败', 'danger'),
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
      patchBootstrapStrategies((rows) => [result.preset, ...rows.filter((item) => item.id !== result.preset.id)]);
      applyPreset(result.preset);
      invalidate();
      showToast('策略副本已创建', 'success');
    },
    onError: (error) => showToast(error instanceof Error ? error.message : '策略复制失败', 'danger'),
  });
  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteStrategy(id),
    onSuccess: (_, deletedId) => {
      patchBootstrapStrategies((rows) => rows.filter((item) => item.id !== deletedId));
      createNewDraft();
      invalidate();
      showToast('策略已删除', 'success');
    },
    onError: (error) => showToast(error instanceof Error ? error.message : '策略删除失败', 'danger'),
  });
  const runMutation = useMutation({
    mutationFn: () => runStrategy(namedConfig),
    onSuccess: () => {
      invalidate();
      window.location.hash = '#status';
      showToast('分析任务已开始，可在任务状态查看进度', 'success');
    },
    onError: (error) => showToast(error instanceof Error ? error.message : '分析任务启动失败', 'danger'),
  });
  const handleSave = (saveAs: boolean) => {
    if (!saveAs && draftIsSystem) {
      showToast('系统模板可复制后编辑', 'info');
      return;
    }
    saveMutation.mutate({ saveAs });
  };
  const handleDelete = () => {
    if (!presetId) {
      showToast('当前是未保存草稿，无需删除', 'info');
      return;
    }
    if (draftIsSystem) {
      showToast('系统模板可复制后编辑', 'info');
      return;
    }
    deleteMutation.mutate(presetId);
  };
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
              <Button disabled={saveMutation.isPending} icon={<Save size={16} />} onClick={() => handleSave(false)} variant="secondary">
                保存
              </Button>
              <Button disabled={saveMutation.isPending} icon={<Save size={16} />} onClick={() => handleSave(true)} variant="secondary">
                另存为
              </Button>
              <Button disabled={deleteMutation.isPending} icon={<Trash2 size={16} />} onClick={handleDelete} variant="danger">
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
              { value: 'draft-new', label: '新建未保存策略' },
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
            <label className="parameter-field">
              <span>分析模式</span>
              <Segmented
                value={(namedConfig.analysis_mode === 'score' ? 'score' : 'strict') as 'strict' | 'score'}
                options={[
                  { value: 'strict', label: '严格筛选' },
                  { value: 'score', label: '评分排序' },
                ]}
                onChange={(value) => patchConfig({ analysis_mode: value })}
              />
              <small className="field-readonly muted">
                {namedConfig.analysis_mode === 'score' ? '允许加分和扣分参与排序。' : '硬条件不满足时直接剔除。'}
              </small>
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
