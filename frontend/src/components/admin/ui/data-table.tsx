import type { ReactNode } from "react";

export type AdminColumn<T> = {
  key: string;
  header: string;
  cell: (row: T) => ReactNode;
  numeric?: boolean;
};

export function AdminDataTable<T>({
  rows,
  columns,
  rowKey,
  caption,
  emptyTitle,
  emptyDescription,
}: {
  rows: T[];
  columns: AdminColumn<T>[];
  rowKey: (row: T) => string;
  caption: string;
  emptyTitle: string;
  emptyDescription: string;
}) {
  if (!rows.length) {
    return (
      <div className="rounded-2xl border border-dashed border-brand-purple/25 bg-white p-10 text-center">
        <h2 className="text-xl font-extrabold">{emptyTitle}</h2>
        <p className="mt-2 text-sm text-muted">{emptyDescription}</p>
      </div>
    );
  }
  return (
    <div className="overflow-hidden rounded-2xl border border-brand-purple/12 bg-white shadow-sm">
      <div className="hidden overflow-x-auto md:block">
        <table className="w-full border-collapse text-left text-sm">
          <caption className="sr-only">{caption}</caption>
          <thead className="bg-deep-indigo text-white">
            <tr>
              {columns.map((column) => (
                <th
                  key={column.key}
                  className={`px-4 py-3 font-black ${column.numeric ? "text-right" : "text-left"}`}
                  scope="col"
                >
                  {column.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-brand-purple/8">
            {rows.map((row) => (
              <tr key={rowKey(row)} className="align-top hover:bg-soft-lavender/35">
                {columns.map((column) => (
                  <td
                    key={column.key}
                    className={`px-4 py-3.5 ${column.numeric ? "text-right tabular-nums" : ""}`}
                  >
                    {column.cell(row)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ul className="divide-y divide-brand-purple/10 md:hidden" aria-label={caption}>
        {rows.map((row) => (
          <li key={rowKey(row)} className="grid gap-3 p-4">
            {columns.map((column) => (
              <div
                key={column.key}
                className="grid grid-cols-[minmax(7rem,42%)_1fr] items-start gap-3"
              >
                <span className="text-xs font-black tracking-wide text-muted uppercase">
                  {column.header}
                </span>
                <div
                  className={`min-w-0 text-sm ${column.numeric ? "text-right tabular-nums" : ""}`}
                >
                  {column.cell(row)}
                </div>
              </div>
            ))}
          </li>
        ))}
      </ul>
    </div>
  );
}
