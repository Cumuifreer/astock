import type { Candidate } from '../../types';
import { useMutation } from '@tanstack/react-query';
import { Badge } from '../../design/Badge';
import { Button } from '../../design/Button';
import { addWatchlistItems } from '../../api/watchlist';
import { formatMoney, formatPercent, formatRatio } from '../../utils/format';

type CandidateEvidencePanelProps = {
  candidate: Candidate | null;
};

export function CandidateEvidencePanel({ candidate }: CandidateEvidencePanelProps) {
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

  const ruleResults = Array.isArray(candidate.metrics?.strategy_rule_results) ? (candidate.metrics.strategy_rule_results as Array<Record<string, unknown>>) : [];
  const matchedRules = ruleResults
    .filter((item) => item.matched)
    .slice(0, 6)
    .map((item) => `${item.indicator_name || item.indicator_id}: ${item.value ?? '未记录'}${item.adjustment ? ` (${item.adjustment})` : ''}`);
  const riskRules = ruleResults
    .filter((item) => item.action === 'risk' || item.missing || item.reason)
    .slice(0, 6)
    .map((item) => `${item.indicator_name || item.indicator_id}: ${item.reason || (item.matched ? '命中' : '未命中')}`);
  const sources = Object.entries(candidate.data_sources || {})
    .filter(([, value]) => value)
    .slice(0, 8)
    .map(([key, value]) => `${key}: ${value}`);

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
        <Button onClick={() => window.alert('AI 解读入口已保留：会基于结构化指标、命中规则、风险项、市场状态和板块热力生成摘要。')} variant="secondary">
          AI 解读
        </Button>
      </div>
      <details className="developer-details">
        <summary>开发者详情</summary>
        <div className="grid-2" style={{ marginTop: 12 }}>
          <EvidenceBlock title="数据来源" items={sources.length ? sources : ['暂无结构化来源']} />
          <EvidenceBlock title="规则明细" items={matchedRules.length ? matchedRules : ['这次分析缺少规则明细，可重新运行策略生成完整解释']} />
        </div>
      </details>
    </section>
  );
}

function EvidenceBlock({ title, items }: { title: string; items: string[] }) {
  return (
    <article className="rule-card">
      <strong>{title}</strong>
      <div className="list-stack">
        {items.map((item) => (
          <p className="card-copy" key={item}>
            {item}
          </p>
        ))}
      </div>
    </article>
  );
}
