"use client";

import { useMemo, useState } from "react";
import { ChevronRight } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { toast } from "react-toastify";
import Can from "@/components/Can";
import ConfirmDialog from "@/components/ConfirmDialog";
import SearchInput from "@/components/SearchInput";
import TableSkeleton from "@/components/TableSkeleton";
import Pagination from "@/components/Pagination";
import AddButton from "@/components/AddButton";
import EditButton from "@/components/EditButton";
import DeleteButton from "@/components/DeleteButton";
import { useRbac } from "@/context/RbacContext";
import { errorMessage, useCatalogueApi } from "@/features/catalogue/api";
import { ErrorBox, StatusBadge, localizedLabel } from "@/features/catalogue/components/ui";
import type { ListSummary, ListValue, VersionRef } from "@/features/catalogue/types";
import { useListValues, valueHasChildren } from "../hooks";
import AttributeValueDialog from "./AttributeValueDialog";
import { REFERENCE_DATA_ACTIONS } from "./AttributeListExplorer";

interface AttributeValuesViewProps {
    list: ListSummary;
    version: VersionRef;
    /** True when the open DRAFT is shown and the user may edit it. */
    editable: boolean;
    hasDraft: boolean;
    reloadNonce?: number;
    onChanged?: () => void;
}

const PAGE_SIZE = 10;
const th = "text-left pb-3 px-6 border-b border-gray-200 font-semibold text-[#ED7C22] text-[16px] tracking-wider";

function attributeSummary(attrs: Record<string, unknown> | null | undefined): string {
    if (!attrs) return "";
    return Object.entries(attrs)
        .map(([k, v]) => `${k}: ${typeof v === "string" ? v : JSON.stringify(v)}`)
        .join(" · ");
}

/** Values of a list at the selected version; editing actions work on the list's draft. */
export default function AttributeValuesView({
    list,
    version,
    editable,
    hasDraft,
    reloadNonce = 0,
    onChanged,
}: AttributeValuesViewProps) {
    const t = useTranslations();
    const locale = useLocale();
    const call = useCatalogueApi();
    const { can } = useRbac();

    const [parentCode, setParentCode] = useState<string | null>(null);
    const [breadcrumb, setBreadcrumb] = useState<ListValue[]>([]);
    const [searchText, setSearchText] = useState("");
    const [page, setPage] = useState(1);
    const [includeRetired, setIncludeRetired] = useState(version === "draft");
    const [localNonce, setLocalNonce] = useState(0);
    const [valueDialog, setValueDialog] = useState<{ open: boolean; mode: "add" | "edit"; value?: ListValue }>({
        open: false,
        mode: "add",
    });
    const [confirmRetire, setConfirmRetire] = useState<ListValue | null>(null);
    const [cascade, setCascade] = useState(false);
    const [busyCode, setBusyCode] = useState<string | null>(null);

    const { values: allValues, version: info, loading, error } = useListValues(
        list.list_id,
        version,
        includeRetired,
        reloadNonce * 1000 + localNonce,
    );

    const isHierarchical = list.is_hierarchical;
    const searching = Boolean(searchText.trim());

    const rows = useMemo(() => {
        const q = searchText.trim().toLowerCase();
        return allValues.filter((v) => {
            if (q) {
                // Search across the whole list, not only the current level.
                return (
                    v.value_code.toLowerCase().includes(q) ||
                    (v.display ?? "").toLowerCase().includes(q) ||
                    Object.values(v.display_i18n ?? {}).some((l) => l.toLowerCase().includes(q))
                );
            }
            if (!isHierarchical) return true;
            return parentCode ? v.parent_code === parentCode : !v.parent_code;
        });
    }, [allValues, searchText, isHierarchical, parentCode]);

    const totalPages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
    const currentPage = Math.min(page, totalPages);
    const pageRows = rows.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);

    const changed = () => {
        setLocalNonce((n) => n + 1);
        onChanged?.();
    };

    const handleDrillDown = (value: ListValue) => {
        if (!isHierarchical || searching) return;
        setParentCode(value.value_code);
        setBreadcrumb((prev) => [...prev, value]);
        setPage(1);
    };

    const handleBreadcrumbClick = (index: number) => {
        if (index < 0) {
            setParentCode(null);
            setBreadcrumb([]);
        } else {
            setParentCode(breadcrumb[index].value_code);
            setBreadcrumb(breadcrumb.slice(0, index + 1));
        }
        setSearchText("");
        setPage(1);
    };

    const proceedRetire = async () => {
        if (!confirmRetire) return;
        setBusyCode(confirmRetire.value_code);
        try {
            const { payload } = await call<{ retired: string[]; removed: string[] }>("retire_draft_values", {
                list_code: list.list_id,
                value_codes: [confirmRetire.value_code],
                cascade,
            });
            toast.success(
                t("cat_values_retired", { retired: payload.retired.length, removed: payload.removed.length }),
            );
            changed();
        } catch (e) {
            toast.error(errorMessage(e));
        } finally {
            setBusyCode(null);
            setConfirmRetire(null);
            setCascade(false);
        }
    };

    const reactivate = async (value: ListValue) => {
        setBusyCode(value.value_code);
        try {
            await call("upsert_draft_values", {
                list_code: list.list_id,
                values: [{ value_id: value.value_id, value_code: value.value_code, status: "ACTIVE" }],
            });
            toast.success(t("cat_value_reactivated"));
            changed();
        } catch (e) {
            toast.error(errorMessage(e));
        } finally {
            setBusyCode(null);
        }
    };

    const showActions = editable;

    return (
        <div className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-4">
                <div className="flex flex-col gap-1">
                    {isHierarchical && !searching ? (
                        <>
                            <span className="text-[14px] text-gray-400">{t("attr_hierarchical_hint")}</span>
                            <div className="flex items-center gap-1 text-[16px] text-gray-500">
                                <button
                                    type="button"
                                    onClick={() => handleBreadcrumbClick(-1)}
                                    className="hover:text-[#ED7C22] transition-colors cursor-pointer"
                                >
                                    {t("root")}
                                </button>
                                {breadcrumb.map((crumb, i) => (
                                    <span key={crumb.value_id} className="flex items-center gap-1">
                                        <ChevronRight size={14} />
                                        <button
                                            type="button"
                                            onClick={() => handleBreadcrumbClick(i)}
                                            className="hover:text-[#ED7C22] transition-colors max-w-32 truncate cursor-pointer"
                                        >
                                            {localizedLabel(crumb.display, crumb.display_i18n, locale) || crumb.value_code}
                                        </button>
                                    </span>
                                ))}
                            </div>
                        </>
                    ) : null}
                    {info ? (
                        <span className="text-[13px] text-gray-500">
                            {t("cat_values_of_version", { count: allValues.length, no: info.version_no })}
                        </span>
                    ) : null}
                </div>
                <div className="flex flex-wrap items-center gap-3">
                    <label className="flex cursor-pointer items-center gap-2 text-[14px] text-gray-700">
                        <input
                            type="checkbox"
                            checked={includeRetired}
                            onChange={(e) => {
                                setIncludeRetired(e.target.checked);
                                setPage(1);
                            }}
                            className="h-4 w-4 accent-[#f4bb1b]"
                        />
                        {t("cat_include_retired")}
                    </label>
                    <SearchInput
                        value={searchText}
                        onChange={(v) => {
                            setSearchText(v);
                            setPage(1);
                        }}
                        placeholder={t("search_attribute_values")}
                    />
                    {editable ? (
                        <Can action={REFERENCE_DATA_ACTIONS.edit}>
                            <AddButton onClick={() => setValueDialog({ open: true, mode: "add" })} label={t("add_attribute_value")} />
                        </Can>
                    ) : null}
                </div>
            </div>

            {!editable && can(REFERENCE_DATA_ACTIONS.edit) ? (
                <p className="rounded bg-gray-100 px-3 py-2 text-[13px] text-gray-700">
                    {hasDraft ? t("cat_readonly_view_draft_hint") : t("cat_readonly_open_draft_hint")}
                </p>
            ) : null}

            <ErrorBox message={error} />

            {loading && allValues.length === 0 ? (
                <TableSkeleton rows={10} columns={6} />
            ) : (
                <div className="bg-white rounded-[10px] pt-6 pb-3 shadow-sm">
                    <div className="overflow-auto">
                        <table className="w-full min-w-[960px] border-collapse bg-white table-fixed">
                            <thead>
                                <tr>
                                    <th className={th} style={{ width: "6%" }}>{t("col_no")}</th>
                                    <th className={th} style={{ width: "16%" }}>{t("value_code")}</th>
                                    <th className={th} style={{ width: "22%" }}>{t("value_display")}</th>
                                    <th className={th} style={{ width: "8%" }}>{t("sort_order")}</th>
                                    <th className={th} style={{ width: "10%" }}>{t("col_status")}</th>
                                    <th className={th} style={{ width: showActions ? "18%" : "38%" }}>{t("cat_attributes")}</th>
                                    {showActions ? <th className={th} style={{ width: "20%" }}>{t("col_actions")}</th> : null}
                                </tr>
                            </thead>
                            <tbody>
                                {pageRows.length === 0 ? (
                                    <tr>
                                        <td colSpan={showActions ? 7 : 6} className="text-center py-10 px-4 text-gray-600">
                                            {t("no_results")}
                                        </td>
                                    </tr>
                                ) : (
                                    pageRows.map((item, idx) => {
                                        const hasChildren = isHierarchical && valueHasChildren(item.value_code, allValues);
                                        const label = localizedLabel(item.display, item.display_i18n, locale) || item.value_code;
                                        const i18nTitle = Object.entries(item.display_i18n ?? {})
                                            .map(([l, v]) => `${l}: ${v}`)
                                            .join("\n");
                                        const retired = item.status === "RETIRED";
                                        const attrs = attributeSummary(item.attributes);
                                        return (
                                            <tr
                                                key={item.value_id}
                                                className={`transition-colors duration-150 ${isHierarchical && !searching ? "cursor-pointer" : ""} ${idx % 2 === 1 ? "bg-white" : "bg-gray-50"} hover:bg-gray-100 ${retired ? "text-gray-400" : ""}`}
                                                onClick={() => handleDrillDown(item)}
                                            >
                                                <td className="py-2 px-6 align-middle text-[16px] text-gray-500">
                                                    {String((currentPage - 1) * PAGE_SIZE + idx + 1).padStart(2, "0")}
                                                </td>
                                                <td className="py-2 px-6 align-middle font-mono text-[14px] truncate" title={item.value_code}>
                                                    {item.value_code}
                                                </td>
                                                <td className="py-2 px-6 align-middle">
                                                    <div className="flex items-center gap-2">
                                                        <div
                                                            className={`text-[16px] truncate ${retired ? "line-through" : "text-black"}`}
                                                            title={i18nTitle ? `${item.display ?? ""}\n${i18nTitle}` : label}
                                                        >
                                                            {label}
                                                        </div>
                                                        {hasChildren && !searching ? (
                                                            <ChevronRight size={16} className="text-[#ED7C22] shrink-0" />
                                                        ) : null}
                                                    </div>
                                                    {searching && item.parent_code ? (
                                                        <div className="text-[12px] text-gray-500">
                                                            {t("cat_parent_value")}: {item.parent_code}
                                                        </div>
                                                    ) : null}
                                                </td>
                                                <td className="py-2 px-6 align-middle text-[15px] text-gray-600">{item.sort_order ?? 0}</td>
                                                <td className="py-2 px-6 align-middle">
                                                    <StatusBadge status={item.status} label={t(`cat_status_${item.status}`)} />
                                                </td>
                                                <td className="py-2 px-6 align-middle font-mono text-[12px] text-gray-600 truncate" title={attrs}>
                                                    {attrs || "—"}
                                                </td>
                                                {showActions ? (
                                                    <td className="py-2 px-6 align-middle" onClick={(e) => e.stopPropagation()}>
                                                        <div className="flex flex-wrap items-center justify-start gap-2">
                                                            {!retired ? (
                                                                <Can action={REFERENCE_DATA_ACTIONS.edit}>
                                                                    <EditButton
                                                                        onClick={() => setValueDialog({ open: true, mode: "edit", value: item })}
                                                                        title={t("edit")}
                                                                    >
                                                                        {t("edit")}
                                                                    </EditButton>
                                                                </Can>
                                                            ) : null}
                                                            {retired ? (
                                                                <Can action={REFERENCE_DATA_ACTIONS.edit}>
                                                                    <EditButton
                                                                        onClick={() => void reactivate(item)}
                                                                        disabled={busyCode === item.value_code}
                                                                        title={t("cat_reactivate")}
                                                                    >
                                                                        {t("cat_reactivate")}
                                                                    </EditButton>
                                                                </Can>
                                                            ) : (
                                                                <Can action={REFERENCE_DATA_ACTIONS.delete}>
                                                                    <DeleteButton
                                                                        onClick={() => setConfirmRetire(item)}
                                                                        loading={busyCode === item.value_code}
                                                                        title={t("cat_retire")}
                                                                    >
                                                                        {t("cat_retire")}
                                                                    </DeleteButton>
                                                                </Can>
                                                            )}
                                                        </div>
                                                    </td>
                                                ) : null}
                                            </tr>
                                        );
                                    })
                                )}
                            </tbody>
                        </table>
                    </div>

                    {rows.length > PAGE_SIZE && (
                        <div className="shrink-0 border-t border-gray-200 px-4 pt-3 flex justify-end">
                            <Pagination page={currentPage} pageSize={PAGE_SIZE} total={rows.length} onPageChange={setPage} />
                        </div>
                    )}
                </div>
            )}

            {valueDialog.open ? (
                <AttributeValueDialog
                    open
                    mode={valueDialog.mode}
                    list={list}
                    allValues={allValues}
                    parentCode={parentCode}
                    value={valueDialog.value}
                    onClose={() => setValueDialog({ open: false, mode: "add" })}
                    onSuccess={changed}
                />
            ) : null}

            <ConfirmDialog
                open={!!confirmRetire}
                title={t("cat_retire_value_title")}
                message={t("cat_retire_value_message", {
                    name: confirmRetire ? localizedLabel(confirmRetire.display, confirmRetire.display_i18n, locale) || confirmRetire.value_code : "",
                })}
                danger
                confirming={busyCode !== null && busyCode === confirmRetire?.value_code}
                confirmLabel={t("cat_retire")}
                confirmingLabel={t("cat_retiring")}
                onConfirm={() => void proceedRetire()}
                onClose={() => {
                    setConfirmRetire(null);
                    setCascade(false);
                }}
            >
                {confirmRetire && isHierarchical && valueHasChildren(confirmRetire.value_code, allValues) ? (
                    <label className="flex cursor-pointer items-center justify-center gap-2 text-[14px]">
                        <input
                            type="checkbox"
                            checked={cascade}
                            onChange={(e) => setCascade(e.target.checked)}
                            className="h-4 w-4 accent-[#f4bb1b]"
                        />
                        {t("cat_retire_cascade")}
                    </label>
                ) : null}
            </ConfirmDialog>
        </div>
    );
}
