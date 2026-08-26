"use client";

import { useMemo, useState, type ReactNode } from "react";
import { Search } from "lucide-react";
import { useTranslations } from "next-intl";
import Pagination from "@/components/Pagination";
import AddButton from "@/components/AddButton";

export type DataTableColumn<T> = {
  key: string;
  header: string;
  className?: string;
  render?: (row: T, index: number) => ReactNode;
};

type DataTablePanelProps<T extends Record<string, unknown>> = {
  tableLabel: string;
  columns: DataTableColumn<T>[];
  data: T[];
  searchKeys?: (keyof T)[];
  pageSize?: number;
  onAddNew?: () => void;
  emptyValue?: string;
};

export default function DataTablePanel<T extends Record<string, unknown>>({
  tableLabel,
  columns,
  data,
  searchKeys,
  pageSize = 10,
  onAddNew,
  emptyValue = "--",
}: DataTablePanelProps<T>) {
  const t = useTranslations();
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return data;

    const keys =
      searchKeys ?? (columns.map((column) => column.key) as (keyof T)[]);

    return data.filter((row) =>
      keys.some((key) =>
        String(row[key] ?? "")
          .toLowerCase()
          .includes(query)
      )
    );
  }, [columns, data, search, searchKeys]);

  const total = filtered.length;
  const totalPages = Math.max(1, Math.ceil(total / pageSize) || 1);
  const currentPage = Math.min(page, totalPages);
  const pageRows = filtered.slice(
    (currentPage - 1) * pageSize,
    currentPage * pageSize
  );

  return (
    <div>
      <div className="flex items-center justify-between gap-4 mb-6">
        <h1 className="font-semibold text-[24px] text-black">{tableLabel}</h1>
        <div className="flex items-center gap-3">
          {onAddNew && <AddButton onClick={onAddNew} label={t("add_new")} />}

          <label className="relative w-[240px]">
            <span className="sr-only">{t("search")}</span>
            <input
              type="search"
              value={search}
              onChange={(event) => {
                setSearch(event.target.value);
                setPage(1);
              }}
              placeholder={t("search")}
              className="h-9 w-full rounded-[4px] border border-gray-300 bg-white px-3 pr-9 text-[14px] text-black outline-none placeholder:text-gray-400 focus:border-(--color-yellow)"
            />
            <Search
              size={15}
              className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-gray-400"
            />
          </label>
        </div>
      </div>

      {/* Table */}
      <div className="bg-white rounded-[10px] py-6 shadow-sm">
        <div className="overflow-auto px-4">
          <table className="w-full border-collapse bg-white table-fixed">
            <thead>
              <tr>
                {columns.map((column) => (
                  <th
                    key={column.key}
                    className={`text-left pb-3 px-9 border-b border-gray-200 font-semibold text-black text-[16px] tracking-wider ${column.className ?? ""}`}
                    style={{ width: `${100 / columns.length}%` }}
                  >
                    <div className="truncate" title={column.header}>
                      {column.header}
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {pageRows.length === 0 ? (
                <tr>
                  <td
                    colSpan={columns.length}
                    className="text-center py-10 px-4 text-gray-600"
                  >
                    {t("no_results")}
                  </td>
                </tr>
              ) : (
                pageRows.map((row, index) => {
                  const absoluteIndex = (currentPage - 1) * pageSize + index;
                  return (
                    <tr
                      key={`${absoluteIndex}-${String(row.id ?? index)}`}
                      className={`cursor-pointer transition-colors duration-150 ${index % 2 === 1 ? 'bg-white' : 'bg-gray-50'} hover:bg-gray-100`}
                    >
                      {columns.map((column) => (
                        <td
                          key={column.key}
                          className={`py-2 px-9 align-middle ${column.className ?? ""}`}
                        >
                          <div className="truncate text-[16px]" title={String(column.render ? column.render(row, absoluteIndex) : row[column.key] ?? emptyValue)}>
                            {column.render
                              ? column.render(row, absoluteIndex)
                              : String(row[column.key] ?? emptyValue)}
                          </div>
                        </td>
                      ))}
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        <div className="px-4 py-3 flex justify-end">
          <Pagination
            page={currentPage}
            pageSize={pageSize}
            total={total}
            onPageChange={setPage}
          />
        </div>
      </div>
    </div>
  );
}
