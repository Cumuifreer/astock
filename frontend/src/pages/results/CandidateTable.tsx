import { useMemo } from 'react';
import type { ColumnDef } from '@tanstack/react-table';
import type { Candidate } from '../../types';
import { Badge } from '../../design/Badge';
import { DataTable } from '../../design/DataTable';
import { formatMoney, formatPercent, formatRatio } from '../../utils/format';

type CandidateTableProps = {
  candidates: Candidate[];
  onSelect: (candidate: Candidate) => void;
};

export function CandidateTable({ candidates, onSelect }: CandidateTableProps) {
  const columns = useMemo<Array<ColumnDef<Candidate, unknown>>>(
    () => [
      { header: '排名', accessorKey: 'rank', cell: ({ row }) => <strong>{row.original.rank}</strong> },
      {
        header: '代码 / 名称',
        cell: ({ row }) => (
          <button className="chip-button" type="button" onClick={() => onSelect(row.original)}>
            {row.original.code} · {row.original.name}
          </button>
        ),
      },
      { header: '总分', accessorKey: 'signal_score', cell: ({ row }) => <Badge tone="info">{formatRatio(row.original.signal_score)}</Badge> },
      { header: '涨跌幅', accessorKey: 'pct_chg', cell: ({ row }) => formatPercent(row.original.pct_chg) },
      { header: '成交额', accessorKey: 'amount', cell: ({ row }) => formatMoney(row.original.amount) },
      { header: 'RPS20', accessorKey: 'rps20', cell: ({ row }) => formatRatio(row.original.rps20) },
      { header: '信号', accessorKey: 'signal_type' },
    ],
    [onSelect],
  );
  return (
    <DataTable data={candidates} columns={columns} />
  );
}
