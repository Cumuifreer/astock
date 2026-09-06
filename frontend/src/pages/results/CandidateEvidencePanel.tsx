import type { Candidate } from '../../types';
import { Badge } from '../../design/Badge';
import { formatRatio } from '../../utils/format';

export function CandidateEvidencePanel({ candidate }: { candidate: Candidate | null }) {
  if (!candidate) return null;
  const results = candidate.metrics?.strategy_rule_results;
  const rules = Array.isArray(results) ? results as Array<Record<string, unknown>> : [];
  const risks = rules.filter(rule => rule.missing || (rule.action === 'risk' && rule.matched));
  return <section className="surface pad">
    <div className="section-heading">
      <div><h2>{candidate.name} · 入选依据</h2><p>{candidate.code} · 策略分 {formatRatio(candidate.signal_score)}（用于本次候选排序）</p></div>
      <Badge>规则计算</Badge>
    </div>
    <div className="grid-2 evidence-grid">
      <article className="rule-card evidence-block"><strong>入选理由</strong>
        {(candidate.reasons?.length ? candidate.reasons : ['满足当前策略筛选条件']).map((reason, i) => <p className="card-copy" key={i}>{reason}</p>)}
      </article>
      <article className="rule-card evidence-block"><strong>风险与缺失数据</strong>
        {risks.length ? risks.map((rule, i) => <p className="card-copy" key={i}>{String(rule.indicator_name || rule.indicator_id)}：{String(rule.reason || (rule.missing ? '缺少数据' : '命中风险条件'))}</p>) : <p className="card-copy">本次已启用的规则未记录风险命中或数据缺失。</p>}
      </article>
    </div>
    {rules.length > 0 && <details style={{ marginTop: 16 }}><summary>查看全部规则计算（{rules.length} 项）</summary>
      {rules.map((rule, i) => <p className="card-copy" key={i}>{String(rule.indicator_name || rule.indicator_id)} · {String(rule.value ?? '无数据')} · {rule.matched ? '命中' : '未命中'}{rule.adjustment ? ` · 分值 ${rule.adjustment}` : ''}</p>)}
    </details>}
  </section>;
}
