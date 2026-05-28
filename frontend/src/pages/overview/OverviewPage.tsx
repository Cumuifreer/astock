import { useQuery } from '@tanstack/react-query';
import { getMarketOverview } from '../../api/market';
import type { DailyBrief } from '../../types';
import { Badge } from '../../design/Badge';
import { LoadingState } from '../../design/LoadingState';
import { EmptyState } from '../../design/EmptyState';
import { useBootstrap } from '../../hooks/useBootstrap';
import { formatDate, formatDateTime } from '../../utils/date';
import { MarketHero } from './MarketHero';
import { SectorHeatmap } from './SectorHeatmap';
import { DailyActionList } from './DailyActionList';
import { MarketFlowPanel } from './MarketFlowPanel';

export function OverviewPage() {
  const bootstrap = useBootstrap();
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
      <DailyBriefPanel brief={bootstrap.data?.daily_brief || bootstrap.data?.overview?.latest_brief || null} />
    </div>
  );
}

function DailyBriefPanel({ brief }: { brief: DailyBrief | null }) {
  if (!brief) {
    return <EmptyState title="今日资讯简报生成中" description="后台会用现有 daily brief 任务自动补齐，生成后会回到市场总览。" />;
  }
  const rows = [
    ...(brief.article_flow?.tech || []),
    ...(brief.article_flow?.finance || []),
    ...(brief.article_flow?.politics || []),
  ].slice(0, 9);
  return (
    <section className="surface pad daily-brief-panel">
      <div className="section-heading">
        <div>
          <h2>今日资讯简报</h2>
          <p>{brief.hero_headline || brief.daily_overview || '多源资讯摘要'}</p>
        </div>
        <div className="button-row">
          <Badge tone="info">{formatDate(brief.brief_date)}</Badge>
          <Badge>{formatDateTime(brief.generated_at)}</Badge>
        </div>
      </div>
      <p className="card-copy">{brief.daily_overview}</p>
      <div className="brief-list-grid">
        {rows.length ? (
          rows.map((item) => (
            <a className="brief-mini-card" href={item.url} key={`${item.url}-${item.title}`} rel="noreferrer" target="_blank">
              <strong>{item.title}</strong>
              <span>{item.source}</span>
              <p>{item.summary}</p>
            </a>
          ))
        ) : (
          <p className="card-copy">暂无可展示条目。</p>
        )}
      </div>
      {brief.keywords?.length ? (
        <div className="rule-chip-grid" style={{ marginTop: 14 }}>
          {brief.keywords.slice(0, 8).map((keyword) => (
            <Badge key={keyword}>{keyword}</Badge>
          ))}
        </div>
      ) : null}
    </section>
  );
}
