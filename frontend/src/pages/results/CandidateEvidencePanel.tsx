import { useMutation, useQuery } from '@tanstack/react-query';
import type { Candidate } from '../../types';
import { Badge } from '../../design/Badge';
import { Button } from '../../design/Button';
import { getCandidateAiSummary } from '../../api/strategy';
import { addWatchlistItems } from '../../api/watchlist';
import { useToast } from '../../design/Toast';
import { formatMoney, formatPercent, formatRatio } from '../../utils/format';

type CandidateEvidencePanelProps = {
  candidate: Candidate | null;
  runId?: string | null;
  strategyName?: string;
  analysisDate?: string | null;
};

export function CandidateEvidencePanel({ candidate, runId, strategyName, analysisDate }: CandidateEvidencePanelProps) {
  const { showToast } = useToast();
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
    queryKey: ['candidate-ai-summary', runId, candidate?.code],
    queryFn: () =>
      candidate && runId
        ? getCandidateAiSummary(runId, candidate.code, {
            candidate: {
              code: candidate.code,
              name: candidate.name,
              signal_score: candidate.signal_score,
              signal_type: candidate.signal_type,
              latest_price: candidate.latest_price,
              pct_chg: candidate.pct_chg,
              amount: candidate.amount,
              turnover_rate: candidate.turnover_rate,
              float_market_value: candidate.float_market_value,
              reasons: candidate.reasons || [],
              metrics: candidate.metrics || {},
            },
            matched_rules: ruleResults.filter((item) => item.matched),
            risk_items: ruleResults.filter((item) => item.action === 'risk' || item.missing || item.reason),
          })
        : Promise.resolve({
            enabled: false,
            summary: 'AI 解读暂不可用，当前显示规则证据。',
            opportunities: [],
            risks: [],
            watch_plan: [],
            fallback_reason: 'missing_api_key' as const,
            error_message: null,
          }),
    enabled: Boolean(candidate && runId),
    staleTime: 5 * 60 * 1000,
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
  const primaryExplanation = aiSummary.isLoading
    ? ['正在生成候选解释...']
    : [aiData?.summary || fallbackExplanation(aiData?.fallback_reason, aiData?.error_message, aiSummary.isError)];
  const opportunityItems = aiData?.opportunities?.length ? aiData.opportunities : candidate.reasons?.length ? candidate.reasons : matchedRules;
  const riskItems = aiData?.risks?.length
    ? aiData.risks
    : riskRules.length
      ? riskRules
      : [`换手率 ${formatPercent(candidate.turnover_rate)}`, `振幅 ${formatPercent(candidate.amplitude)}`, `流通市值 ${formatMoney(candidate.float_market_value)}`];
  const watchPlan = aiData?.watch_plan?.length
    ? aiData.watch_plan
    : ['观察 1-3 个交易日的量价延续', '失效条件：跌破 5 日线或放量跌破平台', '复盘 T+1 / T+3 / T+5 收益'];

  return (
    <section className="surface pad">
      <div className="section-heading">
        <div>
          <h2>{candidate.name} 选股解释</h2>
          <p>
            {candidate.code} · 总分 {formatRatio(candidate.signal_score)}
          </p>
        </div>
        <Badge tone={aiData?.enabled ? 'info' : 'watch'}>{aiData?.enabled ? '自然语言解释' : '规则解释'}</Badge>
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
        {candidate.chart_url ? (
          <Button onClick={() => window.open(candidate.chart_url, '_blank', 'noopener,noreferrer')} variant="secondary">
            打开K线
          </Button>
        ) : null}
      </div>
    </section>
  );
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

function fallbackExplanation(reason?: string | null, errorMessage?: string | null, requestFailed?: boolean) {
  if (requestFailed) return 'AI 解读暂不可用，当前显示规则证据。';
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
