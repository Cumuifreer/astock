import type { IndicatorDefinition, StrategyRule, StrategyResonance } from '../../types';
import { Badge } from '../../design/Badge';
import { EmptyState } from '../../design/EmptyState';
import { RuleCard } from './RuleCard';

type RuleCanvasProps = {
  rules: StrategyRule[];
  resonances: StrategyResonance[];
  indicators: Map<string, IndicatorDefinition>;
  selectableResonanceRules: StrategyRule[];
};

const sections: Array<{ title: string; action?: string; copy: string }> = [
  { title: 'Filters', action: 'filter', copy: '硬筛规则必须有足够覆盖率，缺失处理明确。' },
  { title: 'Scores', action: 'score', copy: '加分规则只在字段命中时生效，不让缺失字段偷加分。' },
  { title: 'Risks', action: 'risk', copy: '风险规则用于过热、炸板、筹码压力和异常换手。' },
  { title: 'Display', action: 'display', copy: '展示列不参与运算，只进入候选表和证据面板。' },
];

export function RuleCanvas({ rules, resonances, indicators, selectableResonanceRules }: RuleCanvasProps) {
  return (
    <div className="list-stack">
      <section className="surface pad">
        <div className="section-heading">
          <div>
            <h2>Rule Canvas</h2>
            <p>Universe / Filters / Scores / Risks / Display / Resonance / Advanced</p>
          </div>
        </div>
        <div className="grid-2">
          {sections.map((section) => {
            const sectionRules = section.action ? rules.filter((rule) => rule.action === section.action) : [];
            return (
              <div className="rule-section" key={section.title}>
                <div>
                  <h3>{section.title}</h3>
                  <p className="card-copy">{section.copy}</p>
                </div>
                {sectionRules.length ? (
                  sectionRules.map((rule) => <RuleCard indicator={indicators.get(rule.indicator_id)} key={rule.id} rule={rule} />)
                ) : (
                  <EmptyState title={`${section.title} 暂无规则`} description="从左侧指标库添加真实可执行指标。" />
                )}
              </div>
            );
          })}
        </div>
      </section>

      <section className="surface pad">
        <div className="section-heading">
          <div>
            <h2>Resonance</h2>
            <p>共振只引用已有 filter/score 规则，固定 bonus，不重新填写阈值。</p>
          </div>
          <Badge tone="purple">{selectableResonanceRules.length} 个可引用规则</Badge>
        </div>
        <div className="resonance-chip-grid">
          {selectableResonanceRules.map((rule) => (
            <span className="chip-button active" key={rule.id}>
              {indicators.get(rule.indicator_id)?.name || rule.indicator_id}
            </span>
          ))}
        </div>
        <div className="list-stack" style={{ marginTop: 12 }}>
          {resonances.length ? (
            resonances.map((item) => (
              <article className="rule-card" key={item.id}>
                <strong>{item.name}</strong>
                <p className="card-copy">
                  {item.rule_ids.length} 条规则共振，bonus +{item.bonus}，上限由策略合同控制。
                </p>
              </article>
            ))
          ) : (
            <EmptyState title="暂无共振规则" description="选择已有硬筛或加分规则后，可以形成可解释的固定加分。" />
          )}
        </div>
      </section>

      <section className="surface pad">
        <div className="section-heading">
          <div>
            <h2>Advanced</h2>
            <p>平台窗口、EMA、MACD、随机指标等内部参数默认折叠，避免主画布变成参数墙。</p>
          </div>
        </div>
        <div className="metric-row">
          <Metric label="平台窗口" value="platform_lookback_days" />
          <Metric label="平台振幅" value="platform_max_range" />
          <Metric label="EMA 周期" value="ma_short / ma_long" />
          <Metric label="回踩容忍" value="pullback_tolerance" />
        </div>
      </section>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric-pill">
      <span className="metric-label">{label}</span>
      <div className="metric-value" style={{ fontSize: 14 }}>
        {value}
      </div>
    </div>
  );
}
