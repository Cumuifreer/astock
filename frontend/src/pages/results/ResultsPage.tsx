import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import type { Candidate, StrategyConfig } from '../../types';
import { getAnalysisReport, getAnalysisReports, runStrategy } from '../../api/strategy';
import { addWatchlistItems } from '../../api/watchlist';
import { Badge } from '../../design/Badge';
import { Button } from '../../design/Button';
import { EmptyState } from '../../design/EmptyState';
import { LoadingState } from '../../design/LoadingState';
import { Select } from '../../design/Select';
import { useToast } from '../../design/Toast';
import { useBootstrap } from '../../hooks/useBootstrap';
import { formatDateTime, todayISO } from '../../utils/date';
import { formatMoney, formatPercent, formatRatio } from '../../utils/format';
import { CandidateTable } from './CandidateTable';
import { CandidateEvidencePanel } from './CandidateEvidencePanel';

type SortKey = 'signal_score' | 'rps20' | 'amount' | 'pct_chg' | 'turnover_rate' | 'risk';
const defaultStrategyKey = ['default', 'strategy'].join('_');
const latestRunKey = ['run', 'id'].join('_');

export function ResultsPage() {
  const bootstrap = useBootstrap();
  const { showToast } = useToast();
  const reports = useQuery({ queryKey: ['result-reports'], queryFn: getAnalysisReports });
  const flattenedReports = useMemo(
    () => (reports.data?.groups || []).flatMap((group) => group.reports),
    [reports.data],
  );
  const [selectedRunId, setSelectedRunId] = useState<string>('');
  const [manualRunSelection, setManualRunSelection] = useState(false);
  const [selected, setSelected] = useState<Candidate | null>(null);
  const [search, setSearch] = useState('');
  const [sortKey, setSortKey] = useState<SortKey>('signal_score');
  const latestRunId = flattenedReports[0]?.id || getLatestRunId(bootstrap.data?.candidates) || '';
  const reportDetail = useQuery({
    queryKey: ['result-report', selectedRunId],
    queryFn: () => getAnalysisReport(selectedRunId),
    enabled: Boolean(selectedRunId),
  });
  const selectedIsLatest = Boolean(selectedRunId && selectedRunId === latestRunId);
  const bootstrapCandidateRows = getLatestRunId(bootstrap.data?.candidates) === selectedRunId ? bootstrap.data?.candidates?.rows : undefined;
  const bootstrapLatestReport = bootstrap.data?.latest_analysis?.id === selectedRunId ? bootstrap.data.latest_analysis : null;
  const activeCandidates = reportDetail.data?.candidates?.rows || (selectedIsLatest ? bootstrapCandidateRows : []) || [];
  const activeReport = reportDetail.data?.analysis || (selectedIsLatest ? bootstrapLatestReport : null) || flattenedReports.find((report) => report.id === selectedRunId) || null;
  const activeReportDate = reportDateValue(activeReport);
  const observedCodes = useMemo(
    () => new Set((bootstrap.data?.watchlist?.batches || []).flatMap((batch) => batch.items.map((item) => item.code))),
    [bootstrap.data],
  );
  const filteredCandidates = useMemo(() => {
    const term = search.trim().toLowerCase();
    return [...activeCandidates]
      .filter((candidate) => !term || candidate.code.toLowerCase().includes(term) || candidate.name.toLowerCase().includes(term))
      .sort((left, right) => candidateSortValue(right, sortKey) - candidateSortValue(left, sortKey));
  }, [activeCandidates, search, sortKey]);
  const rerunMutation = useMutation({
    mutationFn: () => {
      const config = activeReport?.config || ((bootstrap.data as Record<string, unknown> | undefined)?.[defaultStrategyKey] as unknown);
      return config ? runStrategy(withStrategyName(config as StrategyConfig, activeStrategyName)) : Promise.resolve(null);
    },
    onSuccess: (result) => {
      if (!result) return;
      window.location.hash = '#status';
      showToast('分析任务已开始，可在任务状态查看进度', 'success');
    },
    onError: (error) => showToast(error instanceof Error ? error.message : '分析任务启动失败', 'danger'),
  });
  const batchAddMutation = useMutation({
    mutationFn: () =>
      addWatchlistItems({
        source_type: 'strategy',
        source_label: activeStrategyName || '未命名策略',
        source_ref: activeReport?.id || selectedRunId || null,
        batch_date: activeReportDate || undefined,
        items: filteredCandidates.slice(0, 50).map((candidate) => ({
          code: candidate.code,
          name: candidate.name,
          entry_date: activeReportDate || undefined,
          entry_price: candidate.latest_price,
          signal_score: candidate.signal_score,
          signal_type: candidate.signal_type,
          chart_url: candidate.chart_url,
          reasons: candidate.reasons || [],
          metrics: candidate.metrics || {},
          hypothesis: (candidate.reasons || []).slice(0, 2).join('；') || '策略候选进入观察池',
          invalidation_rule: '跌破最近平台或策略风险项重新命中',
        })),
      }),
  });

  useEffect(() => {
    if (!latestRunId || manualRunSelection) return;
    setSelectedRunId(latestRunId);
  }, [latestRunId, manualRunSelection]);

  useEffect(() => {
    setSelected(filteredCandidates[0] || null);
  }, [selectedRunId, filteredCandidates]);

  if (bootstrap.isLoading) return <LoadingState label="读取候选结果" />;

  const reportOptions = flattenedReports.length
    ? flattenedReports.map((report) => ({
        value: report.id,
        label: reportLabel(report),
      }))
    : latestRunId
      ? [{ value: latestRunId, label: '最近一次分析结果' }]
      : [{ value: 'none', label: '暂无历史报告' }];
  const activeStrategyName = strategyLabel(activeReport?.summary, activeReport?.config);

  return (
    <div className="page-grid">
      <section className="surface pad">
        <div className="section-heading">
          <div>
            <h2>分析结果</h2>
            <p>保留每次分析历史，候选列表和证据面板会随当前报告切换。</p>
          </div>
          <div className="rule-chip-grid">
            <Badge tone="info">{filteredCandidates.length} 个候选</Badge>
            <Badge>{reports.data?.groups?.length || 0} 组报告</Badge>
          </div>
        </div>
        <div className="data-toolbar">
          <Select
            label="当前报告"
            value={selectedRunId || reportOptions[0].value}
            onChange={(value) => {
              if (value === 'none') return;
              setManualRunSelection(value !== latestRunId);
              setSelectedRunId(value);
            }}
            options={reportOptions}
          />
          <label className="search-box">
            <input placeholder="搜索代码 / 名称" value={search} onChange={(event) => setSearch(event.target.value)} />
          </label>
          <Select
            label="排序"
            value={sortKey}
            onChange={(value) => setSortKey(value as SortKey)}
            options={[
              { value: 'signal_score', label: '总分' },
              { value: 'rps20', label: 'RPS' },
              { value: 'amount', label: '成交额' },
              { value: 'pct_chg', label: '涨跌幅' },
              { value: 'turnover_rate', label: '换手率' },
              { value: 'risk', label: '风险分' },
            ]}
          />
        </div>
        <div className="grid-4">
          <Metric label="当前报告" value={activeReport ? `${formatDateTime(activeReport.finished_at || activeReport.started_at)} · ${activeStrategyName}` : '暂无'} />
          <Metric label="运行时间" value={activeReport ? formatDateTime(activeReport.finished_at || activeReport.started_at) : '暂无'} />
          <Metric label="候选数量" value={String(activeCandidates.length)} />
          <Metric label="策略" value={activeStrategyName} />
        </div>
        <div className="button-row" style={{ margin: '14px 0' }}>
          <Button disabled={rerunMutation.isPending || !activeReport} onClick={() => rerunMutation.mutate()} variant="secondary">
            重新运行
          </Button>
          <Button disabled={!filteredCandidates.length} onClick={() => exportCandidates(filteredCandidates)} variant="secondary">
            导出
          </Button>
          <Button disabled={batchAddMutation.isPending || !filteredCandidates.length} onClick={() => batchAddMutation.mutate()} variant="primary">
            加入观察池
          </Button>
        </div>
        {reportDetail.isLoading ? (
          <LoadingState label="读取历史报告" />
        ) : filteredCandidates.length ? (
          <CandidateTable candidates={filteredCandidates} observedCodes={observedCodes} onSelect={setSelected} />
        ) : (
          <EmptyState title="暂无候选" description="运行策略后，这里会展示候选表和结构化证据。" />
        )}
      </section>
      <CandidateEvidencePanel candidate={selected || filteredCandidates[0] || null} runId={selectedRunId || latestRunId} strategyName={activeStrategyName} analysisDate={activeReportDate} />
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <article className="metric-pill">
      <span className="metric-label">{label}</span>
      <div className="metric-value">{value || '暂无'}</div>
    </article>
  );
}

function reportLabel(report: { started_at?: string; finished_at?: string | null; summary?: Record<string, unknown>; config?: unknown }) {
  return `${formatDateTime(report.finished_at || report.started_at)} · ${strategyLabel(report.summary, report.config)} · ${report.summary?.candidate_count ?? 0} 个候选`;
}

function reportDateValue(report?: { started_at?: string; finished_at?: string | null } | null): string | null {
  const value = report?.finished_at || report?.started_at;
  return value ? String(value).slice(0, 10) : null;
}

function strategyLabel(summary: unknown, config: unknown): string {
  const summaryRecord = summary && typeof summary === 'object' ? (summary as Record<string, unknown>) : {};
  const configRecord = config && typeof config === 'object' ? (config as Record<string, unknown>) : {};
  return String(summaryRecord.strategy_name || configRecord.strategy_name || configRecord.name || configRecord.preset_name || '未命名策略');
}

function withStrategyName(config: StrategyConfig, strategy_name: string): StrategyConfig {
  return {
    ...config,
    strategy_name,
    name: strategy_name,
    preset_name: strategy_name,
  };
}

function candidateSortValue(candidate: Candidate, sortKey: SortKey): number {
  if (sortKey === 'risk') {
    const flags = Array.isArray(candidate.metrics?.risk_flags) ? candidate.metrics.risk_flags.length : 0;
    return Number(candidate.metrics?.risk_score || flags || 0);
  }
  return Number(candidate[sortKey] || 0);
}

function exportCandidates(candidates: Candidate[]) {
  const rows = candidates.map((candidate) => ({
    code: candidate.code,
    name: candidate.name,
    signal_score: formatRatio(candidate.signal_score),
    rps20: formatRatio(candidate.rps20),
    amount: formatMoney(candidate.amount),
    pct_chg: formatPercent(candidate.pct_chg),
    turnover_rate: formatPercent(candidate.turnover_rate),
    reasons: candidate.reasons?.join('；') || '',
  }));
  const blob = new Blob([JSON.stringify(rows, null, 2)], { type: 'application/json;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = `candidates-${todayISO()}.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}

function getLatestRunId(bundle: unknown) {
  return String((bundle as Record<string, unknown> | undefined)?.[latestRunKey] || '');
}
