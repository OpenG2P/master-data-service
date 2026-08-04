"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useTranslations } from "next-intl";
import Pagination from "@/components/Pagination";
import type {
  ChildrenCacheEntry,
  GeoLevelValue,
  GeoTreeNode,
} from "@/types/geo";
import { getValueLabel } from "@/shared/utils/geoHierarchy";

type GeoChildrenTableProps = {
  selected: GeoTreeNode | null;
  childrenEntry: ChildrenCacheEntry | undefined;
  onSelect: (value: GeoLevelValue) => void;
  onEdit: (value: GeoLevelValue) => void;
  onDelete: (value: GeoLevelValue) => void;
  getChildCount: (value: GeoLevelValue) => number | null;
  footerActions?: ReactNode;
};

export default function GeoChildrenTable({
  selected,
  childrenEntry,
  onSelect,
  onEdit,
  onDelete,
  getChildCount,
  footerActions,
}: GeoChildrenTableProps) {
  const t = useTranslations();
  const [page, setPage] = useState(1);
  const [sortKey, setSortKey] = useState<"name" | "children">("name");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const pageSize = 10;

  const rows = childrenEntry?.values ?? [];
  const loading = Boolean(childrenEntry?.loading);
  const error = childrenEntry?.error ?? null;

  useEffect(() => {
    setPage(1);
  }, [selected?.key, rows[0]?.level_value_id, rows.length]);

  const filtered = useMemo(() => {
    const sorted = [...rows].sort((a, b) => {
      let cmp = 0;
      if (sortKey === "name") {
        cmp = getValueLabel(a).localeCompare(getValueLabel(b));
      } else {
        cmp = (getChildCount(a) ?? -1) - (getChildCount(b) ?? -1);
      }
      return sortDir === "asc" ? cmp : -cmp;
    });

    return sorted;
  }, [getChildCount, rows, sortDir, sortKey]);

  const total = filtered.length;
  const totalPages = Math.max(1, Math.ceil(total / pageSize) || 1);
  const currentPage = Math.min(page, totalPages);
  const pageRows = filtered.slice(
    (currentPage - 1) * pageSize,
    currentPage * pageSize
  );
  const showPagination = Boolean(selected) && !loading && !error && total > 0;
  const showFooter = Boolean(footerActions) || showPagination;

  const toggleSort = (key: typeof sortKey) => {
    if (sortKey === key) {
      setSortDir((dir) => (dir === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
    setPage(1);
  };

  const sortMarker = (key: typeof sortKey) =>
    sortKey === key ? (sortDir === "asc" ? " ↑" : " ↓") : "";

  const footer = showFooter ? (
    <div className="flex h-auto shrink-0 flex-wrap items-center justify-between gap-2 border-t border-[#5A5A5A] px-4 py-2">
      <div className="flex w-fit flex-wrap items-center gap-2">
        {footerActions}
      </div>
      {showPagination ? (
        <div className="ml-auto w-fit">
          <Pagination
            page={currentPage}
            pageSize={pageSize}
            total={total}
            onPageChange={setPage}
          />
        </div>
      ) : null}
    </div>
  ) : null;

  if (!selected) {
    return (
      <div className="absolute inset-0 flex flex-col">
        <div className="shrink-0 border-b border-[#5A5A5A] px-4 py-2.5 text-start font-normal text-[16px] leading-none tracking-normal text-[#F4BB1B]">
          {t("geo_children")}
        </div>
        <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-2 px-6 text-center">
          <p className="font-normal text-[16px] leading-none tracking-normal text-white">
            {t("geo_select_node_title")}
          </p>
          <p className="max-w-sm text-[14px] text-white/45">
            {t("geo_select_node_hint")}
          </p>
        </div>
        {footer}
      </div>
    );
  }

  return (
    <div className="absolute inset-0 flex flex-col">
      <div className="shrink-0 border-b border-[#5A5A5A] px-4 py-2.5 text-start font-normal text-[16px] leading-none tracking-normal text-[#F4BB1B]">
        {t("geo_children")}
      </div>

      <div className="min-h-0 flex-1 overflow-x-hidden overflow-y-auto px-4 pt-0 pb-2 [scrollbar-gutter:stable]">
        {loading ? (
          <p className="px-1 py-8 text-center text-[14px] text-white/45">
            {t("loading")}
          </p>
        ) : error ? (
          <p className="px-1 py-8 text-center text-[14px] text-red-300">{error}</p>
        ) : pageRows.length === 0 ? (
          <div className="flex flex-col items-center gap-3 px-1 py-10 text-center">
            <p className="text-[14px] text-white/45">{t("geo_no_level_values")}</p>
          </div>
        ) : (
          <table className="w-full table-fixed border-collapse text-left">
            <thead className="sticky top-0 bg-black">
              <tr className="border-b border-[#3A3A3A]">
                <th className="w-[45%] px-2 py-2 text-[13px] font-semibold text-[#F4BB1B]">
                  <button
                    type="button"
                    className="cursor-pointer"
                    onClick={() => toggleSort("name")}
                  >
                    {t("col_name")}
                    {sortMarker("name")}
                  </button>
                </th>
                <th className="w-[25%] px-2 py-2 text-[13px] font-semibold text-[#F4BB1B]">
                  <button
                    type="button"
                    className="cursor-pointer"
                    onClick={() => toggleSort("children")}
                  >
                    {t("geo_child_count")}
                    {sortMarker("children")}
                  </button>
                </th>
                <th className="w-[30%] px-2 py-2 text-[13px] font-semibold text-[#F4BB1B]">
                  {t("col_actions")}
                </th>
              </tr>
            </thead>
            <tbody>
              {pageRows.map((row) => {
                const count = getChildCount(row);
                return (
                  <tr
                    key={row.level_value_id}
                    className="cursor-pointer border-b border-[#3A3A3A] hover:bg-white/[0.03]"
                    onClick={() => onSelect(row)}
                  >
                    <td className="truncate px-2 py-2.5 font-normal text-[16px] leading-none tracking-normal text-white">
                      {getValueLabel(row)}
                    </td>
                    <td className="px-2 py-2.5 font-normal text-[16px] leading-none tracking-normal text-white/80">
                      {count === null ? "—" : count}
                    </td>
                    <td className="px-2 py-2.5 font-normal text-[16px] leading-none tracking-normal">
                      <div className="flex flex-wrap gap-3">
                        <button
                          type="button"
                          onClick={(event) => {
                            event.stopPropagation();
                            onEdit(row);
                          }}
                          className="cursor-pointer text-white/80 hover:text-[#F4BB1B] hover:underline"
                        >
                          {t("edit")}
                        </button>
                        <button
                          type="button"
                          onClick={(event) => {
                            event.stopPropagation();
                            onDelete(row);
                          }}
                          className="cursor-pointer text-red-300 hover:underline"
                        >
                          {t("delete")}
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {footer}
    </div>
  );
}
