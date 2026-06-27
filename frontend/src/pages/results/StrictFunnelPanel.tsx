import type { FunnelStep } from '../../types';

type StrictFunnelPanelProps = {
  funnel?: FunnelStep[];
  analysisMode?: string | null;
};

export function StrictFunnelPanel({ funnel = [], analysisMode }: StrictFunnelPanelProps) {
  if (analysisMode !== 'strict') return null;

  const rows = funnel.filter((step) => Number(step.removed_count) > 0 && step.step_name !== '候选数量');
  if (!rows.length) return null;

  const totalRemoved = rows.reduce((total, step) => total + Number(step.removed_count || 0), 0);
  const remaining = rows[rows.length - 1]?.after_count ?? 0;
  const largestRemoved = Math.max(...rows.map((step) => Number(step.removed_count || 0)));

  return (
    <section className="strict-funnel-panel" aria-label="严格筛选漏斗">
      <div className="strict-funnel-heading">
        <div>
          <h3>严格筛选漏斗</h3>
          <p>按策略执行顺序展示每个硬性条件减少了多少候选。</p>
        </div>
        <div className="strict-funnel-summary">
          <span>减少 {totalRemoved}</span>
          <strong>剩余 {remaining}</strong>
        </div>
      </div>
      <div className="strict-funnel-table">
        <div className="strict-funnel-head">
          <span>筛选项</span>
          <span>筛选前</span>
          <span>筛选后</span>
          <span>减少</span>
        </div>
        {rows.map((step) => {
          const removed = Number(step.removed_count || 0);
          return (
            <div className={`strict-funnel-row ${removed === largestRemoved ? 'bottleneck' : ''}`.trim()} key={`${step.step_name}-${step.before_count}-${step.after_count}`}>
              <div className="strict-funnel-name">
                <strong>{step.step_name}</strong>
                {step.note ? <span>{step.note}</span> : null}
              </div>
              <span>{step.before_count}</span>
              <span>{step.after_count}</span>
              <em>-{removed}</em>
            </div>
          );
        })}
      </div>
    </section>
  );
}
