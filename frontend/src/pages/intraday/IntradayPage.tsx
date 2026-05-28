import { useQuery } from '@tanstack/react-query';
import { getIntradayBoards } from '../../api/intraday';
import { Badge } from '../../design/Badge';
import { LoadingState } from '../../design/LoadingState';
import { Tabs } from '../../design/Tabs';
import { formatDateTime } from '../../utils/date';
import { IntradayBoard } from './IntradayBoard';
import { IntradayTimeline } from './IntradayTimeline';

export function IntradayPage() {
  const boards = useQuery({
    queryKey: ['intraday-boards'],
    queryFn: getIntradayBoards,
    refetchInterval: 30_000,
  });

  if (boards.isLoading) return <LoadingState label="读取盘中三榜" />;
  const data = boards.data || {};

  return (
    <div className="page-grid">
      <section className="surface pad">
        <div className="section-heading">
          <div>
            <h2>盘中雷达三榜</h2>
            <p>基于多次快照计算成交速度、增量、冲高回落、市场分位和题材同步。</p>
          </div>
          <div className="rule-chip-grid">
            <Badge tone="info">{formatDateTime(data.sample_at)}</Badge>
            <Badge>{data.sample_count || 0} 次采样</Badge>
          </div>
        </div>
        <Tabs
          defaultValue="anomaly"
          items={[
            { value: 'anomaly', label: '异动榜', content: <IntradayBoard rows={data.anomaly || []} tone="info" /> },
            { value: 'pullback', label: '低吸榜', content: <IntradayBoard rows={data.pullback || []} tone="good" /> },
            { value: 'danger', label: '风险榜', content: <IntradayBoard rows={data.risk || []} tone="risk" /> },
          ]}
        />
      </section>
      <IntradayTimeline themes={data.theme_pulse || []} />
    </div>
  );
}
