import { useMemo, useState } from 'react';
import { Plus } from 'lucide-react';
import type { IndicatorDefinition } from '../../types';
import { Badge } from '../../design/Badge';
import { Button } from '../../design/Button';
import { Combobox } from '../../design/Combobox';
import { indicatorParameterKeys, indicatorParameterScope, supportedRuleActions } from '../../utils/strategy';

type FactorPickerProps = {
  indicators: IndicatorDefinition[];
  onAddRule: (indicator: IndicatorDefinition) => void;
  onEditParameter?: (indicator: IndicatorDefinition) => void;
};

export function FactorPicker({ indicators, onAddRule, onEditParameter }: FactorPickerProps) {
  const [query, setQuery] = useState('');
  const [showBuiltIn, setShowBuiltIn] = useState(false);
  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return indicators
      .filter((indicator) => {
        if (!showBuiltIn && indicator.paired_strategy_ids?.length) return false;
        if (!normalized) return true;
        return `${indicator.name} ${indicator.id} ${indicator.category_id}`.toLowerCase().includes(normalized);
      })
      .slice(0, 24);
  }, [indicators, query, showBuiltIn]);

  return (
    <section className="surface pad">
      <div className="section-heading">
        <div>
          <h2>指标搜索</h2>
          <p>仅把真实可执行、合同允许的指标放进规则画布。</p>
        </div>
      </div>
      <label className="factor-toggle">
        <input checked={showBuiltIn} type="checkbox" onChange={(event) => setShowBuiltIn(event.target.checked)} />
        显示内置指标
      </label>
      <Combobox value={query} onChange={setQuery} />
      <div className="list-stack" style={{ marginTop: 14 }}>
        {filtered.map((indicator) => {
          const builtIn = Boolean(indicator.paired_strategy_ids?.length);
          const parameterKeys = indicatorParameterKeys(indicator);
          return (
            <article className="rule-card" key={indicator.id}>
              <div className="rule-card-header">
                <strong>{indicator.name}</strong>
                <Badge tone={indicator.data_status === 'executable' ? 'good' : 'neutral'}>{indicator.data_status || 'unknown'}</Badge>
              </div>
              <p className="card-copy">{indicator.description || indicator.formula || '暂无说明'}</p>
              {builtIn ? (
                <p className="card-copy">
                  由 {indicatorParameterScope(indicator)} 覆盖
                  {parameterKeys.length ? ` · ${parameterKeys.join(', ')}` : ''}
                </p>
              ) : null}
              <div className="rule-chip-grid" style={{ alignItems: 'center' }}>
                {supportedRuleActions(indicator).map((action) => (
                  <Badge key={action}>{action}</Badge>
                ))}
                {builtIn ? <Badge tone="purple">由 {indicatorParameterScope(indicator)} 覆盖</Badge> : null}
                {builtIn ? (
                  <Button
                    aria-label={`编辑 ${indicator.name} 参数`}
                    disabled={!onEditParameter}
                    onClick={() => onEditParameter?.(indicator)}
                    variant="ghost"
                  >
                    编辑参数
                  </Button>
                ) : null}
                <Button
                  aria-label={`${builtIn ? '转为显式规则' : '加入'} ${indicator.name}`}
                  disabled={indicator.data_status === 'planned'}
                  icon={<Plus size={14} />}
                  onClick={() => onAddRule(indicator)}
                  variant="ghost"
                >
                  {builtIn ? '转为显式规则' : '加入规则'}
                </Button>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
