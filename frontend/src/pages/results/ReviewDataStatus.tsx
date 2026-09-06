import { useQuery } from '@tanstack/react-query';
import { getReviewOverview } from '../../api/review';
import { Badge } from '../../design/Badge';

export function ReviewDataStatus() {
  const query = useQuery({ queryKey: ['review-overview'], queryFn: getReviewOverview, staleTime: 60_000 });
  if (query.isError) return <p role="alert">数据状态读取失败：{query.error.message}</p>;
  if (!query.data) return <p role="status">读取日线覆盖…</p>;
  const data = query.data;
  const coverage = data.stock_count ? data.covered_count / data.stock_count : 0;
  return <section className="surface pad">
    <div className="section-heading">
      <div><h2>日线数据</h2><p>{data.source} · 所有选股条件使用行情交易日的收盘数据。</p></div>
      <Badge tone={coverage >= 0.95 ? 'good' : 'watch'}>{coverage >= 0.95 ? '覆盖充足' : '覆盖待补齐'}</Badge>
    </div>
    <div className="grid-3">
      <div className="metric-pill"><span className="metric-label">最新行情交易日</span><div className="metric-value">{data.trade_date || '尚未更新'}</div></div>
      <div className="metric-pill"><span className="metric-label">当日覆盖 / 股票池</span><div className="metric-value">{data.covered_count} / {data.stock_count}</div></div>
      <div className="metric-pill"><span className="metric-label">定时更新（北京时间）</span><div className="metric-value">{data.schedule_enabled ? data.schedule_time : '手动更新'}</div></div>
    </div>
    {coverage < 0.95 && <p className="card-copy">部分股票缺少最新日线，选股只使用该交易日有数据的股票。可在“数据与任务”补齐。</p>}
  </section>;
}
