import { useEffect, useMemo } from 'react';
import type { IndicatorDefinition, IndicatorLibrary, StrategyConfig, StrategyRule } from '../../types';
import { EmptyState } from '../../design/EmptyState';
import { LoadingState } from '../../design/LoadingState';
import { useBootstrap } from '../../hooks/useBootstrap';
import { useStrategyDraft } from '../../hooks/useStrategyDraft';
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
  const draftName = useStrategyDraft((state) => state.name);
  const draftConfig = useStrategyDraft((state) => state.config);
  const draftRules = useStrategyDraft((state) => state.rules);
  const draftResonances = useStrategyDraft((state) => state.resonances);
  const setDraft = useStrategyDraft((state) => state.setDraft);
  const data = bootstrap.data;
  const library = (data as typeof data & { indicator_library?: IndicatorLibrary })?.indicator_library;

  useEffect(() => {
    if (!data?.default_strategy) return;
    const defaultPreset = data.strategies.find((preset) => preset.is_default) || data.strategies[0];
    setDraft(defaultPreset?.name || '我的 Scanner', defaultPreset?.config || data.default_strategy);
  }, [data, setDraft]);

  const config = draftConfig || data?.default_strategy;
  const rules = draftRules.length ? draftRules : fallbackRules(config);
  const resonances = draftResonances;
  const indicators = useMemo(() => new Map((library?.indicators || []).map((indicator) => [indicator.id, indicator] as const)), [library]);
  const selectableResonanceRules = rules.filter((rule) => rule.action === 'filter' || rule.action === 'score');

  if (bootstrap.isLoading) return <LoadingState label="加载 Scanner 合同" />;
  if (!config) return <EmptyState title="Scanner 暂无默认策略" description="保留旧策略兼容逻辑；当 bootstrap 返回默认策略后会自动进入规则画布。" />;

  return (
    <div className="grid-aside">
      <main className="list-stack">
        <UniversePanel config={config} />
        <RuleCanvas indicators={indicators} resonances={resonances} rules={rules} selectableResonanceRules={selectableResonanceRules} />
      </main>
      <aside className="list-stack">
        <StrategySummary config={config} name={draftName} rules={rules} />
        <FactorPicker indicators={library?.indicators || []} />
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
