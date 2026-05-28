import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getWatchlist } from '../../api/watchlist';
import { Badge } from '../../design/Badge';
import { EmptyState } from '../../design/EmptyState';
import { LoadingState } from '../../design/LoadingState';
import { Segmented } from '../../design/Segmented';
import { HypothesisCard, type HypothesisItem } from './HypothesisCard';

type StatusFilter = '全部' | '观察中' | '有效' | '误报' | '归档';

const hypothesis = 'hypothesis';
const invalidation_rule = 'invalidation_rule';

export function WatchlistPage() {
  const watchlist = useQuery({ queryKey: ['watchlist'], queryFn: getWatchlist });
  const [status, setStatus] = useState<StatusFilter>('全部');
  const items = useMemo(() => {
    const all = (watchlist.data?.batches || []).flatMap((batch) => batch.items as HypothesisItem[]);
    return status === '全部' ? all : all.filter((item) => item.review_status === status);
  }, [status, watchlist.data]);

  if (watchlist.isLoading) return <LoadingState label="读取观察池" />;

  return (
    <div className="page-grid">
      <section className="surface pad">
        <div className="section-heading">
          <div>
            <h2>交易假设观察池</h2>
            <p>
              观察池按 {hypothesis}、触发规则、{invalidation_rule} 和后验收益管理，不再只是收藏夹。
            </p>
          </div>
          <div className="rule-chip-grid">
            <Badge tone="info">{watchlist.data?.summary?.item_count || 0} 个观察项</Badge>
            <Badge>{watchlist.data?.summary?.batch_count || 0} 个批次</Badge>
          </div>
        </div>
        <Segmented
          value={status}
          onChange={setStatus}
          options={[
            { value: '全部', label: '全部' },
            { value: '观察中', label: '观察中' },
            { value: '有效', label: '有效' },
            { value: '误报', label: '误报' },
            { value: '归档', label: '归档' },
          ]}
        />
      </section>
      {items.length ? (
        <div className="grid-2">
          {items.map((item) => (
            <HypothesisCard item={item} key={`${item.batch_id}-${item.code}`} />
          ))}
        </div>
      ) : (
        <EmptyState title="没有匹配观察项" description="从策略结果或盘中雷达加入观察池后，会自动记录交易假设和后验表现。" />
      )}
    </div>
  );
}
