import { useMemo, useState } from 'react';
import { Plus } from 'lucide-react';
import type { IndicatorDefinition } from '../../types';
import { Badge } from '../../design/Badge';
import { Button } from '../../design/Button';
import { Combobox } from '../../design/Combobox';
import { Segmented } from '../../design/Segmented';
import { indicatorParameterKeys, indicatorParameterScope, ruleActionMeta, supportedRuleActions } from '../../utils/strategy';

type FactorPickerProps = {
  indicators: IndicatorDefinition[];
  onAddRule: (indicator: IndicatorDefinition) => void;
  onEditParameter?: (indicator: IndicatorDefinition) => void;
};

type PickerMode = 'supplement' | 'built-in' | 'all';
const initialVisibleCount = 36;

export function FactorPicker({ indicators, onAddRule, onEditParameter }: FactorPickerProps) {
  const [query, setQuery] = useState('');
  const [mode, setMode] = useState<PickerMode>('supplement');
  const [category, setCategory] = useState('all');
  const [visibleCount, setVisibleCount] = useState(initialVisibleCount);
  const categories = useMemo(() => {
    const pairs = indicators.map((indicator) => [indicator.group_id || indicator.category_id || 'other', indicator.group_label || indicator.category_id || '其它'] as const);
    return [['all', '全部'] as const, ...Array.from(new Map(pairs).entries())];
  }, [indicators]);
  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return indicators
      .filter((indicator) => {
        const builtIn = Boolean(indicator.paired_strategy_ids?.length);
        const searchable = `${indicator.name} ${indicator.id} ${indicator.category_id} ${indicator.group_label} ${indicator.source}`.toLowerCase();
        if (normalized) return searchable.includes(normalized);
        if (mode === 'supplement' && builtIn) return false;
        if (mode === 'built-in' && !builtIn) return false;
        return true;
      })
      .filter((indicator) => normalized || category === 'all' || (indicator.group_id || indicator.category_id || 'other') === category);
  }, [category, indicators, mode, query]);
  const visible = filtered.slice(0, visibleCount);
  const addRule = (indicator: IndicatorDefinition) => {
    if (indicator.paired_strategy_ids?.length) {
      const ok = window.confirm(`${indicator.name} 会与已有参数叠加生效，确认转为显式规则？`);
      if (!ok) return;
    }
    onAddRule(indicator);
  };

  return (
    <section className="surface pad">
      <div className="section-heading">
        <div>
          <h2>指标搜索</h2>
          <p>仅把真实可执行、合同允许的指标放进规则画布。</p>
        </div>
      </div>
      <Segmented
        value={mode}
        onChange={(value) => {
          setMode(value);
          setVisibleCount(initialVisibleCount);
        }}
        options={[
          { value: 'supplement', label: '补充规则' },
          { value: 'built-in', label: '内置参数' },
          { value: 'all', label: '全部指标' },
        ]}
      />
      <Combobox value={query} onChange={setQuery} />
      <div className="rule-chip-grid" style={{ marginTop: 12 }}>
        {categories.map(([value, label]) => (
          <button className={category === value ? 'chip-button active' : 'chip-button'} key={value} type="button" onClick={() => setCategory(value)}>
            {label}
          </button>
        ))}
      </div>
      <p className="card-copy" style={{ marginTop: 10 }}>
        显示 {visible.length} / {filtered.length} 个指标；搜索会覆盖当前分组，直接查全部指标。
      </p>
      <div className="list-stack" style={{ marginTop: 14 }}>
        {visible.map((indicator) => {
          const builtIn = Boolean(indicator.paired_strategy_ids?.length);
          const parameterKeys = indicatorParameterKeys(indicator);
          return (
            <article className="rule-card" key={indicator.id}>
              <div className="rule-card-header">
                <strong>{indicator.name}</strong>
                <Badge tone={indicator.data_status === 'executable' ? 'good' : 'neutral'}>{indicator.data_status || 'unknown'}</Badge>
              </div>
              <p className="card-copy">
                {indicator.group_label || indicator.category_id || '未分类'} · {indicator.source || '本地指标'}
              </p>
              <p className="card-copy">{indicator.description || indicator.formula || '暂无说明'}</p>
              {builtIn ? (
                <p className="card-copy">
                  由 {indicatorParameterScope(indicator)} 参数控制
                  {parameterKeys.length ? ` · ${parameterKeys.join(', ')}` : ''}
                </p>
              ) : null}
              <div className="rule-chip-grid" style={{ alignItems: 'center' }}>
                {supportedRuleActions(indicator).map((action) => (
                  <Badge key={action}>{ruleActionMeta[action]?.label || action}</Badge>
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
                  onClick={() => addRule(indicator)}
                  variant="ghost"
                >
                  {builtIn ? '转为显式规则' : '加入规则'}
                </Button>
              </div>
              {builtIn ? <p className="card-copy">转为显式规则会与已有参数叠加生效。</p> : null}
            </article>
          );
        })}
      </div>
      {visible.length < filtered.length ? (
        <div className="rule-card-actions">
          <Button onClick={() => setVisibleCount((value) => value + initialVisibleCount)} variant="ghost">
            显示更多
          </Button>
        </div>
      ) : null}
    </section>
  );
}
