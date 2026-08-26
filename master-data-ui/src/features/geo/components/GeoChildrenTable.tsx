"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useTranslations } from "next-intl";
import Pagination from "@/components/Pagination";
import DeleteButton from "@/components/DeleteButton";
import EditButton from "@/components/EditButton";
import type {
  ChildrenCacheEntry,
  GeoLevelValue,
  GeoTreeNode,
} from "../types";
import { getValueLabel } from "../utils";

type GeoChildrenTableProps = {
  selected: GeoTreeNode | null;
  title?: string;
  subtitle?: string | null;
  childrenEntry: ChildrenCacheEntry | undefined;
  onSelect: (value: GeoLevelValue) => void;
  onEdit: (value: GeoLevelValue) => void;
  onDelete: (value: GeoLevelValue) => void;
  getChildCount: (value: GeoLevelValue) => number | null;
  getLevelLabel?: (value: GeoLevelValue) => string | null;
  footerActions?: ReactNode;
  deletingValueId?: string | null;
};

export default function GeoChildrenTable({
  selected,
  title,
  subtitle,
  childrenEntry,
  onSelect,
  onEdit,
  onDelete,
  getChildCount,
  getLevelLabel: getRowLevelLabel,
  footerActions,
  deletingValueId,
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
    <div className="flex h-auto shrink-0 flex-wrap items-center justify-between gap-2 border-t border-gray-200 px-4 py-2">
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
        <div className="shrink-0 border-b border-gray-200 px-4 py-2.5">
          <div className="text-[16px] leading-none tracking-normal text-black">
            {title || t("geo_children")}
          </div>
          {subtitle ? (
            <p className="mt-1.5 text-[12px] text-gray-400">{subtitle}</p>
          ) : null}
        </div>
        <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-2 px-6 text-center">
          <p className="text-[16px] leading-none tracking-normal text-black">
            {t("geo_select_node_title")}
          </p>
          <p className="max-w-sm text-[16px] text-gray-400">
            {t("geo_select_node_hint")}
          </p>
        </div>
        {footer}
      </div>
    );
  }

  return (
    <div className="absolute inset-0 flex flex-col">
      <div className="shrink-0 border-b border-gray-200 px-4 py-2.5">
        <div className="text-[16px] leading-none tracking-normal text-black">
          {title || t("geo_children")}
        </div>
        {subtitle ? (
          <p className="mt-1.5 text-[12px] text-gray-400">{subtitle}</p>
        ) : null}
      </div>

      <div className="min-h-0 flex-1 overflow-x-hidden overflow-y-auto px-4 pt-0 pb-2 [scrollbar-gutter:stable]">
        {loading ? (
          <div className="flex items-center justify-center py-8 bg-white">
            <img
              src="/loading.gif"
              alt="Loading"
              className="w-12 h-12 rounded-[10px]"
            />
          </div>
        ) : error ? (
          <p className="px-1 py-8 text-center text-[16px] text-red-500">{error}</p>
        ) : pageRows.length === 0 ? (
          <div className="flex flex-col items-center gap-3 px-1 py-10 text-center">
            <p className="text-[16px] text-gray-400">{t("geo_no_level_values")}</p>
          </div>
        ) : (
          <table className="w-full border-collapse bg-white table-fixed">
            <thead>
              <tr>
                <th className="text-left py-3 px-9 border-b border-gray-200 font-semibold text-black text-[16px] tracking-wider" style={{ width: "45%" }}>
                  <button
                    type="button"
                    className="cursor-pointer"
                    onClick={() => toggleSort("name")}
                  >
                    {t("col_name")}
                    {sortMarker("name")}
                  </button>
                </th>
                {getRowLevelLabel ? (
                  <th className="text-left py-3 px-9 border-b border-gray-200 font-semibold text-black text-[16px] tracking-wider" style={{ width: "20%" }}>
                    {t("geo_level")}
                  </th>
                ) : null}
                <th className="text-left py-3 px-9 border-b border-gray-200 font-semibold text-black text-[16px] tracking-wider" style={{ width: "25%" }}>
                  <button
                    type="button"
                    className="cursor-pointer"
                    onClick={() => toggleSort("children")}
                  >
                    {t("geo_child_count")}
                    {sortMarker("children")}
                  </button>
                </th>
                <th className="text-left py-3 px-9 border-b border-gray-200 font-semibold text-black text-[16px] tracking-wider" style={{ width: "30%" }}>
                  {t("col_actions")}
                </th>
              </tr>
            </thead>
            <tbody>
              {pageRows.map((row, index) => {
                const count = getChildCount(row);
                return (
                  <tr
                    key={row.level_value_id}
                    className={`cursor-pointer transition-colors duration-150 ${index % 2 === 1 ? 'bg-white' : 'bg-gray-50'} hover:bg-gray-100`}
                    onClick={() => onSelect(row)}
                  >
                    <td className="py-2 px-9 align-middle">
                      <div className="truncate text-[16px] text-black" title={getValueLabel(row)}>
                        {getValueLabel(row)}
                      </div>
                    </td>
                    {getRowLevelLabel ? (
                      <td className="py-2 px-9 align-middle">
                        <div className="truncate text-[16px] text-gray-600" title={getRowLevelLabel(row) || "—"}>
                          {getRowLevelLabel(row) || "—"}
                        </div>
                      </td>
                    ) : null}
                    <td className="py-2 px-9 align-middle">
                      <div className="text-[16px] text-gray-600">
                        {count === null ? "—" : count}
                      </div>
                    </td>
                    <td className="py-2 px-9 align-middle">
                      <div className="flex flex-wrap gap-3">
                        <EditButton onClick={(event) => {
                          event.stopPropagation();
                          onEdit(row);
                        }}>
                          {t("edit")}
                        </EditButton>
                        <DeleteButton
                          onClick={(event) => {
                            event.stopPropagation();
                            onDelete(row);
                          }}
                          loading={deletingValueId === row.level_value_id}
                        >
                          {t("delete")}
                        </DeleteButton>
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
