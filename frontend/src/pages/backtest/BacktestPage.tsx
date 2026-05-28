import { useQuery } from '@tanstack/react-query';
import { getBacktestRuns } from '../../api/backtest';
import { Badge } from '../../design/Badge';
import { Tabs } from '../../design/Tabs';
import { formatDateTime } from '../../utils/date';
import { SignalEvaluation } from './SignalEvaluation';
import { PortfolioBacktest } from './PortfolioBacktest';

export function BacktestPage() {
  const runs = useQuery({ queryKey: ['backtest-runs'], queryFn: getBacktestRuns });
  const latest = runs.data?.rows?.[0];
  return (
    <div className="page-grid">
      <section className="surface pad">
        <div className="section-heading">
          <div>
            <h2>回测实验室</h2>
            <p>先判断规则是否有预测力，再判断组合是否能赚钱。</p>
          </div>
          <div className="rule-chip-grid">
            <Badge tone="info">{runs.data?.rows?.length || 0} 次历史运行</Badge>
            {latest ? <Badge>{formatDateTime(latest.started_at)}</Badge> : null}
          </div>
        </div>
        <Tabs
          defaultValue="signal"
          items={[
            { value: 'signal', label: '信号评估', content: <SignalEvaluation /> },
            { value: 'portfolio', label: '组合回测', content: <PortfolioBacktest /> },
          ]}
        />
      </section>
    </div>
  );
}
