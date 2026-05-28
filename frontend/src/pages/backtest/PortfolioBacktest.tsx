import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Play } from 'lucide-react';
import { getPortfolioBacktest, runPortfolioBacktest } from '../../api/backtest';
import type { StrategyConfig } from '../../types';
import { Button } from '../../design/Button';
import { Badge } from '../../design/Badge';
import { CheckTile } from '../../design/CheckTile';
import { Select } from '../../design/Select';
import { strategySummary } from '../../utils/strategy';
import { formatMoney, formatPercent, formatRatio, toNumber } from '../../utils/format';
import { todayISO } from '../../utils/date';

export function PortfolioBacktest({ config, strategyName }: { config: StrategyConfig | null; strategyName: string }) {
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState(todayISO());
  const [initialCapital, setInitialCapital] = useState('1000000');
  const [rebalance, setRebalance] = useState('daily');
  const [maxPositions, setMaxPositions] = useState('8');
  const [maxPositionPct, setMaxPositionPct] = useState('15');
  const [holdDays, setHoldDays] = useState('5');
  const [candidateLimit, setCandidateLimit] = useState('');
  const [entryRule, setEntryRule] = useState('next_open');
  const [exitRule, setExitRule] = useState('hold_days');
  const [feeBps, setFeeBps] = useState('8');
  const [slippageBps, setSlippageBps] = useState('5');
  const [limitUpModel, setLimitUpModel] = useState(true);
  const [limitDownModel, setLimitDownModel] = useState(true);
  const mutation = useMutation({
    mutationFn: () =>
      runPortfolioBacktest({
        config,
        strategy_name: strategyName,
        initial_capital: Number(initialCapital) || 1_000_000,
        start_date: startDate || undefined,
        end_date: endDate || undefined,
        candidate_limit: Number(candidateLimit) || config?.candidate_limit || 80,
        max_positions: Number(maxPositions) || 8,
        rebalance_frequency: rebalance,
        position_sizing: 'equal_weight',
        max_position_pct: (Number(maxPositionPct) || 15) / 100,
        entry_rule: entryRule,
        exit_rule: exitRule,
        hold_days: Number(holdDays) || 5,
        transaction_cost_bps: Number(feeBps) || 8,
        slippage_bps: Number(slippageBps) || 5,
        limit_up_model: limitUpModel,
        limit_down_model: limitDownModel,
        limit_up_down_model: limitUpModel || limitDownModel,
      }),
  });
  const result = useQuery({
    queryKey: ['portfolio-backtest', mutation.data?.runId],
    queryFn: () => getPortfolioBacktest(mutation.data?.runId || ''),
    enabled: Boolean(mutation.data?.runId),
    refetchInterval: (query) => {
      const run = (query.state.data as Record<string, unknown> | undefined)?.run as Record<string, unknown> | undefined;
      const status = String(run?.status || '');
      return status === 'queued' || status === 'running' ? 2600 : false;
    },
  });
  const run = (result.data?.run || {}) as Record<string, unknown>;
  const summary = (run.summary || {}) as Record<string, unknown>;
  return (
    <section className="surface pad">
      <div className="section-heading">
        <div>
          <h2>简化组合模拟</h2>
          <p>{strategyName} · {strategySummary(config)}</p>
        </div>
        <Button disabled={mutation.isPending || !config} icon={<Play size={16} />} onClick={() => mutation.mutate()} variant="primary">
          运行组合回测
        </Button>
      </div>
      <div className="notice-card" style={{ marginBottom: 14 }}>
        当前为简化组合模拟，适合快速比较策略，不等同真实交易账户回测。
      </div>
      <div className="backtest-form">
        <label>
          <span>初始资金</span>
          <input inputMode="numeric" value={initialCapital} onChange={(event) => setInitialCapital(event.target.value)} />
        </label>
        <label>
          <span>开始日期</span>
          <input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} />
        </label>
        <label>
          <span>结束日期</span>
          <input type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} />
        </label>
        <label>
          <span>候选数量</span>
          <input inputMode="numeric" placeholder={String(config?.candidate_limit || 80)} value={candidateLimit} onChange={(event) => setCandidateLimit(event.target.value)} />
        </label>
        <label>
          <span>调仓频率</span>
          <Select
            label="调仓频率"
            value={rebalance}
            onChange={setRebalance}
            options={[
              { value: 'daily', label: '每日' },
              { value: 'weekly', label: '每周' },
              { value: 'monthly', label: '每月' },
            ]}
          />
        </label>
        <label>
          <span>持仓数量</span>
          <input inputMode="numeric" value={maxPositions} onChange={(event) => setMaxPositions(event.target.value)} />
        </label>
        <label>
          <span>单票最大仓位</span>
          <input inputMode="numeric" value={maxPositionPct} onChange={(event) => setMaxPositionPct(event.target.value)} />
        </label>
        <label>
          <span>持有天数</span>
          <input inputMode="numeric" value={holdDays} onChange={(event) => setHoldDays(event.target.value)} />
        </label>
        <label>
          <span>买入规则</span>
          <Select
            label="买入规则"
            value={entryRule}
            onChange={setEntryRule}
            options={[
              { value: 'next_open', label: '次日开盘' },
              { value: 'same_close', label: '当日收盘' },
              { value: 'next_vwap', label: '次日 VWAP 近似' },
            ]}
          />
        </label>
        <label>
          <span>卖出规则</span>
          <Select
            label="卖出规则"
            value={exitRule}
            onChange={setExitRule}
            options={[
              { value: 'hold_days', label: '持有 N 日' },
              { value: 'break_rule', label: '跌破条件' },
              { value: 'risk_hit', label: '风险规则命中' },
            ]}
          />
        </label>
        <label>
          <span>交易成本</span>
          <input inputMode="numeric" value={feeBps} onChange={(event) => setFeeBps(event.target.value)} />
        </label>
        <label>
          <span>滑点</span>
          <input inputMode="numeric" value={slippageBps} onChange={(event) => setSlippageBps(event.target.value)} />
        </label>
        <CheckTile checked={limitUpModel} label="涨停买不进" onCheckedChange={setLimitUpModel} />
        <CheckTile checked={limitDownModel} label="跌停卖不出" onCheckedChange={setLimitDownModel} />
      </div>
      {mutation.data ? (
        <div className="backtest-runline">
          <strong>{statusLabel(String(run.status || mutation.data.status))}</strong>
          <Button onClick={() => (window.location.hash = '#status')} variant="ghost">
            查看任务状态
          </Button>
        </div>
      ) : null}
      <div className="metric-row">
        <Metric label="总收益" value={formatPercentStatus(summary.total_return)} />
        <Metric label="年化收益" value={formatPercentStatus(summary.annual_return)} />
        <Metric label="最大回撤" value={formatPercentStatus(summary.max_drawdown)} />
        <Metric label="胜率" value={formatPercentStatus(summary.win_rate)} />
        <Metric label="盈亏比" value={formatRatioStatus(summary.profit_factor)} />
        <Metric label="交易次数" value={formatRatioStatus(summary.trade_count)} />
        <Metric label="换手率" value={formatPercentStatus(summary.turnover)} />
        <Metric label="最终权益" value={formatMoneyStatus(summary.ending_equity || summary.final_equity)} />
      </div>
      <div className="rule-chip-grid" style={{ marginTop: 14 }}>
        <Badge tone="info">涨停买不进</Badge>
        <Badge tone="info">跌停延后卖出</Badge>
        <Badge>等权持仓</Badge>
        <Badge>任务队列跟踪</Badge>
      </div>
      <div className="grid-3" style={{ marginTop: 14 }}>
        <Placeholder title="资金曲线" />
        <Placeholder title="回撤曲线" />
        <Placeholder title="月度收益表" />
        <Placeholder title="交易明细" />
        <Placeholder title="当前持仓模拟" />
      </div>
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric-pill">
      <span className="metric-label">{label}</span>
      <div className="metric-value">{value}</div>
    </div>
  );
}

function formatMoneyStatus(value: unknown) {
  return toNumber(value) === null ? '待回测' : formatMoney(value);
}

function formatPercentStatus(value: unknown) {
  return toNumber(value) === null ? '待回测' : formatPercent(value);
}

function formatRatioStatus(value: unknown) {
  return toNumber(value) === null ? '待回测' : formatRatio(value);
}

function Placeholder({ title }: { title: string }) {
  return (
    <article className="surface-subtle">
      <h3>{title}</h3>
      <p className="card-copy">回测完成后展示。</p>
    </article>
  );
}

function statusLabel(status: string) {
  if (status === 'queued') return '已排队';
  if (status === 'running') return '运行中';
  if (status === 'completed_full' || status === 'completed') return '完成';
  if (status === 'failed') return '失败';
  return status || '已提交';
}
