import type { Candidate } from '../../types';
import { Badge } from '../../design/Badge';
import { formatMoney, formatPercent, formatRatio } from '../../utils/format';

type CandidateEvidencePanelProps = {
  candidate: Candidate | null;
};

export function CandidateEvidencePanel({ candidate }: CandidateEvidencePanelProps) {
  if (!candidate) {
    return (
      <section className="surface pad">
        <div className="section-heading">
          <div>
            <h2>候选证据面板</h2>
            <p>选择候选后展示为什么入选、买点质量、风险和可操作动作。</p>
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="surface pad">
      <div className="section-heading">
        <div>
          <h2>{candidate.name} 证据面板</h2>
          <p>
            {candidate.code} · 总分 {formatRatio(candidate.signal_score)}
          </p>
        </div>
        <Badge tone="info">结构化解释</Badge>
      </div>
      <div className="grid-2">
        <EvidenceBlock title="为什么入选" items={candidate.reasons?.length ? candidate.reasons : ['命中策略硬筛', '候选排名进入当前上限', '数据来源可追踪']} />
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
          title="风险"
          items={[
            `换手率 ${formatPercent(candidate.turnover_rate)}`,
            `振幅 ${formatPercent(candidate.amplitude)}`,
            `流通市值 ${formatMoney(candidate.float_market_value)}`,
            '过热、筹码压力和事件风险按策略规则展示',
          ]}
        />
        <EvidenceBlock title="可操作动作" items={['加入观察池', '标记误报', '打开 K 线', '生成回测样本']} />
      </div>
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
