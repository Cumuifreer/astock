import { useQuery } from '@tanstack/react-query';
import { getCapabilities } from '../../api/data';
import type { Capability } from '../../types';
import { EmptyState } from '../../design/EmptyState';
import { LoadingState } from '../../design/LoadingState';
import { normalizeRows } from '../../utils/metrics';
import { CapabilityCard } from './CapabilityCard';

const groups: Array<{ title: string; names: string[] }> = [
  { title: '核心数据', names: ['股票基础信息', '历史 K 线', '当天行情快照', '流通市值', '换手率', 'RPS', '振幅'] },
  { title: '增强数据', names: ['每日指标', '技术因子', '资金流向', '筹码分布', '概念/行业成分'] },
  { title: '事件数据', names: ['涨跌停', '龙虎榜/游资'] },
  { title: '市场上下文', names: ['市场环境', '板块热力', '资讯简报'] },
];

export function DataMapPage() {
  const capabilities = useQuery({ queryKey: ['capabilities'], queryFn: getCapabilities });
  if (capabilities.isLoading) return <LoadingState label="读取数据中心" />;
  const rows = normalizeRows<Capability>(capabilities.data);
  if (!rows.length) return <EmptyState title="数据能力为空" description="刷新数据能力后会按核心、增强、事件、市场上下文分组展示。" />;

  return (
    <div className="page-grid">
      {groups.map((group) => {
        const items = rows.filter((row) => group.names.includes(row.capability));
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
                <CapabilityCard capability={capability} key={capability.capability} />
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}
