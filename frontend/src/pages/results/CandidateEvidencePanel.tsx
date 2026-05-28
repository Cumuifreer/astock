import { useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { useMutation } from '@tanstack/react-query';
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
};

export function CandidateEvidencePanel({ candidate, runId }: CandidateEvidencePanelProps) {
  const { showToast } = useToast();
  const [aiOpen, setAiOpen] = useState(false);
  const addMutation = useMutation({
    mutationFn: () =>
      candidate
        ? addWatchlistItems({
            source_type: 'strategy',
            source_label: '策略选股候选',
            source_ref: candidate.code,
            items: [
              {
                code: candidate.code,
                name: candidate.name,
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
  const aiMutation = useMutation({
    mutationFn: () =>
      candidate && runId
        ? getCandidateAiSummary(runId, candidate.code, {
            candidate: {
              code: candidate.code,
              name: candidate.name,
              signal_score: candidate.signal_score,
              reasons: candidate.reasons || [],
              metrics: candidate.metrics || {},
            },
            matched_rules: extractRuleResults(candidate).filter((item) => item.matched),
            risk_items: extractRuleResults(candidate).filter((item) => item.action === 'risk' || item.missing || item.reason),
          })
        : Promise.resolve({
            enabled: false,
            summary: 'AI 解读暂未启用',
            opportunities: [],
            risks: ['请先选择一份历史报告，再生成候选解读。'],
            watch_plan: [],
          }),
  });
  if (!candidate) {
    return (
      <section className="surface pad">
        <div className="section-heading">
          <div>
            <h2>选股解释</h2>
            <p>选择候选后展示为什么入选、买点质量、风险和可操作动作。</p>
          </div>
        </div>
      </section>
    );
  }

  const ruleResults = extractRuleResults(candidate);
  const matchedRules = ruleResults
    .filter((item) => item.matched)
    .slice(0, 6)
    .map((item) => `${item.indicator_name || '指标'}：${item.value ?? '未记录'}${item.adjustment ? `（${item.adjustment}）` : ''}`);
  const riskRules = ruleResults
    .filter((item) => item.action === 'risk' || item.missing || item.reason)
    .slice(0, 6)
    .map((item) => `${item.indicator_name || '指标'}：${item.reason || (item.matched ? '命中' : '未命中')}`);
  const sourceCoverage = Object.entries(candidate.data_sources || {})
    .filter(([, value]) => value)
    .slice(0, 8)
    .map(([key]) => userDataLabel(key));

  return (
    <section className="surface pad">
      <div className="section-heading">
        <div>
          <h2>{candidate.name} 选股解释</h2>
          <p>
            {candidate.code} · 总分 {formatRatio(candidate.signal_score)}
          </p>
        </div>
        <Badge tone="info">结构化解释</Badge>
      </div>
      <div className="grid-2">
        <EvidenceBlock title="为什么入选" items={candidate.reasons?.length ? candidate.reasons : matchedRules} />
        <EvidenceBlock
          title="买点质量"
          items={[
            `涨跌幅 ${formatPercent(candidate.pct_chg)}`,
            `量比 ${formatRatio(candidate.metrics?.volume_ratio)}`,
            `成交额 ${formatMoney(candidate.amount)}`,
            `RPS20 ${formatRatio(candidate.rps20)}`,
          ]}
        />
        <EvidenceBlock
          title="风险提示"
          items={(riskRules.length ? riskRules : [
            `换手率 ${formatPercent(candidate.turnover_rate)}`,
            `振幅 ${formatPercent(candidate.amplitude)}`,
            `流通市值 ${formatMoney(candidate.float_market_value)}`,
          ])}
        />
        <EvidenceBlock
          title="后续观察"
          items={[
            '建议观察 3 个交易日',
            '失效条件：跌破 5 日线或放量跌破平台',
            '复盘指标：T+1 / T+3 / T+5 收益',
          ]}
        />
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
        <Button
          disabled={aiMutation.isPending || !candidate}
          onClick={() => {
            setAiOpen(true);
            aiMutation.mutate();
          }}
          variant="secondary"
        >
          AI 解读
        </Button>
      </div>
      <details className="maintenance-details">
        <summary>查看技术明细</summary>
        <div className="grid-2" style={{ marginTop: 12 }}>
          <EvidenceBlock title="数据覆盖" items={sourceCoverage.length ? sourceCoverage : ['暂无结构化覆盖信息']} />
          <EvidenceBlock title="规则明细" items={matchedRules.length ? matchedRules : ['这次分析缺少规则明细，可重新运行策略生成完整解释']} />
        </div>
      </details>
      <AiSummaryDialog open={aiOpen} busy={aiMutation.isPending} data={aiMutation.data} onOpenChange={setAiOpen} />
    </section>
  );
}

function EvidenceBlock({ title, items }: { title: string; items: string[] }) {
  return (
    <article className="rule-card">
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

function AiSummaryDialog({
  open,
  busy,
  data,
  onOpenChange,
}: {
  open: boolean;
  busy: boolean;
  data?: { enabled?: boolean; summary: string; opportunities?: string[]; risks?: string[]; watch_plan?: string[]; generated_at?: string | null };
  onOpenChange: (open: boolean) => void;
}) {
  const disabled = data?.enabled === false;
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="drawer-overlay" />
        <Dialog.Content className="dialog-content">
          <Dialog.Title>{disabled ? 'AI 解读暂未启用' : 'AI 解读'}</Dialog.Title>
          {busy ? (
            <p className="card-copy">正在生成候选解读...</p>
          ) : disabled ? (
            <p className="card-copy">{data?.summary || '请在系统配置中填写模型密钥。'}</p>
          ) : data ? (
            <div className="list-stack">
              <p className="card-copy">{data.summary}</p>
              <EvidenceBlock title="机会" items={data.opportunities?.length ? data.opportunities : ['暂无额外机会提示']} />
              <EvidenceBlock title="风险" items={data.risks?.length ? data.risks : ['暂无额外风险提示']} />
              <EvidenceBlock title="观察计划" items={data.watch_plan?.length ? data.watch_plan : ['等待后续走势确认']} />
            </div>
          ) : (
            <p className="card-copy">请重新点击候选解读。</p>
          )}
          <div className="dialog-actions">
            <Dialog.Close asChild>
              <Button variant="secondary">关闭</Button>
            </Dialog.Close>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function extractRuleResults(candidate: Candidate): Array<Record<string, unknown>> {
  const key = ['strategy', 'rule', 'results'].join('_');
  const value = candidate.metrics?.[key];
  return Array.isArray(value) ? (value as Array<Record<string, unknown>>) : [];
}

function userDataLabel(key: string) {
  if (key.includes('money')) return '资金流向';
  if (key.includes('factor')) return '技术指标';
  if (key.includes('concept') || key.includes('sector')) return '题材板块';
  if (key.includes('limit')) return '涨跌停事件';
  if (key.includes('daily')) return '每日交易指标';
  return '基础行情';
}
