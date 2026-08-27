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
  const [pageByLevel, setPageByLevel] = useState<Record<string, number>>({});
  const [sortKey, setSortKey] = useState<"name" | "children">("name");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const pageSize = 10;

  const rows = childrenEntry?.values ?? [];
  const loading = Boolean(childrenEntry?.loading);
  const error = childrenEntry?.error ?? null;

  useEffect(() => {
    setPage(1);
    setPageByLevel({});
  }, [selected?.key, rows[0]?.level_value_id, rows.length]);

  const filtered = useMemo(() => {
    return [...rows].sort((a, b) => {
      let cmp = 0;
      if (sortKey === "name") {
        cmp = getValueLabel(a).localeCompare(getValueLabel(b));
      } else {
        cmp = (getChildCount(a) ?? -1) - (getChildCount(b) ?? -1);
      }
      return sortDir === "asc" ? cmp : -cmp;
    });
  }, [getChildCount, rows, sortDir, sortKey]);

  const groups = useMemo(() => {
    const order: string[] = [];
    const byLevel = new Map<string, GeoLevelValue[]>();
    for (const row of filtered) {
      const levelId = row.level_id;
      if (!byLevel.has(levelId)) {
        order.push(levelId);
        byLevel.set(levelId, []);
      }
      byLevel.get(levelId)!.push(row);
    }
    return order.map((levelId) => ({
      levelId,
      rows: byLevel.get(levelId) ?? [],
    }));
  }, [filtered]);

  const isForked = groups.length > 1;
  const total = filtered.length;
  const totalPages = Math.max(1, Math.ceil(total / pageSize) || 1);
  const currentPage = Math.min(page, totalPages);
  const pageRows = isForked
    ? []
    : filtered.slice((currentPage - 1) * pageSize, currentPage * pageSize);
  const showPagination =
    Boolean(selected) && !loading && !error && total > 0 && !isForked;
  const showFooter = Boolean(footerActions) || showPagination;

  const toggleSort = (key: typeof sortKey) => {
    if (sortKey === key) {
      setSortDir((dir) => (dir === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
    setPage(1);
    setPageByLevel({});
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
      <div className="shrink-0 border-b border-gray-200 px-4 pl-9 py-2.5">
        <div className="text-[16px] leading-none tracking-normal text-black">
          {title || t("geo_children")}
        </div>
        {subtitle ? (
          <p className="mt-1.5 text-[12px] text-gray-400">{subtitle}</p>
        ) : null}
      </div>

      <div className="min-h-0 flex-1 overflow-x-hidden overflow-y-auto pt-0 pb-2">
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
        ) : total === 0 ? (
          <div className="flex flex-col items-center gap-3 px-1 py-10 text-center">
            <p className="text-[16px] text-gray-400">{t("geo_no_level_values")}</p>
          </div>
        ) : (
          <table className="w-full border-collapse bg-white table-fixed">
            <thead>
              <tr>
                <th className="text-left py-3 px-9 border-b border-gray-200 font-semibold text-[#ed7c22] text-[16px] tracking-wider" style={{ width: "45%" }}>
                  <button
                    type="button"
                    className="cursor-pointer"
                    onClick={() => toggleSort("name")}
                  >
                    {t("col_name")}
                    {/* {sortMarker("name")} */}
                  </button>
                </th>
                {getRowLevelLabel ? (
                  <th className="text-left py-3 px-9 border-b border-gray-200 font-semibold text-[#ed7c22] text-[16px] tracking-wider" style={{ width: "20%" }}>
                    {t("geo_level")}
                  </th>
                ) : null}
                <th className="text-left py-3 px-9 border-b border-gray-200 font-semibold text-[#ed7c22] text-[16px] tracking-wider" style={{ width: "25%" }}>
                  <button
                    type="button"
                    className="cursor-pointer"
                    onClick={() => toggleSort("children")}
                  >
                    {t("geo_child_count")}
                    {/* {sortMarker("children")} */}
                  </button>
                </th>
                <th className="text-left py-3 px-9 border-b border-gray-200 font-semibold text-[#ed7c22] text-[16px] tracking-wider" style={{ width: "30%" }}>
                  {t("col_actions")}
                </th>
              </tr>
            </thead>
            <tbody>
              {(isForked ? groups : [{ levelId: "", rows: pageRows }]).flatMap(
                (group) => {
                  const groupTotal = group.rows.length;
                  const groupPage = isForked
                    ? Math.min(
                        pageByLevel[group.levelId] ?? 1,
                        Math.max(1, Math.ceil(groupTotal / pageSize) || 1)
                      )
                    : 1;
                  const visibleRows = isForked
                    ? group.rows.slice(
                        (groupPage - 1) * pageSize,
                        groupPage * pageSize
                      )
                    : group.rows;
                  const colSpan = getRowLevelLabel ? 4 : 3;
                  const groupLabel =
                    getRowLevelLabel?.(group.rows[0]) || group.levelId;
                  const header =
                    isForked && group.rows.length > 0 ? (
                      <tr key={`${group.levelId}-header`}>
                        <td
                          colSpan={colSpan}
                          className="bg-gray-100 py-2 px-9 text-[14px] font-semibold text-black"
                        >
                          {groupLabel}
                          <span className="ml-2 font-normal text-gray-500">
                            ({groupTotal})
                          </span>
                        </td>
                      </tr>
                    ) : null;
                  const dataRows = visibleRows.map((row, index) => {
                    const count = getChildCount(row);
                    return (
                      <tr
                        key={row.level_value_id}
                        className={`cursor-pointer transition-colors duration-150 ${index % 2 === 1 ? "bg-white" : "bg-gray-50"} hover:bg-gray-100`}
                        onClick={() => onSelect(row)}
                      >
                        <td className="py-2 px-9 align-middle">
                          <div
                            className="truncate text-[16px] text-black"
                            title={getValueLabel(row)}
                          >
                            {getValueLabel(row)}
                          </div>
                        </td>
                        {getRowLevelLabel ? (
                          <td className="py-2 px-9 align-middle">
                            <div
                              className="truncate text-[16px] text-gray-600"
                              title={getRowLevelLabel(row) || "—"}
                            >
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
                            <EditButton
                              onClick={(event) => {
                                event.stopPropagation();
                                onEdit(row);
                              }}
                            >
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
                  });
                  const pager =
                    isForked && groupTotal > pageSize ? (
                      <tr key={`${group.levelId}-pager`}>
                        <td colSpan={colSpan} className="px-9 py-2">
                          <div className="flex justify-end">
                            <Pagination
                              page={groupPage}
                              pageSize={pageSize}
                              total={groupTotal}
                              onPageChange={(next) =>
                                setPageByLevel((prev) => ({
                                  ...prev,
                                  [group.levelId]: next,
                                }))
                              }
                            />
                          </div>
                        </td>
                      </tr>
                    ) : null;
                  return [header, ...dataRows, pager].filter(Boolean);
                }
              )}
            </tbody>
          </table>
        )}
      </div>

      {footer}
    </div>
  );
}
