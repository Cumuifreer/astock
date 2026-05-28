import { useMemo, useState } from 'react';
import { Plus } from 'lucide-react';
import type { IndicatorDefinition } from '../../types';
import { Badge } from '../../design/Badge';
import { Button } from '../../design/Button';
import { Combobox } from '../../design/Combobox';
import { supportedRuleActions } from '../../utils/strategy';

type FactorPickerProps = {
  indicators: IndicatorDefinition[];
  onAddRule: (indicator: IndicatorDefinition) => void;
};

export function FactorPicker({ indicators, onAddRule }: FactorPickerProps) {
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
            <div className="rule-chip-grid" style={{ alignItems: 'center' }}>
              {supportedRuleActions(indicator).map((action) => (
                <Badge key={action}>{action}</Badge>
              ))}
              <Button
                aria-label={`加入 ${indicator.name}`}
                disabled={indicator.data_status === 'planned'}
                icon={<Plus size={14} />}
                onClick={() => onAddRule(indicator)}
                variant="ghost"
              >
                加入规则
              </Button>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
