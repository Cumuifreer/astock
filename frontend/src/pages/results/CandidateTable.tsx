import { useMemo } from 'react';
import type { ColumnDef } from '@tanstack/react-table';
import type { Candidate } from '../../types';
import { Badge } from '../../design/Badge';
import { DataTable } from '../../design/DataTable';
import { formatMoney, formatPercent, formatRatio } from '../../utils/format';

type CandidateTableProps = {
  candidates: Candidate[];
  observedCodes: Set<string>;
  selectedCode?: string;
  onSelect: (candidate: Candidate) => void;
};

export function CandidateTable({ candidates, observedCodes, selectedCode, onSelect }: CandidateTableProps) {
  const columns = useMemo<Array<ColumnDef<Candidate, unknown>>>(
    () => [
      { header: '排名', accessorKey: 'rank', cell: ({ row }) => <strong>{row.original.rank}</strong> },
      {
        header: '代码 / 名称',
        cell: ({ row }) => {
          const isSelected = row.original.code === selectedCode;
          return (
            <button className={`chip-button ${isSelected ? 'active' : ''}`.trim()} type="button" aria-pressed={isSelected} onClick={() => onSelect(row.original)}>
              {row.original.code} · {row.original.name}
            </button>
          );
        },
      },
      { header: '总分', accessorKey: 'signal_score', cell: ({ row }) => <Badge tone="info">{formatRatio(row.original.signal_score)}</Badge> },
      { header: '涨跌幅', accessorKey: 'pct_chg', cell: ({ row }) => formatPercent(row.original.pct_chg) },
      { header: '成交额', accessorKey: 'amount', cell: ({ row }) => formatMoney(row.original.amount) },
      { header: 'RPS20', accessorKey: 'rps20', cell: ({ row }) => formatRatio(row.original.rps20) },
      {
        header: '标签',
        cell: ({ row }) => (
          <div className="rule-chip-grid">
            {candidateTags(row.original, observedCodes.has(row.original.code)).map((tag) => (
              <Badge key={tag} tone={tag === '风险' ? 'risk' : tag === '已观察' ? 'watch' : 'good'}>
                {tag}
              </Badge>
            ))}
          </div>
        ),
      },
    ],
    [observedCodes, onSelect, selectedCode],
  );
  return (
    <DataTable
      data={candidates}
      columns={columns}
      getRowClassName={(candidate) => candidate.code === selectedCode ? 'selected-row' : undefined}
      onRowClick={onSelect}
    />
  );
}

function candidateTags(candidate: Candidate, observed: boolean): string[] {
  const tags: string[] = [];
  if (Number(candidate.signal_score || 0) >= 80 || Number(candidate.rps20 || 0) >= 85) tags.push('强势');
  if (Number(candidate.metrics?.volume_ratio || 0) >= 1.5 || Number(candidate.amount || 0) >= 100000000) tags.push('放量');
  if (candidate.metrics?.strong_theme_name || candidate.metrics?.theme_sync_score) tags.push('题材');
  if (Array.isArray(candidate.metrics?.risk_flags) ? candidate.metrics.risk_flags.length : Number(candidate.amplitude || 0) >= 0.08) tags.push('风险');
  if (observed) tags.push('已观察');
  return tags.length ? tags.slice(0, 4) : ['观察'];
}
