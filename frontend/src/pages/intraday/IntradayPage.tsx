import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { ColumnDef } from '@tanstack/react-table';
import { getIntradayBoards, getIntradayTimeline, type IntradayCandidate } from '../../api/intraday';
import { Badge } from '../../design/Badge';
import { DataTable } from '../../design/DataTable';
import { Drawer } from '../../design/Drawer';
import { LoadingState } from '../../design/LoadingState';
import { Tabs } from '../../design/Tabs';
import { formatDateTime } from '../../utils/date';
import { formatMoney, formatPercent, formatRatio, toNumber } from '../../utils/format';
import { IntradayBoard } from './IntradayBoard';
import { IntradayTimeline } from './IntradayTimeline';

export function IntradayPage() {
  const [timelineTarget, setTimelineTarget] = useState<IntradayCandidate | null>(null);
  const boards = useQuery({
    queryKey: ['intraday-boards'],
    queryFn: getIntradayBoards,
    refetchInterval: 30_000,
  });
  const timeline = useQuery({
    queryKey: ['intraday-timeline', timelineTarget?.code],
    queryFn: () => getIntradayTimeline(timelineTarget?.code || ''),
    enabled: Boolean(timelineTarget?.code),
  });

  if (boards.isLoading) return <LoadingState label="读取盘中三榜" />;
  const data = boards.data || {};
  const allRows = [...(data.anomaly || []), ...(data.pullback || []), ...(data.risk || [])];
  const hideSampleMetrics = (data.sample_count || 0) <= 1;
  const hideThemeMetrics = !data.theme_pulse?.length && allRows.every((row) => row.theme_sync_score == null && row.metrics?.theme_sync_score == null);

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
        <div className="list-stack" style={{ marginBottom: 16 }}>
          {hideSampleMetrics ? (
            <p className="card-copy">
              {(data.sample_count || 0) === 1 ? '已完成 1 次采样，成交速度和增量将在第二次采样后显示。' : `已完成 ${data.sample_count || 0} 次采样，成交速度和增量将在第二次采样后显示。`}
            </p>
          ) : null}
          {hideThemeMetrics ? <p className="card-copy">题材联动数据未同步，本次榜单暂不显示题材同步。</p> : null}
        </div>
        <Tabs
          defaultValue="anomaly"
          items={[
            {
              value: 'anomaly',
              label: '异动榜',
              content: (
                <BoardWithHint
                  hideSampleMetrics={hideSampleMetrics}
                  hideThemeMetrics={hideThemeMetrics}
                  hint="异动榜：成交额明显放大，涨幅排名靠前，且未明显冲高回落。"
                  onOpenTimeline={setTimelineTarget}
                  rows={data.anomaly || []}
                  tone="info"
                />
              ),
            },
            {
              value: 'pullback',
              label: '低吸榜',
              content: (
                <BoardWithHint
                  hideSampleMetrics={hideSampleMetrics}
                  hideThemeMetrics={hideThemeMetrics}
                  hint="低吸榜：趋势仍在，日内回落到可观察区间，涨幅不过热。"
                  onOpenTimeline={setTimelineTarget}
                  rows={data.pullback || []}
                  tone="good"
                />
              ),
            },
            {
              value: 'danger',
              label: '风险榜',
              content: (
                <BoardWithHint
                  hideSampleMetrics={hideSampleMetrics}
                  hideThemeMetrics={hideThemeMetrics}
                  hint="风险榜：冲高回落、放量滞涨、涨幅过热或风险标签增加。"
                  onOpenTimeline={setTimelineTarget}
                  rows={data.risk || []}
                  tone="risk"
                />
              ),
            },
          ]}
        />
      </section>
      <IntradayTimeline themes={data.theme_pulse || []} />
      <Drawer open={Boolean(timelineTarget)} onOpenChange={(open) => !open && setTimelineTarget(null)} title={`${timelineTarget?.name || timelineTarget?.code || ''} 分时轨迹`}>
        {timeline.isLoading ? <LoadingState label="读取分时轨迹" /> : <TimelineDetail data={timeline.data || null} />}
      </Drawer>
    </div>
  );
}

function BoardWithHint({
  hint,
  rows,
  tone,
  hideSampleMetrics,
  hideThemeMetrics,
  onOpenTimeline,
}: {
  hint: string;
  rows: Parameters<typeof IntradayBoard>[0]['rows'];
  tone: 'info' | 'good' | 'risk';
  hideSampleMetrics: boolean;
  hideThemeMetrics: boolean;
  onOpenTimeline: (row: IntradayCandidate) => void;
}) {
  return (
    <div className="list-stack">
      <p className="card-copy">{hint}</p>
      <IntradayBoard hideSampleMetrics={hideSampleMetrics} hideThemeMetrics={hideThemeMetrics} onOpenTimeline={onOpenTimeline} rows={rows} tone={tone} />
    </div>
  );
}

function TimelineDetail({ data }: { data: import('../../types').IntradayTimeline | null }) {
  const columns = useMemo<Array<ColumnDef<import('../../types').IntradayTimelineRow, unknown>>>(
    () => [
      { header: '时间', accessorKey: 'sample_at', cell: ({ row }) => formatDateTime(row.original.sample_at) },
      { header: '最新价', accessorKey: 'latest_price', cell: ({ row }) => formatRatioStatus(row.original.latest_price) },
      { header: '涨跌幅', accessorKey: 'pct_chg', cell: ({ row }) => formatPercentStatus(row.original.pct_chg) },
      { header: '成交额', accessorKey: 'amount', cell: ({ row }) => formatMoneyStatus(row.original.amount) },
      { header: '成交增量', accessorKey: 'amount_delta', cell: ({ row }) => formatMoneyStatus(row.original.amount_delta, amountDeltaFallback(row.original.amount_delta_status)) },
      { header: '成交放大', accessorKey: 'amount_ratio', cell: ({ row }) => formatRatioStatus(row.original.amount_ratio, amountRatioFallback(row.original.amount_ratio_status)) },
      { header: '触发原因', accessorKey: 'reasons', cell: ({ row }) => (row.original.reasons || []).join('；') || '等待确认' },
    ],
    [],
  );
  if (!data?.rows?.length) return <p className="card-copy">暂无分时采样记录。</p>;
  return (
    <div className="list-stack">
      <div className="grid-3">
        <Metric label="采样次数" value={String(data.rows.length)} />
        <Metric label="最新涨跌幅" value={formatPercentStatus(data.rows[data.rows.length - 1]?.pct_chg)} />
        <Metric label="成交额变化" value={formatMoneyStatus(data.rows[data.rows.length - 1]?.amount_delta, amountDeltaFallback(data.rows[data.rows.length - 1]?.amount_delta_status))} />
      </div>
      <DataTable data={data.rows} columns={columns} estimateRowHeight={64} />
    </div>
  );
}

function formatMoneyStatus(value: unknown, fallback = '暂无数据') {
  return toNumber(value) === null ? fallback : formatMoney(value);
}

function formatPercentStatus(value: unknown, fallback = '暂无数据') {
  return toNumber(value) === null ? fallback : formatPercent(value);
}

function formatRatioStatus(value: unknown, fallback = '暂无数据') {
  return toNumber(value) === null ? fallback : formatRatio(value);
}

function amountDeltaFallback(status?: string | null) {
  return status === 'insufficient_samples' ? '等待第二次采样' : '暂无数据';
}

function amountRatioFallback(status?: string | null) {
  return status === 'missing_history_amount' ? '缺历史均量' : '暂无数据';
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <article className="metric-pill">
      <span className="metric-label">{label}</span>
      <div className="metric-value">{value}</div>
    </article>
  );
}
