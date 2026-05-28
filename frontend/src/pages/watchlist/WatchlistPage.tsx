import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { deleteWatchlistItem, getWatchlist, updateWatchlistItem } from '../../api/watchlist';
import { Badge } from '../../design/Badge';
import { Button } from '../../design/Button';
import { EmptyState } from '../../design/EmptyState';
import { LoadingState } from '../../design/LoadingState';
import { Segmented } from '../../design/Segmented';
import { formatDate } from '../../utils/date';
import { formatNumber, formatPercent } from '../../utils/format';
import { HypothesisCard, type HypothesisItem } from './HypothesisCard';

type StatusFilter = '全部' | '观察中' | '有效' | '误报' | '归档';
type ViewMode = 'card' | 'table';

export function WatchlistPage() {
  const queryClient = useQueryClient();
  const watchlist = useQuery({ queryKey: ['watchlist'], queryFn: getWatchlist });
  const [status, setStatus] = useState<StatusFilter>('全部');
  const [view, setView] = useState<ViewMode>('card');
  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['watchlist'] });
    void queryClient.invalidateQueries({ queryKey: ['bootstrap'] });
  };
  const updateMutation = useMutation({
    mutationFn: ({ item, payload }: { item: HypothesisItem; payload: Record<string, unknown> }) =>
      updateWatchlistItem(item.batch_id, item.code, payload),
    onSuccess: invalidate,
  });
  const deleteMutation = useMutation({
    mutationFn: (item: HypothesisItem) => deleteWatchlistItem(item.batch_id, item.code),
    onSuccess: invalidate,
  });
  const items = useMemo(() => {
    const all = (watchlist.data?.batches || []).flatMap((batch) => batch.items as HypothesisItem[]);
    return status === '全部' ? all : all.filter((item) => item.review_status === status);
  }, [status, watchlist.data]);
  const editItem = (item: HypothesisItem, field: 'note' | 'invalidation_rule' | 'review_status') => {
    const labels = { note: '备注', invalidation_rule: '失效条件', review_status: '状态' };
    const current = field === 'note' ? item.note || item.hypothesis || '' : field === 'review_status' ? item.review_status || '观察中' : item.invalidation_rule || '';
    const value = window.prompt(`编辑${labels[field]}`, current);
    if (value === null) return;
    updateMutation.mutate({ item, payload: { [field]: value } });
  };
  const deleteItem = (item: HypothesisItem) => {
    if (!window.confirm('确认删除这个观察项？删除后不会影响历史分析结果。')) return;
    deleteMutation.mutate(item);
  };

  if (watchlist.isLoading) return <LoadingState label="读取观察池" />;

  return (
    <div className="page-grid">
      <section className="surface pad">
        <div className="section-heading">
          <div>
            <h2>观察池</h2>
            <p>跟踪已加入的候选，记录加入理由、失效条件和后续表现。</p>
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
        <div style={{ marginTop: 12 }}>
          <Segmented
            value={view}
            onChange={setView}
            options={[
              { value: 'card', label: '卡片视图' },
              { value: 'table', label: '表格视图' },
            ]}
          />
        </div>
      </section>
      {items.length ? (
        view === 'card' ? (
          <div className="grid-2">
            {items.map((item) => (
              <HypothesisCard item={item} key={`${item.batch_id}-${item.code}`} onDelete={deleteItem} onEdit={editItem} />
            ))}
          </div>
        ) : (
          <WatchlistTable items={items} onDelete={deleteItem} onEdit={editItem} />
        )
      ) : (
        <EmptyState title="没有匹配观察项" description="从策略结果或盘中雷达加入观察池后，会自动记录交易假设和后验表现。" />
      )}
    </div>
  );
}

function WatchlistTable({
  items,
  onEdit,
  onDelete,
}: {
  items: HypothesisItem[];
  onEdit: (item: HypothesisItem, field: 'note' | 'invalidation_rule' | 'review_status') => void;
  onDelete: (item: HypothesisItem) => void;
}) {
  return (
    <section className="surface pad">
      <div className="table-wrap">
        <table className="warehouse-table">
          <thead>
            <tr>
              <th>股票</th>
              <th>状态</th>
              <th>加入日期</th>
              <th>加入价</th>
              <th>当前价</th>
              <th>T+1</th>
              <th>T+5</th>
              <th>最新收益</th>
              <th>失效条件</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={`${item.batch_id}-${item.code}`}>
                <td>
                  <strong>{item.name || item.code}</strong>
                  <div className="card-copy">{item.code}</div>
                </td>
                <td>{item.review_status || '观察中'}</td>
                <td>{formatDate(item.entry_date)}</td>
                <td>{formatNumber(item.entry_price, 2)}</td>
                <td>{formatNumber(item.latest_close, 2)}</td>
                <td>{formatPercent(item.return_1d)}</td>
                <td>{formatPercent(item.return_5d)}</td>
                <td>{formatPercent(item.return_latest)}</td>
                <td>{item.invalidation_rule || '未设置'}</td>
                <td>
                  <div className="button-row">
                    <Button onClick={() => onEdit(item, 'review_status')} variant="ghost">
                      状态
                    </Button>
                    <Button onClick={() => onDelete(item)} variant="danger">
                      删除
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
