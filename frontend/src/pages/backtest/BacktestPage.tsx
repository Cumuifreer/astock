import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getBacktestRuns } from '../../api/backtest';
import { queryKeys } from '../../api/queryKeys';
import type { StrategyConfig } from '../../types';
import { Badge } from '../../design/Badge';
import { Select } from '../../design/Select';
import { Tabs } from '../../design/Tabs';
import { useBootstrap } from '../../hooks/useBootstrap';
import { useStrategyDraft } from '../../hooks/useStrategyDraft';
import { formatDateTime } from '../../utils/date';
import { composeStrategyConfig } from '../../utils/strategy';
import { SignalEvaluation } from './SignalEvaluation';
import { PortfolioBacktest } from './PortfolioBacktest';

const defaultStrategyKey = ['default', 'strategy'].join('_');
const signalRunStorageKey = 'astock.signalEvaluationRunId';
const portfolioRunStorageKey = 'astock.portfolioBacktestRunId';

export function BacktestPage() {
  const bootstrap = useBootstrap();
  const draft = useStrategyDraft();
  const [selectedStrategyId, setSelectedStrategyId] = useState('draft');
  const [selectedSignalRunId, setSelectedSignalRunId] = useState(() => readStoredRunId(signalRunStorageKey));
  const [selectedPortfolioRunId, setSelectedPortfolioRunId] = useState(() => readStoredRunId(portfolioRunStorageKey));
  const runs = useQuery({ queryKey: queryKeys.backtest.runs(), queryFn: getBacktestRuns });
  const latest = runs.data?.rows?.[0];
  const defaultConfig = (bootstrap.data as Record<string, unknown> | undefined)?.[defaultStrategyKey] as StrategyConfig | undefined;
  const draftConfig = useMemo(
    () => (draft.config ? composeStrategyConfig(draft.config, draft.rules, draft.resonances) : defaultConfig || null),
    [defaultConfig, draft.config, draft.resonances, draft.rules],
  );
  const selectedPreset = bootstrap.data?.strategies?.find((preset) => preset.id === selectedStrategyId);
  const selectedConfig = selectedStrategyId === 'draft' ? draftConfig : selectedPreset?.config || draftConfig;
  const selectedName = selectedStrategyId === 'draft' ? draft.name || '当前策略草稿' : selectedPreset?.name || '未命名策略';
  const strategyOptions = [
    { value: 'draft', label: `${draft.name || '当前策略草稿'} · 当前` },
    ...(bootstrap.data?.strategies || []).map((preset) => ({
      value: preset.id,
      label: preset.name,
    })),
  ];
  useEffect(() => {
    if (!selectedSignalRunId && latest?.id) {
      setSelectedSignalRunId(latest.id);
      persistRunId(signalRunStorageKey, latest.id);
    }
  }, [latest?.id, selectedSignalRunId]);

  const handleSignalRunStarted = (runId: string) => {
    setSelectedSignalRunId(runId);
    persistRunId(signalRunStorageKey, runId);
  };
  const handlePortfolioRunStarted = (runId: string) => {
    setSelectedPortfolioRunId(runId);
    persistRunId(portfolioRunStorageKey, runId);
  };

  return (
    <div className="page-grid">
      <section className="surface pad">
        <div className="section-heading backtest-header-grid">
          <div>
            <h2>回测</h2>
            <p>选择策略和时间范围，评估信号质量与组合表现。</p>
          </div>
          <div className="rule-chip-grid">
            <Badge tone="info">{runs.data?.rows?.length || 0} 次历史运行</Badge>
            {latest ? <Badge>{formatDateTime(latest.started_at)}</Badge> : null}
          </div>
        </div>
        <div className="data-toolbar">
          <span className="subsection-title">回测策略：</span>
          <Select label="回测策略" value={selectedStrategyId} onChange={setSelectedStrategyId} options={strategyOptions} />
          <Badge tone="info">{selectedName}</Badge>
        </div>
        <div className="backtest-tabs">
          <Tabs
            defaultValue="signal"
            items={[
              {
                value: 'signal',
                label: '信号评估',
                content: (
                  <SignalEvaluation
                    config={selectedConfig as StrategyConfig | null}
                    selectedRunId={selectedSignalRunId}
                    strategyName={selectedName}
                    onRunStarted={handleSignalRunStarted}
                  />
                ),
              },
              {
                value: 'portfolio',
                label: '组合回测',
                content: (
                  <PortfolioBacktest
                    config={selectedConfig as StrategyConfig | null}
                    selectedRunId={selectedPortfolioRunId}
                    strategyName={selectedName}
                    onRunStarted={handlePortfolioRunStarted}
                  />
                ),
              },
            ]}
          />
        </div>
      </section>
    </div>
  );
}

function readStoredRunId(key: string) {
  try {
    return window.localStorage.getItem(key) || '';
  } catch {
    return '';
  }
}

function persistRunId(key: string, runId: string) {
  try {
    window.localStorage.setItem(key, runId);
  } catch {
    // localStorage may be disabled; keeping React state is enough for the current session.
  }
}
