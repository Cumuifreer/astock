import { useMemo, useState } from 'react';
import ReactECharts from 'echarts-for-react';
import type { SectorHeatNode } from '../../api/market';
import { Segmented } from '../../design/Segmented';
import { EmptyState } from '../../design/EmptyState';
import { formatMoney, formatPercent, toNumber } from '../../utils/format';

type HeatMode = 'concept' | 'industry' | 'money' | 'limit';

type SectorHeatmapProps = {
  sectors: SectorHeatNode[];
};

export function SectorHeatmap({ sectors }: SectorHeatmapProps) {
  const [mode, setMode] = useState<HeatMode>('concept');
  const filtered = sectors
    .filter((sector) => {
      const type = sector.type || sector.sector_type;
      if (mode === 'industry') return type === 'industry';
      if (mode === 'concept') return type !== 'industry';
      return true;
    })
    .slice(0, 36);
  const option = useMemo(
    () => ({
      tooltip: {
        formatter: (params: { data?: { raw?: SectorHeatNode } }) => {
          const raw = params.data?.raw || {};
          return [
            `<strong>${raw.name || raw.sector_name || '--'}</strong>`,
            `涨跌幅：${formatPercent(raw.pct_chg)}`,
            `净流入：${formatMoney(raw.net_amount)}`,
            `涨停数：${raw.limit_up_count ?? '--'}`,
            `领涨股：${raw.leader_name || raw.leader_code || '--'}`,
          ].join('<br/>');
        },
      },
      series: [
        {
          type: 'treemap',
          roam: false,
          nodeClick: false,
          breadcrumb: { show: false },
          label: { color: '#111827', formatter: '{b}' },
          upperLabel: { show: false },
          data: filtered.map((sector) => {
            const heat = toNumber(sector.heat_score) || 0;
            const value = mode === 'money' ? Math.abs(toNumber(sector.net_amount) || 1) : mode === 'limit' ? toNumber(sector.limit_up_count) || 1 : toNumber(sector.amount) || toNumber(sector.company_count) || 1;
            return {
              name: sector.name || sector.sector_name || sector.code || sector.sector_code || '--',
              value,
              raw: sector,
              itemStyle: {
                color: heat >= 70 ? '#dcfce7' : heat >= 45 ? '#fef3c7' : '#e0f2fe',
                borderColor: '#ffffff',
                borderWidth: 2,
              },
            };
          }),
        },
      ],
    }),
    [filtered, mode],
  );

  return (
    <section className="surface pad">
      <div className="section-heading">
        <div>
          <h2>板块热力图</h2>
          <p>面积看成交额或数量，颜色看热度分，tooltip 展示资金、涨停扩散和领涨股。</p>
        </div>
        <Segmented
          value={mode}
          onChange={setMode}
          options={[
            { value: 'concept', label: '概念' },
            { value: 'industry', label: '行业' },
            { value: 'money', label: '资金' },
            { value: 'limit', label: '涨停扩散' },
          ]}
        />
      </div>
      {filtered.length ? (
        <>
          <ReactECharts option={option} style={{ height: 340, width: '100%' }} />
          <div className="heatmap-grid" style={{ marginTop: 12 }}>
            {filtered.slice(0, 8).map((sector) => (
              <div className="heat-tile" key={`${sector.sector_code || sector.code}-${sector.sector_type || sector.type}`}>
                <strong>{sector.name || sector.sector_name || '--'}</strong>
                <span className="card-copy">
                  {formatPercent(sector.pct_chg)} · {formatMoney(sector.net_amount)}
                </span>
              </div>
            ))}
          </div>
        </>
      ) : (
        <EmptyState title="板块热力等待同步" description="同步今日数据会写入 market_sector_daily，并在这里展示概念、行业、资金和涨停扩散。" />
      )}
    </section>
  );
}
