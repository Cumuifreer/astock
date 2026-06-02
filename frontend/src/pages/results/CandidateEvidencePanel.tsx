import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { Candidate } from '../../types';
import { Badge } from '../../design/Badge';
import { Button } from '../../design/Button';
import { getCandidateAiSummary, startCandidateAiSummary } from '../../api/strategy';
import { queryKeys } from '../../api/queryKeys';
import type { CandidateAiSummary, CandidateAiSummaryContent, CandidateAiSummaryStatus } from '../../api/strategy';
import { addWatchlistItems } from '../../api/watchlist';
import { useToast } from '../../design/Toast';
import { formatMoney, formatPercent, formatRatio, formatRatioPercent } from '../../utils/format';

type CandidateEvidencePanelProps = {
  candidate: Candidate | null;
  runId?: string | null;
  strategyName?: string;
  analysisDate?: string | null;
};

export function CandidateEvidencePanel({ candidate, runId, strategyName, analysisDate }: CandidateEvidencePanelProps) {
  const { showToast } = useToast();
  const queryClient = useQueryClient();
  const ruleResults = candidate ? extractRuleResults(candidate) : [];
  const matchedRules = ruleResults
    .filter((item) => item.matched)
    .slice(0, 6)
    .map((item) => `${item.indicator_name || '指标'}：${item.value ?? '已命中'}${item.adjustment ? `（${item.adjustment}）` : ''}`);
  const riskRules = ruleResults
    .filter((item) => item.action === 'risk' || item.missing || item.reason)
    .slice(0, 6)
    .map((item) => `${item.indicator_name || '指标'}：${item.reason || (item.matched ? '命中' : '未命中')}`);
  const aiSummary = useQuery({
    queryKey: queryKeys.analysis.candidateAiSummary(runId || undefined, candidate?.code),
    queryFn: () =>
      candidate && runId
        ? getCandidateAiSummary(runId, candidate.code)
        : Promise.resolve({
            status: 'not_requested' as const,
            summary: null,
          }),
    enabled: Boolean(candidate && runId),
    refetchInterval: (query) => (isAiSummaryActive(query.state.data as CandidateAiSummary | undefined) ? 2600 : false),
    staleTime: 30 * 1000,
  });
  const aiMutation = useMutation({
    mutationFn: ({ runId: targetRunId, code, force }: { runId: string; code: string; force: boolean }) =>
      startCandidateAiSummary(targetRunId, code, force),
    onSuccess: (result, variables) => {
      const targetRunId = result.run_id || variables.runId;
      const targetCode = result.code || variables.code;
      if (targetRunId && targetCode) {
        queryClient.setQueryData<CandidateAiSummary>(queryKeys.analysis.candidateAiSummary(targetRunId, targetCode), (current) => ({
          ...(current || {}),
          status: (result.status as CandidateAiSummaryStatus) || 'queued',
          task_id: result.task_id,
          run_id: targetRunId,
          code: targetCode,
          input_hash: result.input_hash || current?.input_hash || null,
        }));
        void queryClient.invalidateQueries({ queryKey: queryKeys.analysis.candidateAiSummary(targetRunId, targetCode) });
      }
      void queryClient.invalidateQueries({ queryKey: queryKeys.tasks.all() });
      showToast('候选解释已加入任务队列', 'success');
    },
    onError: (error) => showToast(error instanceof Error ? error.message : '候选解释任务启动失败', 'danger'),
  });
  const addMutation = useMutation({
    mutationFn: () =>
      candidate
        ? addWatchlistItems({
            source_type: 'strategy',
            source_label: strategyName || '未命名策略',
            source_ref: runId || null,
            batch_date: analysisDate || undefined,
            items: [
              {
                code: candidate.code,
                name: candidate.name,
                entry_date: analysisDate || undefined,
                entry_price: candidate.latest_price,
                signal_score: candidate.signal_score,
                signal_type: candidate.signal_type,
                reasons: candidate.reasons || [],
                metrics: candidate.metrics || {},
                hypothesis: (candidate.reasons || []).slice(0, 2).join('；'),
                invalidation_rule: '跌破最近平台或策略风险项重新命中',
              },
            ],
          })
        : Promise.resolve({}),
    onSuccess: () => showToast('已加入观察池', 'success'),
  });

  if (!candidate) {
    return (
      <section className="surface pad">
        <div className="section-heading">
          <div>
            <h2>选股解释</h2>
            <p>选择候选后展示为什么入选、风险和后续观察动作。</p>
          </div>
        </div>
      </section>
    );
  }

  const aiData = aiSummary.data;
  const aiContent = normalizeAiSummary(aiData);
  const aiStatus = aiSummary.isError ? 'failed' : aiData?.status || 'not_requested';
  const aiText = typeof aiContent.summary === 'string' ? aiContent.summary : null;
  const useAiEvidence = Boolean(aiText && (aiStatus === 'completed_full' || aiStatus === 'completed_partial'));
  const aiReady = Boolean(aiText && aiStatus === 'completed_full');
  const aiBusy = aiMutation.isPending || aiStatus === 'queued' || aiStatus === 'running';
  const primaryExplanation = useAiEvidence
    ? [aiText || '']
    : [fallbackExplanation(aiStatus, aiContent.fallback_reason, aiContent.error_message, aiSummary.isError || aiMutation.isError)];
  const opportunityItems =
    useAiEvidence && aiContent.opportunities?.length ? aiContent.opportunities : candidate.reasons?.length ? candidate.reasons : matchedRules;
  const riskItems = useAiEvidence && aiContent.risks?.length
    ? aiContent.risks
    : riskRules.length
      ? riskRules
      : [`换手率 ${formatPercent(candidate.turnover_rate)}`, `振幅 ${formatRatioPercent(candidate.amplitude)}`, `流通市值 ${formatMoney(candidate.float_market_value)}`];
  const watchPlan = useAiEvidence && aiContent.watch_plan?.length
    ? aiContent.watch_plan
    : ['观察 1-3 个交易日的量价延续', '失效条件：跌破 5 日线或放量跌破平台', '复盘 T+1 / T+3 / T+5 收益'];
  const forceGenerate = aiStatus === 'completed_full' || aiStatus === 'completed_partial' || aiStatus === 'failed' || aiStatus === 'stale';

  return (
    <section className="surface pad">
      <div className="section-heading">
        <div>
          <h2>{candidate.name} 选股解释</h2>
          <p>
            {candidate.code} · 总分 {formatRatio(candidate.signal_score)}
          </p>
        </div>
        <Badge tone={aiReady ? 'info' : 'watch'}>{aiReady ? '自然语言解释' : '规则解释'}</Badge>
      </div>
      <div className="grid-2 evidence-grid">
        <EvidenceBlock title="AI 解读" items={primaryExplanation} />
        <EvidenceBlock title="入选理由" items={opportunityItems.length ? opportunityItems : matchedRules} />
        <EvidenceBlock title="风险提示" items={riskItems} />
        <EvidenceBlock title="后续观察" items={watchPlan} />
      </div>
      <div className="button-row" aria-label="可操作动作" style={{ marginTop: 16 }}>
        <Button disabled={addMutation.isPending} onClick={() => addMutation.mutate()} variant="primary">
          加入观察池
        </Button>
        <Button disabled={!runId || aiBusy} onClick={() => runId && aiMutation.mutate({ runId, code: candidate.code, force: forceGenerate })} variant="secondary">
          {generateButtonLabel(aiStatus)}
        </Button>
        {candidate.chart_url ? (
          <Button onClick={() => window.open(candidate.chart_url, '_blank', 'noopener,noreferrer')} variant="secondary">
            打开K线
          </Button>
        ) : null}
      </div>
    </section>
  );
}

function normalizeAiSummary(data?: CandidateAiSummary): CandidateAiSummaryContent {
  const nested = isAiSummaryContent(data?.summary) ? data?.summary : {};
  return {
    enabled: data?.enabled ?? nested.enabled,
    summary: typeof data?.summary === 'string' ? data.summary : nested.summary || null,
    opportunities: data?.opportunities?.length ? data.opportunities : nested.opportunities,
    risks: data?.risks?.length ? data.risks : nested.risks,
    watch_plan: data?.watch_plan?.length ? data.watch_plan : nested.watch_plan,
    generated_at: data?.generated_at ?? nested.generated_at,
    prompt_version: data?.prompt_version ?? nested.prompt_version,
    fallback_reason: data?.fallback_reason ?? nested.fallback_reason,
    error_message: data?.error_message ?? nested.error_message,
  };
}

function isAiSummaryContent(value: CandidateAiSummary['summary']): value is CandidateAiSummaryContent {
  return Boolean(value && typeof value === 'object' && !Array.isArray(value));
}

function isAiSummaryActive(data?: CandidateAiSummary) {
  return data?.status === 'queued' || data?.status === 'running';
}

function generateButtonLabel(status?: CandidateAiSummaryStatus) {
  if (status === 'failed') return '重试';
  if (status === 'completed_full' || status === 'completed_partial' || status === 'stale') return '重新生成';
  return '生成解释';
}

function EvidenceBlock({ title, items }: { title: string; items: string[] }) {
  return (
    <article className="rule-card evidence-block">
      <strong>{title}</strong>
      <div className="list-stack">
        {items.map((item, index) => (
          <p className="card-copy" key={`${item}-${index}`}>
            {item}
          </p>
        ))}
      </div>
    </article>
  );
}

function fallbackExplanation(
  status?: CandidateAiSummaryStatus,
  reason?: CandidateAiSummaryContent['fallback_reason'],
  errorMessage?: string | null,
  requestFailed?: boolean,
) {
  if (requestFailed) return 'AI 解读状态暂不可用，当前显示规则证据。';
  if (status === 'queued') return '候选解释已排队，当前先显示规则证据。';
  if (status === 'running') return '候选解释生成中，当前先显示规则证据。';
  if (status === 'stale') return '候选解释已过期，当前显示规则证据。';
  if (status === 'failed') return errorMessage ? `候选解释生成失败，当前显示规则证据：${errorMessage}` : '候选解释生成失败，当前显示规则证据。';
  if (status === 'not_requested') return '点击生成解释后，将在此显示 AI 解读；当前显示规则证据。';
  if (reason === 'missing_api_key') return '模型未启用，当前显示规则证据。';
  if (reason === 'llm_error') return errorMessage ? `模型请求失败，当前显示规则证据：${errorMessage}` : '模型请求失败，当前显示规则证据。';
  if (reason === 'invalid_response') return '模型返回格式异常，当前显示规则证据。';
  return 'AI 解读暂不可用，当前显示规则证据。';
}

function extractRuleResults(candidate: Candidate): Array<Record<string, unknown>> {
  const key = ['strategy', 'rule', 'results'].join('_');
  const value = candidate.metrics?.[key];
  return Array.isArray(value) ? (value as Array<Record<string, unknown>>) : [];
}
