import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { ColumnDef } from '@tanstack/react-table';
import { Database, Search } from 'lucide-react';
import { getCapabilities, getSourceDiagnostics, getStockDetail, getStocks, startUpdate } from '../../api/data';
import type { Capability, SourceDiagnostics, StockDetail, StockRow } from '../../types';
import { Badge } from '../../design/Badge';
import { Button } from '../../design/Button';
import { DataTable } from '../../design/DataTable';
import { Drawer } from '../../design/Drawer';
import { EmptyState } from '../../design/EmptyState';
import { LoadingState } from '../../design/LoadingState';
import { Select } from '../../design/Select';
import { Tabs } from '../../design/Tabs';
import { useToast } from '../../design/Toast';
import { formatDate } from '../../utils/date';
import { formatMoney, formatNumber, formatPercent, formatRatio, shortText } from '../../utils/format';
import { normalizeRows } from '../../utils/metrics';
import { CapabilityCard } from './CapabilityCard';

const groups: Array<{ title: string; names: string[] }> = [
  { title: '核心数据', names: ['股票基础信息', '历史 K 线', '历史行情', '当天行情快照', '今日行情', '流通市值', '换手率', 'RPS', '振幅'] },
  { title: '补充数据', names: ['每日指标', '每日交易指标', '技术因子', '资金流向', '筹码分布', '筹码数据', '概念/行业成分', '题材板块'] },
  { title: '事件数据', names: ['涨跌停', '涨跌停事件', '龙虎榜/游资', '龙虎榜数据'] },
  { title: '市场上下文', names: ['市场环境', '板块热力', '资讯简报'] },
];

const limit = 40;

export function DataMapPage() {
  const [tab, setTab] = useState(() => dataMapTabFromHash());
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('active');
  const [exchange, setExchange] = useState('');
  const [offset, setOffset] = useState(0);
  const [selectedCode, setSelectedCode] = useState<string | null>(null);
  const [backfillingCapability, setBackfillingCapability] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const capabilities = useQuery({ queryKey: ['capabilities'], queryFn: getCapabilities });
  const diagnostics = useQuery({ queryKey: ['source-diagnostics'], queryFn: getSourceDiagnostics });
  const stocks = useQuery({
    queryKey: ['stocks', query, status, exchange, offset],
    queryFn: () => getStocks({ limit, offset, search: query, status, exchange }),
  });
  const detail = useQuery({
    queryKey: ['stock-detail', selectedCode],
    queryFn: () => getStockDetail(selectedCode || ''),
    enabled: Boolean(selectedCode),
  });
  const capabilityRows = normalizeRows<Capability>(capabilities.data);
  const stockRows = stocks.data?.rows || [];
  const total = stocks.data?.total || 0;
  const backfillMutation = useMutation({
    mutationFn: (capability: Capability) => startUpdate({ mode: 'capability_backfill', capability: capability.capability }),
    onMutate: (capability) => setBackfillingCapability(capability.capability),
    onSuccess: (_result, capability) => showToast(`已开始补齐${friendlyCapability(capability.capability)}，可在任务状态查看进度。`, 'success'),
    onSettled: () => {
      setBackfillingCapability(null);
      void queryClient.invalidateQueries({ queryKey: ['capabilities'] });
      void queryClient.invalidateQueries({ queryKey: ['bootstrap'] });
      void queryClient.invalidateQueries({ queryKey: ['runtime-health'] });
      void queryClient.invalidateQueries({ queryKey: ['tasks'] });
    },
  });

  useEffect(() => {
    const syncFromHash = () => setTab(dataMapTabFromHash());
    const handleTabEvent = (event: Event) => {
      const value = (event as CustomEvent<string>).detail;
      if (value === 'warehouse' || value === 'health' || value === 'diagnostics') setTab(value);
    };
    window.addEventListener('hashchange', syncFromHash);
    window.addEventListener('data-map-tab', handleTabEvent);
    return () => {
      window.removeEventListener('hashchange', syncFromHash);
      window.removeEventListener('data-map-tab', handleTabEvent);
    };
  }, []);

  return (
    <div className="page-grid">
      <Tabs
        value={tab}
        onValueChange={setTab}
        items={[
          {
            value: 'warehouse',
            label: '数据仓库',
            content: (
              <StockWarehouse
                exchange={exchange}
                loading={stocks.isLoading}
                offset={offset}
                query={query}
                rows={stockRows}
                selectedCode={selectedCode}
                setExchange={setExchange}
                setOffset={setOffset}
                setQuery={setQuery}
                setSelectedCode={setSelectedCode}
                setStatus={setStatus}
                status={status}
                total={total}
              />
            ),
          },
          {
            value: 'health',
            label: '数据健康',
            content: (
              <DataHealth
                backfillingCapability={backfillingCapability}
                capabilities={capabilityRows}
                loading={capabilities.isLoading}
                onBackfill={(capability) => backfillMutation.mutate(capability)}
              />
            ),
          },
          {
            value: 'diagnostics',
            label: '维护诊断',
            content: <SourceDiagnosticsPanel diagnostics={diagnostics.data} loading={diagnostics.isLoading} />,
          },
        ]}
      />
      <Drawer open={Boolean(selectedCode)} onOpenChange={(open) => !open && setSelectedCode(null)} title={selectedCode || '个股档案'}>
        {detail.isLoading ? <LoadingState label="读取个股档案" /> : <StockProfile detail={detail.data || null} />}
      </Drawer>
    </div>
  );
}

function StockWarehouse({
  rows,
  total,
  query,
  setQuery,
  status,
  setStatus,
  exchange,
  setExchange,
  offset,
  setOffset,
  selectedCode,
  setSelectedCode,
  loading,
}: {
  rows: StockRow[];
  total: number;
  query: string;
  setQuery: (value: string) => void;
  status: string;
  setStatus: (value: string) => void;
  exchange: string;
  setExchange: (value: string) => void;
  offset: number;
  setOffset: (value: number) => void;
  selectedCode: string | null;
  setSelectedCode: (value: string) => void;
  loading: boolean;
}) {
  const columns = useMemo<Array<ColumnDef<StockRow, unknown>>>(
    () => [
      {
        header: '股票',
        cell: ({ row }) => (
          <div className="warehouse-stock-cell">
            <Database size={15} />
            <div>
              <strong>
                {row.original.name}
                {row.original.status_label === '非活跃' ? <span className="stock-status-badge inactive">非活跃</span> : null}
              </strong>
              <span className="mono">
                {row.original.code} · {row.original.exchange} · {boardLabel(row.original.board)}
              </span>
            </div>
          </div>
        ),
      },
      { header: '最新价', cell: ({ row }) => formatNumber(row.original.latest_price, 2) },
      { header: '涨跌幅', cell: ({ row }) => <span className={Number(row.original.pct_chg || 0) >= 0 ? 'text-good' : 'text-risk'}>{formatPercent(row.original.pct_chg)}</span> },
      { header: '成交额', cell: ({ row }) => formatMoney(row.original.amount) },
      { header: '换手率', cell: ({ row }) => formatPercent(row.original.turnover_rate) },
      { header: '流通市值', cell: ({ row }) => formatMoney(row.original.float_market_value) },
      { header: '题材', cell: ({ row }) => formatNumber(row.original.concept_count) },
      {
        header: '档案',
        cell: ({ row }) => (
          <Button onClick={() => setSelectedCode(row.original.code)} variant={selectedCode === row.original.code ? 'secondary' : 'ghost'}>
            打开
          </Button>
        ),
      },
    ],
    [selectedCode, setSelectedCode],
  );
  return (
    <section className="surface pad">
      <div className="section-heading">
        <div>
          <h2>本地股票仓</h2>
          <p>股票列表、活跃口径、搜索和个股档案保留在数据中心主视图。</p>
        </div>
        <Badge tone="info">{formatNumber(total)} 只</Badge>
      </div>
      <div className="data-toolbar">
        <label className="search-box">
          <Search size={15} />
          <input
            placeholder="代码 / 名称"
            value={query}
            onChange={(event) => {
              setOffset(0);
              setQuery(event.target.value);
            }}
          />
        </label>
        <Select
          label="股票状态"
          value={status}
          onChange={(value) => {
            setOffset(0);
            setStatus(value);
          }}
          options={[
            { value: 'active', label: '活跃' },
            { value: 'inactive', label: '非活跃' },
            { value: 'all', label: '全部' },
          ]}
        />
        <Select
          label="交易所"
          value={exchange || 'all'}
          onChange={(value) => {
            setOffset(0);
            setExchange(value === 'all' ? '' : value);
          }}
          options={[
            { value: 'all', label: '全部市场' },
            { value: 'SH', label: '上交所' },
            { value: 'SZ', label: '深交所' },
            { value: 'BJ', label: '北交所' },
          ]}
        />
      </div>
      {loading ? (
        <LoadingState label="读取股票仓" />
      ) : rows.length ? (
        <>
          <DataTable data={rows} columns={columns} estimateRowHeight={72} />
          <div className="pager">
            <span>{formatNumber(offset + 1)} - {formatNumber(Math.min(offset + limit, total))} / {formatNumber(total)}</span>
            <Button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - limit))} variant="ghost">
              上一页
            </Button>
            <Button disabled={offset + limit >= total} onClick={() => setOffset(offset + limit)} variant="ghost">
              下一页
            </Button>
          </div>
        </>
      ) : (
        <EmptyState title="暂无股票数据" description="同步今日数据或刷新股票池后，这里会显示本地仓库。" />
      )}
    </section>
  );
}

function DataHealth({
  capabilities,
  loading,
  onBackfill,
  backfillingCapability,
}: {
  capabilities: Capability[];
  loading: boolean;
  onBackfill: (capability: Capability) => void;
  backfillingCapability: string | null;
}) {
  if (loading) return <LoadingState label="读取数据健康" />;
  return (
    <div className="page-grid">
      {groups.map((group) => {
        const items = capabilities.filter((row) => group.names.includes(row.capability));
        if (!items.length) return null;
        return (
          <section className="surface pad" key={group.title}>
            <div className="section-heading">
              <div>
                <h2>{group.title}</h2>
                <p>数据新不新、覆盖够不够、能不能参与分析、如何补齐。</p>
              </div>
            </div>
            <div className="grid-3">
              {items.map((capability) => (
                <CapabilityCard
                  backfilling={backfillingCapability === capability.capability}
                  capability={capability}
                  key={capability.capability}
                  onBackfill={onBackfill}
                />
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}

function SourceDiagnosticsPanel({ diagnostics, loading }: { diagnostics?: SourceDiagnostics; loading: boolean }) {
  const healthCards = useMemo(
    () => [
      ['数据配置', diagnostics?.tushare_token_configured ? '已配置' : '未配置', diagnostics?.last_tushare_error],
      ['今日行情', statusLabel(diagnostics?.realtime_status), userSourceLabel(diagnostics?.last_snapshot_source)],
      ['历史行情', statusLabel(diagnostics?.history_status), userSourceLabel(diagnostics?.last_history_source)],
      ['补充交易数据', statusLabel(diagnostics?.enrichment_status), diagnostics?.tushare_http_url_configured ? '已配置' : '缺少中转配置'],
    ],
    [diagnostics],
  );
  if (loading) return <LoadingState label="读取数据源诊断" />;
  return (
    <section className="surface pad">
      <div className="section-heading">
        <div>
          <h2>数据源诊断</h2>
          <p>维护者可在这里查看配置、最近失败原因和数据切换情况。</p>
        </div>
      </div>
      <div className="grid-4">
        {healthCards.map(([label, value, detail]) => (
          <div className="metric-pill" key={String(label)}>
            <span className="metric-label">{String(label)}</span>
            <div className="metric-value" style={{ fontSize: 16 }}>{String(value || '暂无')}</div>
            <small>{String(detail || '')}</small>
          </div>
        ))}
      </div>
    </section>
  );
}

function dataMapTabFromHash() {
  if (window.location.hash.includes('tab=diagnostics')) return 'diagnostics';
  return window.location.hash.includes('tab=health') ? 'health' : 'warehouse';
}

function StockProfile({ detail }: { detail: StockDetail | null }) {
  if (!detail?.basic) return <EmptyState title="暂无个股档案" description="本地仓库还没有这只股票的详情。" />;
  const basic = detail.basic;
  const daily = detail.daily_basic || {};
  const factor = detail.factor || {};
  const moneyflow = detail.moneyflow || {};
  const concepts = detail.concepts || [];
  const limitEvents = detail.limit_events || [];
  const topEvents = detail.top_events || [];
  return (
    <div className="list-stack">
      <section className="profile-metrics">
        <Metric label="最新价" value={formatNumber(basic.latest_price, 2)} detail={formatPercent(basic.pct_chg)} />
        <Metric label="量比" value={formatRatio(daily.volume_ratio ?? basic.volume_ratio)} detail={`换手 ${formatPercent(daily.turnover_rate ?? basic.turnover_rate)}`} />
        <Metric label="主力净额" value={formatMoney(moneyflow.main_net_amount)} detail={`净流 ${formatMoney(moneyflow.net_mf_amount)}`} />
        <Metric label="流通市值" value={formatMoney(daily.circ_mv ?? basic.float_market_value)} detail={formatDate(basic.latest_history_date)} />
      </section>
      <ProfileBlock title="技术因子" rows={[['MACD', factor.macd], ['KDJ', `${shortValue(factor.kdj_k)} / ${shortValue(factor.kdj_d)} / ${shortValue(factor.kdj_j)}`], ['RSI6', factor.rsi_6], ['BOLL', `${shortValue(factor.boll_upper)} / ${shortValue(factor.boll_mid)} / ${shortValue(factor.boll_lower)}`]]} />
      <ProfileBlock title="题材成分" rows={concepts.slice(0, 8).map((item) => [formatDate(item.updated_at), `${shortText(item.con_name || item.name)} · ${shortText(item.con_code || item.code)}`])} />
      <ProfileBlock title="涨跌停 / 炸板" rows={limitEvents.slice(0, 6).map((item) => [formatDate(item.trade_date), `${shortText(item.limit_type)} · 开板 ${formatNumber(item.open_times)} 次`])} />
      <ProfileBlock title="龙虎榜 / 游资" rows={topEvents.slice(0, 6).map((item) => [formatDate(item.trade_date), `${formatMoney(item.net_amount)} · ${shortText(item.reason || item.hm_name)}`])} />
    </div>
  );
}

function Metric({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <div className="metric-pill">
      <span className="metric-label">{label}</span>
      <div className="metric-value" style={{ fontSize: 16 }}>{value}</div>
      <small>{detail}</small>
    </div>
  );
}

function ProfileBlock({ title, rows }: { title: string; rows: Array<[unknown, unknown]> }) {
  return (
    <section className="surface-subtle">
      <h3>{title}</h3>
      {rows.length ? (
        <div className="profile-row-list">
          {rows.map(([label, value], index) => (
            <div className="split-row" key={`${title}-${index}`}>
              <span>{String(label || '暂无记录')}</span>
              <strong>{String(value || '暂无记录')}</strong>
            </div>
          ))}
        </div>
      ) : (
        <p className="card-copy">暂无记录</p>
      )}
    </section>
  );
}

function boardLabel(value: unknown) {
  const labels: Record<string, string> = { main: '主板', gem: '创业板', star: '科创板', bj: '北交所' };
  return labels[String(value || '')] || String(value || '待确认');
}

function shortValue(value: unknown) {
  return value === null || value === undefined || value === '' ? '暂不可用' : String(value);
}

function statusLabel(value: unknown) {
  const labels: Record<string, string> = {
    normal: '正常',
    failed: '失败',
    fallback: '回退',
    partial: '部分失败',
    unknown: '未知',
  };
  return labels[String(value || '')] || String(value || '未知');
}

function userSourceLabel(value: unknown) {
  const text = String(value || '');
  if (!text) return '';
  if (/daily|snapshot|实时|新浪/i.test(text)) return '今日行情';
  if (/history|historical|qfq|历史/i.test(text)) return '历史行情';
  return '数据源切换';
}

function friendlyCapability(value: string) {
  return value
    .replace('历史 K 线', '历史行情')
    .replace('当天行情快照', '今日行情')
    .replace('每日指标', '每日交易指标')
    .replace('概念/行业成分', '题材板块')
    .replace('龙虎榜/游资', '龙虎榜数据')
    .replace('涨跌停', '涨跌停事件');
}
