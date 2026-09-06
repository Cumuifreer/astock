import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { Candidate } from '../../types';
import { getAnalysisReport, getAnalysisReports } from '../../api/strategy';
import { addWatchlistItems, getWatchlistCodes } from '../../api/watchlist';
import { Badge } from '../../design/Badge';
import { Button } from '../../design/Button';
import { EmptyState } from '../../design/EmptyState';
import { LoadingState } from '../../design/LoadingState';
import { Select } from '../../design/Select';
import { useToast } from '../../design/Toast';
import { ReviewDataStatus } from './ReviewDataStatus';
import { formatDateTime } from '../../utils/date';
import { CandidateTable } from './CandidateTable';
import { CandidateEvidencePanel } from './CandidateEvidencePanel';
import { StrictFunnelPanel } from './StrictFunnelPanel';

type SortKey = 'signal_score' | 'rps20' | 'amount' | 'pct_chg' | 'turnover_rate' | 'risk';

export function ResultsPage() {
  const watchlist = useQuery({ queryKey: ['watchlist', 'codes'], queryFn: getWatchlistCodes });
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const reports = useQuery({ queryKey: ['result-reports'], queryFn: getAnalysisReports });
  const flattenedReports = useMemo(
    () => (reports.data?.groups || []).flatMap((group) => group.reports).sort((a, b) => String(b.finished_at || b.started_at).localeCompare(String(a.finished_at || a.started_at))),
    [reports.data],
  );
  const [selectedRunId, setSelectedRunId] = useState<string>('');
  const [manualRunSelection, setManualRunSelection] = useState(false);
  const [selectedCode, setSelectedCode] = useState<string>('');
  const [search, setSearch] = useState('');
  const [sortKey, setSortKey] = useState<SortKey>('signal_score');
  const latestRunId = flattenedReports[0]?.id || '';
  const reportDetail = useQuery({
    queryKey: ['result-report', selectedRunId],
    queryFn: () => getAnalysisReport(selectedRunId),
    enabled: Boolean(selectedRunId),
  });
  const activeCandidates = useMemo(() => reportDetail.data?.candidates?.rows || [], [reportDetail.data]);
  const activeReport = reportDetail.data?.analysis || flattenedReports.find(report => report.id === selectedRunId) || null;
  const activeFunnel = reportDetail.data?.candidates?.funnel || [];
  const activeReportDate = reportDateValue(activeReport);
  const activeStrategyName = strategyLabel(activeReport?.summary, activeReport?.config);
  const observedCodes = useMemo(() => new Set(watchlist.data?.codes || []), [watchlist.data]);
  const filteredCandidates = useMemo(() => {
    const term = search.trim().toLowerCase();
    return [...activeCandidates]
      .filter((candidate) => !term || candidate.code.toLowerCase().includes(term) || candidate.name.toLowerCase().includes(term))
      .sort((left, right) => candidateSortValue(right, sortKey) - candidateSortValue(left, sortKey));
  }, [activeCandidates, search, sortKey]);
  const selectedCandidate = filteredCandidates.find(candidate => candidate.code === selectedCode) || filteredCandidates[0] || null;
  const selectedInWatchlist = Boolean(selectedCandidate && observedCodes.has(selectedCandidate.code));
  const addSelectedMutation = useMutation({
    mutationFn: () =>
      selectedCandidate
        ? addWatchlistItems({
            source_type: 'strategy',
            source_label: activeStrategyName || '未命名策略',
            source_ref: activeReport?.id || selectedRunId || null,
            batch_date: activeReportDate || undefined,
            items: [
              {
                code: selectedCandidate.code,
                name: selectedCandidate.name,
                entry_date: activeReportDate || undefined,
                entry_price: selectedCandidate.latest_price,
                signal_score: selectedCandidate.signal_score,
                signal_type: selectedCandidate.signal_type,
                chart_url: selectedCandidate.chart_url,
                reasons: selectedCandidate.reasons || [],
                metrics: selectedCandidate.metrics || {},
                hypothesis: (selectedCandidate.reasons || []).slice(0, 2).join('；') || '策略候选进入观察池',
                invalidation_rule: '跌破最近平台或策略风险项重新命中',
              },
            ],
          })
        : Promise.resolve({}),
    onSuccess: () => {
      showToast('已加入观察池', 'success');
      void queryClient.invalidateQueries({ queryKey: ['watchlist'] });
    },
    onError: (error) => showToast(error instanceof Error ? error.message : '加入观察池失败', 'danger'),
  });

  useEffect(() => {
    if (!latestRunId || manualRunSelection) return;
    setSelectedRunId(latestRunId);
  }, [latestRunId, manualRunSelection]);

  useEffect(() => {
    setSelectedCode('');
  }, [selectedRunId]);

  if (reports.isLoading) return <LoadingState label="读取候选结果" />;

  const reportOptions = flattenedReports.length
    ? flattenedReports.map((report) => ({
        value: report.id,
        label: reportLabel(report),
      }))
    : latestRunId
      ? [{ value: latestRunId, label: '最近一次分析结果' }]
      : [{ value: 'none', label: '暂无历史报告' }];
  return (
    <div className="page-grid">
      <ReviewDataStatus />
      {reports.isError && <p role="alert">报告列表读取失败：{reports.error.message}</p>}
      <section className="surface pad">
        <div className="section-heading">
          <div>
            <h2>分析结果</h2>
            <p>保留每次分析历史，候选列表和证据面板会随当前报告切换。</p>
          </div>
          <div className="rule-chip-grid">
            <Badge tone="info">{filteredCandidates.length} 个候选</Badge>
            <Badge>{flattenedReports.length} 份报告</Badge>
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
          <Metric label="行情交易日" value={activeReportDate || '旧报告未记录'} />
          <Metric label="运行时间" value={activeReport ? formatDateTime(activeReport.finished_at || activeReport.started_at) : '暂无'} />
          <Metric label="候选数量" value={String(activeCandidates.length)} />
          <Metric label="策略" value={activeStrategyName} />
        </div>
        <div className="button-row" aria-label="候选操作" style={{ margin: '14px 0' }}>
          {selectedCandidate ? (
            <span className="selected-candidate-pill" aria-live="polite">
              当前：{selectedCandidate.code} · {selectedCandidate.name}
            </span>
          ) : null}
          <Button
            disabled={!selectedCandidate?.chart_url}
            onClick={() => selectedCandidate?.chart_url && window.open(selectedCandidate.chart_url, '_blank', 'noopener,noreferrer')}
            variant="secondary"
          >
            打开K线
          </Button>
          <Button disabled={addSelectedMutation.isPending || !selectedCandidate || selectedInWatchlist} onClick={() => addSelectedMutation.mutate()} variant="primary">
            {selectedInWatchlist ? '已在观察池' : '加入观察池'}
          </Button>
        </div>
        {reportDetail.isError ? <p role="alert">报告读取失败：{reportDetail.error.message}</p> : reportDetail.isLoading ? (
          <LoadingState label="读取历史报告" />
        ) : (
          <>
            <StrictFunnelPanel funnel={activeFunnel} analysisMode={activeReport?.config?.analysis_mode} />
            {filteredCandidates.length ? (
              <CandidateTable candidates={filteredCandidates} observedCodes={observedCodes} selectedCode={selectedCandidate?.code} onSelect={candidate => setSelectedCode(candidate.code)} />
            ) : (
              <EmptyState title="暂无候选" description={reportDetail.data?.candidates?.zero_reason || "运行策略后，这里会展示候选表和结构化证据。"} />
            )}
          </>
        )}
      </section>
      <CandidateEvidencePanel candidate={selectedCandidate} />
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

function reportDateValue(report?: { summary?: Record<string, unknown> } | null): string | null {
  return report?.summary?.trade_date ? String(report.summary.trade_date) : null;
}

function strategyLabel(summary: unknown, config: unknown): string {
  const summaryRecord = summary && typeof summary === 'object' ? (summary as Record<string, unknown>) : {};
  const configRecord = config && typeof config === 'object' ? (config as Record<string, unknown>) : {};
  return String(summaryRecord.strategy_name || configRecord.strategy_name || configRecord.name || configRecord.preset_name || '未命名策略');
}

function candidateSortValue(candidate: Candidate, sortKey: SortKey): number {
  if (sortKey === 'risk') {
    const flags = Array.isArray(candidate.metrics?.risk_flags) ? candidate.metrics.risk_flags.length : 0;
    return Number(candidate.metrics?.risk_score || flags || 0);
  }
  return Number(candidate[sortKey] || 0);
}
