import type { StrategyConfig } from '../../types';
import { Badge } from '../../design/Badge';
import { CheckTile } from '../../design/CheckTile';
import { Select } from '../../design/Select';

type UniversePanelProps = {
  config: StrategyConfig;
  focusedParameter?: string | null;
  onPatchConfig: (patch: Partial<StrategyConfig>) => void;
};

const sortOptions = [
  { value: 'signal_score', label: '综合分' },
  { value: 'rps20', label: 'RPS20' },
  { value: 'amount', label: '成交额' },
  { value: 'turnover_rate', label: '换手率' },
  { value: 'pct_chg', label: '涨跌幅' },
];

export function UniversePanel({ config, focusedParameter, onPatchConfig }: UniversePanelProps) {
  const patchNumber = (key: keyof StrategyConfig, rawValue: string, nullable = true) => {
    const value = rawValue.trim() === '' ? (nullable ? null : 0) : Number(rawValue);
    onPatchConfig({ [key]: value } as Partial<StrategyConfig>);
  };
  const patchBoolean = (key: keyof StrategyConfig, value: boolean) => {
    onPatchConfig({ [key]: value } as Partial<StrategyConfig>);
  };
  const patchString = (key: keyof StrategyConfig, value: string) => {
    onPatchConfig({ [key]: value } as Partial<StrategyConfig>);
  };

  return (
    <section className="surface pad">
      <div className="section-heading">
        <div>
          <h2>股票池</h2>
          <p>交易范围、活跃口径、市值、成交额和排序口径都可以直接调整。</p>
        </div>
        <Badge tone="info">{config.include_bj ? '含北交所' : '沪深为主'}</Badge>
      </div>
      <div className="parameter-grid universe-parameter-grid">
        <NumberField
          focused={focusedParameter === 'min_price'}
          id="strategy-field-min_price"
          label="最低价格"
          min={0}
          onChange={(value) => patchNumber('min_price', value, false)}
          step="0.01"
          unit="元"
          value={config.min_price}
        />
        <NumberField
          focused={focusedParameter === 'min_amount'}
          id="strategy-field-min_amount"
          label="成交额门槛"
          min={0}
          onChange={(value) => patchNumber('min_amount', value, false)}
          step="1000000"
          unit="元"
          value={config.min_amount}
        />
        <NumberField
          focused={focusedParameter === 'min_float_market_value'}
          id="strategy-field-min_float_market_value"
          label="最小流通市值"
          min={0}
          onChange={(value) => patchNumber('min_float_market_value', value)}
          step="100000000"
          unit="元"
          value={config.min_float_market_value}
        />
        <NumberField
          focused={focusedParameter === 'max_float_market_value'}
          id="strategy-field-max_float_market_value"
          label="最大流通市值"
          min={0}
          onChange={(value) => patchNumber('max_float_market_value', value)}
          step="100000000"
          unit="元"
          value={config.max_float_market_value}
        />
        <NumberField
          focused={focusedParameter === 'min_turnover'}
          id="strategy-field-min_turnover"
          label="最小换手"
          min={0}
          onChange={(value) => patchNumber('min_turnover', value)}
          step="0.1"
          unit="%"
          value={config.min_turnover}
        />
        <NumberField
          focused={focusedParameter === 'max_turnover'}
          id="strategy-field-max_turnover"
          label="最大换手"
          min={0}
          onChange={(value) => patchNumber('max_turnover', value)}
          step="0.1"
          unit="%"
          value={config.max_turnover}
        />
        <NumberField
          focused={focusedParameter === 'min_rps20'}
          id="strategy-field-min_rps20"
          label="RPS20 门槛"
          min={0}
          onChange={(value) => patchNumber('min_rps20', value)}
          step="1"
          unit="分"
          value={config.min_rps20}
        />
        <NumberField
          focused={focusedParameter === 'min_rps60'}
          id="strategy-field-min_rps60"
          label="RPS60 门槛"
          min={0}
          onChange={(value) => patchNumber('min_rps60', value)}
          step="1"
          unit="分"
          value={config.min_rps60}
        />
        <NumberField
          focused={focusedParameter === 'min_rps120'}
          id="strategy-field-min_rps120"
          label="RPS120 门槛"
          min={0}
          onChange={(value) => patchNumber('min_rps120', value)}
          step="1"
          unit="分"
          value={config.min_rps120}
        />
        <NumberField
          focused={focusedParameter === 'candidate_limit'}
          id="strategy-field-candidate_limit"
          label="候选上限"
          min={1}
          onChange={(value) => patchNumber('candidate_limit', value, false)}
          step="1"
          value={config.candidate_limit}
        />
        <label className={fieldClass(focusedParameter === 'sort_by')}>
          <span>排序字段</span>
          <Select
            label="排序字段"
            value={config.sort_by || 'signal_score'}
            onChange={(value) => patchString('sort_by', value)}
            options={sortOptions}
          />
        </label>
        <div className="parameter-field toggle-stack">
          <CheckTile checked={Boolean(config.include_bj)} id="strategy-field-include_bj" label="包含北交所" onCheckedChange={(checked) => patchBoolean('include_bj', checked)} />
          <CheckTile
            checked={Boolean(config.exclude_star_board)}
            id="strategy-field-exclude_star_board"
            label="排除科创板"
            onCheckedChange={(checked) => patchBoolean('exclude_star_board', checked)}
          />
        </div>
      </div>
    </section>
  );
}

function NumberField({
  focused,
  id,
  label,
  min,
  onChange,
  step,
  unit,
  value,
}: {
  focused?: boolean;
  id: string;
  label: string;
  min?: number;
  onChange: (value: string) => void;
  step: string;
  unit?: string;
  value: number | null | undefined;
}) {
  return (
    <label className={fieldClass(focused)}>
      <span>{label}</span>
      <div className="input-with-unit">
        <input id={id} min={min} step={step} type="number" value={value ?? ''} onChange={(event) => onChange(event.target.value)} />
        {unit ? <em>{unit}</em> : null}
      </div>
    </label>
  );
}

function fieldClass(focused?: boolean) {
  return focused ? 'parameter-field highlight' : 'parameter-field';
}
