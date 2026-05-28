import type { StrategyConfig, StrategyRule } from '../../types';
import { Badge } from '../../design/Badge';
import { Progress } from '../../design/Progress';

type StrategySummaryProps = {
  name: string;
  config: StrategyConfig;
  rules: StrategyRule[];
};

export function StrategySummary({ name, config, rules }: StrategySummaryProps) {
  const filters = rules.filter((rule) => rule.action === 'filter').length;
  const scores = rules.filter((rule) => rule.action === 'score').length;
  const risks = rules.filter((rule) => rule.action === 'risk').length;
  const display = rules.filter((rule) => rule.action === 'display').length;
  return (
    <section className="surface pad">
      <div className="section-heading">
        <div>
          <h2>策略摘要</h2>
          <p>{name}</p>
        </div>
        <Badge tone="info">{modeLabel(config.analysis_mode)}</Badge>
      </div>
      <div className="list-stack">
        <SummaryRow label="硬筛" value={filters} />
        <SummaryRow label="加分" value={scores} />
        <SummaryRow label="风险" value={risks} />
        <SummaryRow label="展示列" value={display} />
      </div>
      <div style={{ marginTop: 16 }}>
        <div className="split-row" style={{ marginBottom: 8 }}>
          <span className="metric-label">预计覆盖健康</span>
          <Badge tone={filters ? 'good' : 'watch'}>{filters ? '可运行' : '需补规则'}</Badge>
        </div>
        <Progress value={Math.min(100, Math.max(24, rules.length * 12))} />
      </div>
    </section>
  );
}

function modeLabel(mode?: string | null) {
  if (mode === 'strict') return '严格模式';
  if (mode === 'score') return '评分模式';
  return '综合模式';
}

function SummaryRow({ label, value }: { label: string; value: number }) {
  return (
    <div className="split-row">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
