import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { ColumnDef } from '@tanstack/react-table';
import { Play } from 'lucide-react';
import {
  getIntradayBoards,
  getIntradayStrategyTracking,
  getIntradayTimeline,
  runIntradayStrategyTracking,
  saveIntradayConfig,
  saveIntradayStrategyTrackingConfig,
  type IntradayBoardKey,
  type IntradayCandidate,
  type IntradayStrategyTracking,
  type IntradayStrategyTrackingRow,
} from '../../api/intraday';
import { queryKeys } from '../../api/queryKeys';
import { Badge } from '../../design/Badge';
import { Button } from '../../design/Button';
import { DataTable } from '../../design/DataTable';
import { Drawer } from '../../design/Drawer';
import { EmptyState } from '../../design/EmptyState';
import { LoadingState } from '../../design/LoadingState';
import { Select as CustomSelect } from '../../design/Select';
import { Switch } from '../../design/Switch';
import { Tabs } from '../../design/Tabs';
import { useToast } from '../../design/Toast';
import { useBootstrap } from '../../hooks/useBootstrap';
import type { StrategyPreset } from '../../types';
import { formatChinaDateTime } from '../../utils/date';
import { formatMoney, formatPercent, formatRatio, toNumber } from '../../utils/format';
import { IntradayBoard } from './IntradayBoard';
import { IntradayTimeline } from './IntradayTimeline';

const boardSwitches: Array<{ key: IntradayBoardKey; label: string; title: string }> = [
  { key: 'anomaly', label: '异动', title: '异动榜' },
  { key: 'pullback', label: '低吸', title: '低吸榜' },
  { key: 'risk', label: '风险', title: '风险榜' },
];

export function IntradayPage() {
  const [timelineTarget, setTimelineTarget] = useState<IntradayCandidate | null>(null);
  const bootstrap = useBootstrap();
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const boards = useQuery({
    queryKey: queryKeys.intraday.boards(),
    queryFn: getIntradayBoards,
    refetchInterval: 30_000,
  });
  const tracking = useQuery({
    queryKey: queryKeys.intraday.strategyTracking(),
    queryFn: getIntradayStrategyTracking,
    refetchInterval: 30_000,
  });
  const timeline = useQuery({
    queryKey: queryKeys.intraday.timeline(timelineTarget?.code),
    queryFn: () => getIntradayTimeline(timelineTarget?.code || ''),
    enabled: Boolean(timelineTarget?.code),
  });
  const saveTrackingMutation = useMutation({
    mutationFn: saveIntradayStrategyTrackingConfig,
    onSuccess: (result) => {
      queryClient.setQueryData(queryKeys.intraday.strategyTracking(), result.strategy_tracking);
      void queryClient.invalidateQueries({ queryKey: queryKeys.intraday.strategyTracking() });
      showToast('策略跟踪已切换', 'success');
    },
    onError: (error) => showToast(error instanceof Error ? error.message : '策略跟踪切换失败', 'danger'),
  });
  const saveConfigMutation = useMutation({
    mutationFn: (enabledBoards: Record<IntradayBoardKey, boolean>) => saveIntradayConfig({ enabled_boards: enabledBoards }),
    onSuccess: (result) => {
      queryClient.setQueryData(queryKeys.intraday.boards(), (current: unknown) => ({
        ...((current || {}) as Record<string, unknown>),
        config: result.config,
        enabled_boards: result.config.enabled_boards,
      }));
      void queryClient.invalidateQueries({ queryKey: queryKeys.intraday.boards() });
      void queryClient.invalidateQueries({ queryKey: queryKeys.runtimeHealth() });
      showToast('盘中榜单已更新', 'success');
    },
    onError: (error) => showToast(error instanceof Error ? error.message : '盘中榜单更新失败', 'danger'),
  });
  const runTrackingMutation = useMutation({
    mutationFn: () => runIntradayStrategyTracking(),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.intraday.strategyTracking() });
      void queryClient.invalidateQueries({ queryKey: queryKeys.tasks.active() });
      void queryClient.invalidateQueries({ queryKey: queryKeys.runtimeHealth() });
      showToast('策略追踪已排队', 'success');
    },
    onError: (error) => showToast(error instanceof Error ? error.message : '策略追踪启动失败', 'danger'),
  });

  if (boards.isLoading || tracking.isLoading) return <LoadingState label="读取盘中雷达" />;
  const data = boards.data || {};
  const trackingData = tracking.data || {};
  const strategies = bootstrap.data?.strategies || [];
  const selectedStrategyId = trackingData.config?.strategy_preset_id || trackingData.strategy?.id || '';
  const enabledBoards = normalizeEnabledBoards(data.enabled_boards || data.config?.enabled_boards);
  const allRows = [...(data.anomaly || []), ...(data.pullback || []), ...(data.risk || [])];
  const hideSampleMetrics = (data.sample_count || 0) <= 1;
  const hideThemeMetrics = !data.theme_pulse?.length && allRows.every((row) => row.theme_sync_score == null && row.metrics?.theme_sync_score == null);
  const handleBoardToggle = (key: IntradayBoardKey, checked: boolean) => {
    saveConfigMutation.mutate({ ...enabledBoards, [key]: checked });
  };

  return (
    <div className="page-grid">
      <section className="surface pad">
        <div className="section-heading">
          <div>
            <h2>盘中雷达</h2>
            <p>跟踪当前策略命中，同时观察成交速度、增量、冲高回落、市场分位和题材同步。</p>
          </div>
          <div className="rule-chip-grid">
            <Badge tone="info">{formatChinaDateTime(data.sample_at)}</Badge>
            <Badge>{data.sample_count || 0} 次采样</Badge>
          </div>
        </div>
        <div className="intraday-control-row">
          <div className="intraday-board-switches" aria-label="盘中榜单开关">
            <span>盘中榜单</span>
            {boardSwitches.map((item) => (
              <Switch
                checked={enabledBoards[item.key]}
                disabled={saveConfigMutation.isPending}
                key={item.key}
                label={item.label}
                onCheckedChange={(checked) => handleBoardToggle(item.key, checked)}
              />
            ))}
          </div>
          <Badge tone={Object.values(enabledBoards).some(Boolean) ? 'info' : 'neutral'}>
            {Object.values(enabledBoards).some(Boolean) ? '高频雷达' : '轻量刷新'}
          </Badge>
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
          defaultValue="strategy-tracking"
          items={[
            {
              value: 'strategy-tracking',
              label: '策略跟踪',
              content: (
                <StrategyTrackingPanel
                  data={trackingData}
                  isRunPending={runTrackingMutation.isPending}
                  onOpenTimeline={setTimelineTarget}
                  onRun={() => runTrackingMutation.mutate()}
                  onSelectStrategy={(strategyPresetId) => saveTrackingMutation.mutate(strategyPresetId)}
                  selectedStrategyId={selectedStrategyId}
                  strategies={strategies}
                />
              ),
            },
            {
              value: 'anomaly',
              label: '异动榜',
              content: (
                <BoardWithHint
                  hideSampleMetrics={hideSampleMetrics}
                  hideThemeMetrics={hideThemeMetrics}
                  hint="异动榜：成交额明显放大，涨幅排名靠前，且未明显冲高回落。"
                  enabled={enabledBoards.anomaly}
                  title="异动榜"
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
                  enabled={enabledBoards.pullback}
                  title="低吸榜"
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
                  enabled={enabledBoards.risk}
                  title="风险榜"
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
  enabled,
  hint,
  rows,
  tone,
  title,
  hideSampleMetrics,
  hideThemeMetrics,
  onOpenTimeline,
}: {
  enabled: boolean;
  hint: string;
  rows: Parameters<typeof IntradayBoard>[0]['rows'];
  tone: 'info' | 'good' | 'risk';
  title: string;
  hideSampleMetrics: boolean;
  hideThemeMetrics: boolean;
  onOpenTimeline: (row: IntradayCandidate) => void;
}) {
  return (
    <div className="list-stack">
      <p className="card-copy">{hint}</p>
      {enabled ? (
        <IntradayBoard hideSampleMetrics={hideSampleMetrics} hideThemeMetrics={hideThemeMetrics} onOpenTimeline={onOpenTimeline} rows={rows} tone={tone} />
      ) : (
        <EmptyState title={`${title}未开启`} description="开启后会在下一次盘中刷新时更新。" />
      )}
    </div>
  );
}

function StrategyTrackingPanel({
  data,
  isRunPending,
  strategies,
  selectedStrategyId,
  onRun,
  onSelectStrategy,
  onOpenTimeline,
}: {
  data: IntradayStrategyTracking;
  isRunPending: boolean;
  strategies: StrategyPreset[];
  selectedStrategyId: string;
  onRun: () => void;
  onSelectStrategy: (strategyPresetId: string) => void;
  onOpenTimeline: (row: IntradayCandidate) => void;
}) {
  const rows = data.rows || [];
  const options = useMemo(
    () =>
      strategies.map((preset) => ({
        value: preset.id,
        label: preset.name,
      })),
    [strategies],
  );
  const summary = data.summary || {};
  const strategyMissing = data.config?.strategy_status === 'missing';
  const zeroReason = summary.zero_reason || '等待下一次盘中采样。';

  return (
    <div className="list-stack">
      <div className="strategy-tracking-toolbar">
        <div className="strategy-tracking-select">
          <span>跟踪策略</span>
          <CustomSelect disabled={!options.length} label="跟踪策略" onChange={onSelectStrategy} options={options} placeholder="选择跟踪策略" value={selectedStrategyId} />
        </div>
        <Button disabled={!selectedStrategyId || isRunPending} icon={<Play size={16} />} onClick={onRun} variant="primary">
          运行策略追踪
        </Button>
        <div className="rule-chip-grid">
          <Badge tone={data.config?.persisted ? 'good' : 'info'}>{data.config?.persisted ? '已固定' : '当前策略'}</Badge>
          <Badge tone="info">{data.strategy?.name || '未选择策略'}</Badge>
          <Badge>{formatChinaDateTime(data.sample_at)}</Badge>
          <Badge tone="good">新命中 {summary.new_count ?? 0}</Badge>
          <Badge>延续 {summary.continued_count ?? 0}</Badge>
        </div>
      </div>
      {strategyMissing ? <EmptyState title="跟踪策略不可用" description="原策略已删除或不可读取，请重新选择一个策略。" /> : null}
      {!strategyMissing && !rows.length ? <EmptyState title="暂无策略命中" description={zeroReason} /> : null}
      {!strategyMissing && rows.length ? (
        <div className="list-stack">
          {rows.map((row) => (
            <StrategyTrackingCard key={row.code} row={row} onOpenTimeline={onOpenTimeline} />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function StrategyTrackingCard({ row, onOpenTimeline }: { row: IntradayStrategyTrackingRow; onOpenTimeline: (row: IntradayCandidate) => void }) {
  const metrics = row.metrics || {};
  const score = row.signal_score ?? metrics.signal_score;
  const trackingLabel = row.tracking_status === 'continued' ? '延续' : '新命中';
  return (
    <article className="rule-card">
      <div className="rule-card-header">
        <strong>
          {row.rank ? `${row.rank}. ` : ''}
          {row.code} · {row.name || '待确认'}
        </strong>
        <div className="rule-chip-grid">
          <Badge tone={row.tracking_status === 'continued' ? 'info' : 'good'}>{trackingLabel}</Badge>
          <Badge tone="info">{formatPercent(row.pct_chg)}</Badge>
        </div>
      </div>
      <div className="metric-row">
        <Metric label="策略分" value={formatRatioStatus(score)} />
        <Metric label="成交额" value={formatMoneyStatus(row.amount ?? metrics.amount)} />
        <Metric label="换手率" value={formatPercentStatus(row.turnover_rate)} />
        <Metric label="RPS20" value={formatRatioStatus(row.rps20)} />
        <Metric label="流通市值" value={formatMoneyStatus(row.float_market_value)} />
      </div>
      <div className="rule-chip-grid">
        {(row.reasons || []).slice(0, 5).map((reason) => (
          <Badge key={reason}>{reason}</Badge>
        ))}
        {row.signal_type ? <Badge tone="purple">{row.signal_type}</Badge> : null}
      </div>
      <div className="rule-card-actions">
        {row.chart_url ? (
          <Button onClick={() => window.open(row.chart_url || '', '_blank', 'noopener,noreferrer')} variant="ghost">
            打开 K 线
          </Button>
        ) : null}
        <Button onClick={() => onOpenTimeline(row)} variant="ghost">
          查看分时轨迹
        </Button>
      </div>
    </article>
  );
}

function TimelineDetail({ data }: { data: import('../../types').IntradayTimeline | null }) {
  const columns = useMemo<Array<ColumnDef<import('../../types').IntradayTimelineRow, unknown>>>(
    () => [
      { header: '时间', accessorKey: 'sample_at', cell: ({ row }) => formatChinaDateTime(row.original.sample_at) },
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

function normalizeEnabledBoards(value?: Partial<Record<IntradayBoardKey, boolean>> | null): Record<IntradayBoardKey, boolean> {
  return {
    anomaly: Boolean(value?.anomaly),
    pullback: Boolean(value?.pullback),
    risk: Boolean(value?.risk),
  };
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <article className="metric-pill">
      <span className="metric-label">{label}</span>
      <div className="metric-value">{value}</div>
    </article>
  );
}
