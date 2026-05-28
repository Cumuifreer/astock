import { useQuery } from '@tanstack/react-query';
import { getMarketOverview } from '../../api/market';
import { LoadingState } from '../../design/LoadingState';
import { EmptyState } from '../../design/EmptyState';
import { MarketHero } from './MarketHero';
import { SectorHeatmap } from './SectorHeatmap';
import { DailyActionList } from './DailyActionList';
import { MarketFlowPanel } from './MarketFlowPanel';

export function OverviewPage() {
  const overview = useQuery({
    queryKey: ['market-overview'],
    queryFn: getMarketOverview,
  });

  if (overview.isLoading) return <LoadingState label="读取市场总览" />;
  if (overview.isError) {
    return <EmptyState title="市场总览暂不可用" description={overview.error instanceof Error ? overview.error.message : '后端没有返回市场状态。'} />;
  }

  const data = overview.data || {};
  return (
    <div className="page-grid">
      <MarketHero state={data.state} tradeDate={data.trade_date} />
      <MarketFlowPanel pulse={data.pulse} freshness={data.data_freshness || []} />
      <SectorHeatmap sectors={data.sector_heatmap || []} />
      <DailyActionList items={data.action_items || []} />
    </div>
  );
}
