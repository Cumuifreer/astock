import { useMemo, useState } from 'react';
import type { IndicatorDefinition } from '../../types';
import { Badge } from '../../design/Badge';
import { Combobox } from '../../design/Combobox';

type FactorPickerProps = {
  indicators: IndicatorDefinition[];
};

export function FactorPicker({ indicators }: FactorPickerProps) {
  const [query, setQuery] = useState('');
  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return indicators
      .filter((indicator) => {
        if (!normalized) return true;
        return `${indicator.name} ${indicator.id} ${indicator.category_id}`.toLowerCase().includes(normalized);
      })
      .slice(0, 24);
  }, [indicators, query]);

  return (
    <section className="surface pad">
      <div className="section-heading">
        <div>
          <h2>指标搜索</h2>
          <p>仅把真实可执行、合同允许的指标放进规则画布。</p>
        </div>
      </div>
      <Combobox value={query} onChange={setQuery} />
      <div className="list-stack" style={{ marginTop: 14 }}>
        {filtered.map((indicator) => (
          <article className="rule-card" key={indicator.id}>
            <div className="rule-card-header">
              <strong>{indicator.name}</strong>
              <Badge tone={indicator.data_status === 'executable' ? 'good' : 'neutral'}>{indicator.data_status || 'unknown'}</Badge>
            </div>
            <p className="card-copy">{indicator.description || indicator.formula || '暂无说明'}</p>
            <div className="rule-chip-grid">
              {(indicator.supported_actions || []).map((action) => (
                <Badge key={action}>{action}</Badge>
              ))}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
