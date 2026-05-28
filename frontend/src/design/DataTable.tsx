import { Fragment, useMemo, useRef } from 'react';
import type { ReactNode } from 'react';
import { flexRender, getCoreRowModel, useReactTable } from '@tanstack/react-table';
import type { ColumnDef } from '@tanstack/react-table';
import { useVirtualizer } from '@tanstack/react-virtual';
import { EmptyState } from './EmptyState';

type DataTableProps<TData extends object> = {
  data: TData[];
  columns: Array<ColumnDef<TData, unknown>>;
  empty?: ReactNode;
  estimateRowHeight?: number;
  renderSubRow?: (row: TData) => ReactNode;
};

export function DataTable<TData extends object>({ data, columns, empty, estimateRowHeight = 48, renderSubRow }: DataTableProps<TData>) {
  const parentRef = useRef<HTMLDivElement | null>(null);
  const table = useReactTable({
    data,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });
  const rows = table.getRowModel().rows;
  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => estimateRowHeight,
    overscan: 8,
  });
  const virtualItems = virtualizer.getVirtualItems();
  const padding = useMemo(() => {
    const first = virtualItems[0];
    const last = virtualItems[virtualItems.length - 1];
    return {
      top: first ? first.start : 0,
      bottom: last ? Math.max(0, virtualizer.getTotalSize() - last.end) : 0,
    };
  }, [virtualItems, virtualizer]);

  if (!data.length) {
    return <>{empty || <EmptyState />}</>;
  }

  return (
    <div className="data-table-wrap" ref={parentRef} style={{ maxHeight: 560 }}>
      <table className="data-table">
        <thead>
          {table.getHeaderGroups().map((headerGroup) => (
            <tr key={headerGroup.id}>
              {headerGroup.headers.map((header) => (
                <th key={header.id}>{header.isPlaceholder ? null : flexRender(header.column.columnDef.header, header.getContext())}</th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {padding.top > 0 ? (
            <tr>
              <td style={{ height: padding.top }} colSpan={columns.length} />
            </tr>
          ) : null}
          {virtualItems.map((virtualRow) => {
            const row = rows[virtualRow.index];
            const subRow = renderSubRow?.(row.original);
            return (
              <Fragment key={row.id}>
                <tr>
                  {row.getVisibleCells().map((cell) => (
                    <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>
                  ))}
                </tr>
                {subRow ? (
                  <tr className="data-table-subrow">
                    <td colSpan={columns.length}>{subRow}</td>
                  </tr>
                ) : null}
              </Fragment>
            );
          })}
          {padding.bottom > 0 ? (
            <tr>
              <td style={{ height: padding.bottom }} colSpan={columns.length} />
            </tr>
          ) : null}
        </tbody>
      </table>
    </div>
  );
}
