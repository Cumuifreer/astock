import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { ColumnDef } from '@tanstack/react-table';
import { deleteWatchlistItem, getWatchlist, updateWatchlistItem } from '../../api/watchlist';
import { Badge } from '../../design/Badge';
import { Button } from '../../design/Button';
import { ConfirmDialog } from '../../design/ConfirmDialog';
import { DataTable } from '../../design/DataTable';
import { EditDialog } from '../../design/EditDialog';
import { EmptyState } from '../../design/EmptyState';
import { LoadingState } from '../../design/LoadingState';
import { Segmented } from '../../design/Segmented';
import { Switch } from '../../design/Switch';
import { useToast } from '../../design/Toast';
import { formatDate } from '../../utils/date';
import { formatNumber, formatPercent, toNumber } from '../../utils/format';
import { HypothesisCard, type HypothesisItem } from './HypothesisCard';

type WatchStatus = '观察中' | '有效' | '误报' | '已归档';
type StatusFilter = '全部' | WatchStatus;
type ViewMode = 'card' | 'table';
type EditField = 'note' | 'invalidation_rule' | 'review_status';

const WATCH_STATUSES: WatchStatus[] = ['观察中', '有效', '误报', '已归档'];

export function WatchlistPage() {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const watchlist = useQuery({ queryKey: ['watchlist'], queryFn: getWatchlist });
  const [status, setStatus] = useState<StatusFilter>('全部');
  const [view, setView] = useState<ViewMode>('card');
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(() => new Set());
  const [editing, setEditing] = useState<{ item: HypothesisItem; field: EditField } | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<HypothesisItem | null>(null);
  const [bulkDeleteOpen, setBulkDeleteOpen] = useState(false);
  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['watchlist'] });
    void queryClient.invalidateQueries({ queryKey: ['bootstrap'] });
  };
  const updateMutation = useMutation({
    mutationFn: ({ item, changes }: { item: HypothesisItem; changes: Record<string, unknown> }) =>
      updateWatchlistItem(item.batch_id, item.code, changes),
    onSuccess: () => {
      invalidate();
      showToast('观察项已保存', 'success');
    },
  });
  const deleteMutation = useMutation({
    mutationFn: (item: HypothesisItem) => deleteWatchlistItem(item.batch_id, item.code),
    onSuccess: () => {
      invalidate();
      showToast('观察项已删除', 'success');
    },
  });
  const bulkUpdateMutation = useMutation({
    mutationFn: async ({ items, review_status }: { items: HypothesisItem[]; review_status: WatchStatus }) => {
      await Promise.all(items.map((item) => updateWatchlistItem(item.batch_id, item.code, { review_status })));
    },
    onSuccess: () => {
      setSelectedKeys(new Set());
      invalidate();
      showToast('批量状态已更新', 'success');
    },
  });
  const bulkDeleteMutation = useMutation({
    mutationFn: async (items: HypothesisItem[]) => {
      await Promise.all(items.map((item) => deleteWatchlistItem(item.batch_id, item.code)));
    },
    onSuccess: () => {
      setBulkDeleteOpen(false);
      setSelectedKeys(new Set());
      invalidate();
      showToast('已删除选中的观察项', 'success');
    },
  });
  const items = useMemo(() => {
    const all = (watchlist.data?.batches || []).flatMap((batch) => batch.items as HypothesisItem[]);
    return status === '全部' ? all : all.filter((item) => itemStatus(item) === status);
  }, [status, watchlist.data]);
  const selectedItems = useMemo(() => items.filter((item) => selectedKeys.has(itemKey(item))), [items, selectedKeys]);
  const editItem = (item: HypothesisItem, field: EditField) => setEditing({ item, field });
  const deleteItem = (item: HypothesisItem) => setDeleteTarget(item);
  const toggleSelected = (item: HypothesisItem, checked: boolean) => {
    const key = itemKey(item);
    setSelectedKeys((current) => {
      const next = new Set(current);
      if (checked) next.add(key);
      else next.delete(key);
      return next;
    });
  };
  const submitEdit = (value: string) => {
    if (!editing) return;
    updateMutation.mutate(
      { item: editing.item, changes: { [editing.field]: editing.field === 'review_status' ? normalizeStatus(value) : value } },
      { onSuccess: () => setEditing(null) },
    );
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
            { value: '已归档', label: '已归档' },
          ]}
        />
        <div className="data-toolbar" style={{ marginTop: 12 }}>
          <Segmented
            value={view}
            onChange={setView}
            options={[
              { value: 'card', label: '卡片视图' },
              { value: 'table', label: '表格视图' },
            ]}
          />
          {selectedItems.length ? (
            <>
              <Badge tone="info">已选 {selectedItems.length} 项</Badge>
              <Button onClick={() => bulkUpdateMutation.mutate({ items: selectedItems, review_status: '有效' })} variant="secondary">
                批量标记有效
              </Button>
              <Button onClick={() => bulkUpdateMutation.mutate({ items: selectedItems, review_status: '误报' })} variant="secondary">
                批量标记误报
              </Button>
              <Button onClick={() => bulkUpdateMutation.mutate({ items: selectedItems, review_status: '已归档' })} variant="secondary">
                批量归档
              </Button>
              <Button onClick={() => setBulkDeleteOpen(true)} variant="danger">
                批量删除
              </Button>
            </>
          ) : null}
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
          <WatchlistTable items={items} onDelete={deleteItem} onEdit={editItem} selectedKeys={selectedKeys} onSelect={toggleSelected} />
        )
      ) : (
        <EmptyState title="没有匹配观察项" description="从策略结果或盘中雷达加入观察池后，会自动记录交易假设和后验表现。" />
      )}
      <EditDialog
        open={Boolean(editing)}
        title={editing ? `编辑${editLabel(editing.field)}` : '编辑观察项'}
        label={editing ? editLabel(editing.field) : '内容'}
        value={editing ? editValue(editing.item, editing.field) : ''}
        mode={editing?.field === 'review_status' ? 'select' : 'textarea'}
        options={WATCH_STATUSES.map((value) => ({ value, label: value }))}
        busy={updateMutation.isPending}
        onSubmit={submitEdit}
        onOpenChange={(open) => {
          if (!open) setEditing(null);
        }}
      />
      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title="删除观察项"
        description="删除后不会影响历史分析结果，但这条观察记录将不再出现在复盘列表中。"
        confirmLabel="删除"
        busy={deleteMutation.isPending}
        onConfirm={() => {
          if (!deleteTarget) return;
          deleteMutation.mutate(deleteTarget, { onSuccess: () => setDeleteTarget(null) });
        }}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
      />
      <ConfirmDialog
        open={bulkDeleteOpen}
        title="批量删除观察项"
        description={`确认删除选中的 ${selectedItems.length} 条观察记录？删除后不会影响历史分析结果。`}
        confirmLabel="删除"
        busy={bulkDeleteMutation.isPending}
        onConfirm={() => bulkDeleteMutation.mutate(selectedItems)}
        onOpenChange={setBulkDeleteOpen}
      />
    </div>
  );
}

function WatchlistTable({
  items,
  onEdit,
  onDelete,
  selectedKeys,
  onSelect,
}: {
  items: HypothesisItem[];
  onEdit: (item: HypothesisItem, field: EditField) => void;
  onDelete: (item: HypothesisItem) => void;
  selectedKeys: Set<string>;
  onSelect: (item: HypothesisItem, checked: boolean) => void;
}) {
  const columns = useMemo<Array<ColumnDef<HypothesisItem, unknown>>>(
    () => [
      {
        header: '选择',
        cell: ({ row }) => <Switch checked={selectedKeys.has(itemKey(row.original))} onCheckedChange={(checked) => onSelect(row.original, checked)} />,
      },
      {
        header: '股票',
        cell: ({ row }) => (
          <div>
            <strong>{row.original.name || row.original.code}</strong>
            <div className="card-copy">{row.original.code}</div>
          </div>
        ),
      },
      { header: '状态', cell: ({ row }) => <Badge tone={statusTone(row.original)}>{itemStatus(row.original)}</Badge> },
      { header: '加入日期', cell: ({ row }) => formatDate(row.original.entry_date) },
      { header: '加入价', cell: ({ row }) => formatNumberStatus(row.original.entry_price, '待确认') },
      { header: '当前价', cell: ({ row }) => formatNumberStatus(row.original.latest_close, '待更新') },
      { header: 'T+1', cell: ({ row }) => formatPercentStatus(row.original.return_1d) },
      { header: 'T+3', cell: ({ row }) => formatPercentStatus(row.original.return_3d) },
      { header: 'T+5', cell: ({ row }) => formatPercentStatus(row.original.return_5d) },
      { header: '最新收益', cell: ({ row }) => formatPercentStatus(row.original.return_latest) },
      { header: '触发来源', cell: ({ row }) => sourceLabel(row.original.source_type, row.original.source_label) },
      { header: '失效条件', cell: ({ row }) => row.original.invalidation_rule || '未设置' },
      {
        header: '操作',
        cell: ({ row }) => (
          <div className="button-row">
            <Button onClick={() => onEdit(row.original, 'note')} variant="ghost">
              备注
            </Button>
            <Button onClick={() => onEdit(row.original, 'review_status')} variant="ghost">
              状态
            </Button>
            <Button onClick={() => onDelete(row.original)} variant="danger">
              删除
            </Button>
          </div>
        ),
      },
    ],
    [onDelete, onEdit, onSelect, selectedKeys],
  );
  return (
    <section className="surface pad">
      <DataTable data={items} columns={columns} estimateRowHeight={72} />
    </section>
  );
}

function itemKey(item: HypothesisItem) {
  return `${item.batch_id}-${item.code}`;
}

function normalizeStatus(value?: string | null): WatchStatus {
  if (value === '有效' || value === '误报' || value === '已归档') return value;
  if (value === '归档' || value === '已放弃' || value === '已验证' || value === '已错过') return '已归档';
  return '观察中';
}

function itemStatus(item: HypothesisItem): WatchStatus {
  return normalizeStatus(item.review_status);
}

function statusTone(item: HypothesisItem): 'good' | 'watch' | 'risk' | 'neutral' {
  const status = itemStatus(item);
  if (status === '有效') return 'good';
  if (status === '误报') return 'risk';
  if (status === '已归档') return 'neutral';
  return 'watch';
}

function editLabel(field: EditField) {
  if (field === 'note') return '备注';
  if (field === 'invalidation_rule') return '失效条件';
  return '状态';
}

function editValue(item: HypothesisItem, field: EditField) {
  if (field === 'note') return item.note || item.hypothesis || '';
  if (field === 'review_status') return itemStatus(item);
  return item.invalidation_rule || '';
}

function formatNumberStatus(value: unknown, fallback: string) {
  return toNumber(value) === null ? fallback : formatNumber(value, 2);
}

function formatPercentStatus(value: unknown) {
  return toNumber(value) === null ? '待复盘' : formatPercent(value);
}

function sourceLabel(sourceType?: string | null, sourceLabel?: string | null) {
  const label = String(sourceLabel || '').trim();
  if (/scanner/i.test(label)) return '策略选股候选';
  if (label) return label;
  if (sourceType === 'intraday') return '盘中雷达';
  if (sourceType === 'manual') return '手动';
  return '策略选股';
}
