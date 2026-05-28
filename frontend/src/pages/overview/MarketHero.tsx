import { AlertTriangle, Compass, ShieldCheck } from 'lucide-react';
import type { MarketState } from '../../api/market';
import { Badge } from '../../design/Badge';
import { formatNumber } from '../../utils/format';

type MarketHeroProps = {
  state?: MarketState;
  tradeDate?: string;
};

export function MarketHero({ state, tradeDate }: MarketHeroProps) {
  const score = typeof state?.score === 'number' ? state.score : null;
  const label = state?.label || '待同步';
  const riskTone = state?.risk_level === '高' || state?.risk_level === '极高' ? 'risk' : state?.risk_level === '中' ? 'watch' : 'good';
  return (
    <section className="surface hero-panel">
      <div>
        <div className="hero-kicker">{tradeDate || state?.trade_date || '最近交易日'}</div>
        <h2 className="hero-title">今日市场：{label}</h2>
        <p className="hero-copy">
          {state?.headline || '一句话判断：完成同步今日数据后，系统会基于市场宽度、指数趋势、成交额热度、涨跌停温度和板块热力生成可解释的市场判断。'}
        </p>
        <div className="metric-row" style={{ marginTop: 18 }}>
          <div className="metric-pill">
            <span className="metric-label">市场评分</span>
            <div className="metric-value">{score === null ? '待同步' : formatNumber(score, 0)}</div>
          </div>
          <div className="metric-pill">
            <span className="metric-label">风险等级</span>
            <div className="metric-value">
              <Badge tone={riskTone}>{state?.risk_level || '未知'}</Badge>
            </div>
          </div>
          <div className="metric-pill">
            <span className="metric-label">仓位建议</span>
            <div className="metric-value">{state?.suggested_position || '待同步'}</div>
          </div>
        </div>
      </div>
      <div className="list-stack">
        <SignalList icon={<Compass size={16} />} title="机会" items={state?.key_opportunities || []} tone="good" />
        <SignalList icon={<AlertTriangle size={16} />} title="风险" items={state?.key_risks || []} tone="risk" />
      </div>
    </section>
  );
}

function SignalList({ title, items, tone, icon }: { title: string; items: string[]; tone: 'good' | 'risk'; icon: JSX.Element }) {
  const fallback = tone === 'good' ? ['等待板块热力和候选变化'] : ['等待涨跌停温度和风险持仓'];
  return (
    <div className="card" style={{ boxShadow: 'none' }}>
      <div className="split-row">
        <Badge tone={tone}>{icon}{title}</Badge>
        {tone === 'good' ? <ShieldCheck size={16} color="var(--success)" /> : null}
      </div>
      <div className="list-stack" style={{ marginTop: 12 }}>
        {(items.length ? items : fallback).slice(0, 3).map((item) => (
          <p className="card-copy" key={item}>
            {item}
          </p>
        ))}
      </div>
    </div>
  );
}
