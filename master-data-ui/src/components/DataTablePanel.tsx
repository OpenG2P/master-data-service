"use client";

import { useMemo, useState, type ReactNode } from "react";
import { Search } from "lucide-react";
import { useTranslations } from "next-intl";
import Pagination from "@/components/Pagination";

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
    <section className="flex min-h-0 flex-1 flex-col overflow-hidden bg-black p-5 pb-12 text-white">
      <div className="relative flex min-h-0 flex-1 flex-col border border-[#5A5A5A]">
        {/* Label | Add New | Search */}
        <div className="flex shrink-0 flex-wrap items-center justify-between gap-4 border-b border-[#5A5A5A] px-4 py-4">
          <h1 className="text-[18px] font-semibold text-white">{tableLabel}</h1>

          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={onAddNew}
              className="inline-flex h-9 cursor-pointer items-center gap-2 rounded-[10px] bg-[#F4BB1B] px-4 text-[14px] font-semibold text-black"
            >
              {t("add_new")}
              <span className="flex h-[18px] w-[18px] items-center justify-center rounded-[10px] bg-white text-[14px] font-bold leading-none text-black">
                +
              </span>
            </button>

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
                className="h-9 w-full rounded-[4px] border border-[#5A5A5A] bg-black px-3 pr-9 text-[14px] text-white outline-none placeholder:text-[#8A8A8A] focus:border-[#F4BB1B]"
              />
              <Search
                size={15}
                className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-white"
              />
            </label>
          </div>
        </div>

        {/* Table */}
        <div className="relative min-h-0 flex-1">
          <div className="h-full overflow-auto px-4 pb-10 pt-2">
            <table className="w-full border-collapse text-left">
              <thead>
                <tr className="border-b border-[#3A3A3A]">
                  {columns.map((column) => (
                    <th
                      key={column.key}
                      className={`px-3 py-3 text-[14px] font-semibold text-[#F4BB1B] ${column.className ?? ""}`}
                    >
                      {column.header}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {pageRows.length === 0 ? (
                  <tr>
                    <td
                      colSpan={columns.length}
                      className="px-3 py-10 text-center text-[14px] text-white/45"
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
                        className="border-b border-[#3A3A3A]"
                      >
                        {columns.map((column) => (
                          <td
                            key={column.key}
                            className={`px-3 py-3 text-[14px] text-white ${column.className ?? ""}`}
                          >
                            {column.render
                              ? column.render(row, absoluteIndex)
                              : String(row[column.key] ?? emptyValue)}
                          </td>
                        ))}
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>

          <div className="absolute bottom-0 right-3 z-10 flex translate-y-1/2 items-center bg-black pl-3 pr-1">
            <Pagination
              page={currentPage}
              pageSize={pageSize}
              total={total}
              onPageChange={setPage}
            />
          </div>
        </div>
      </div>
    </section>
  );
}
