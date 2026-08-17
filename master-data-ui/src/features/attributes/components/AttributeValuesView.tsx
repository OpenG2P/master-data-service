"use client";

import { useEffect, useState } from "react";
import { ChevronRight, Search } from "lucide-react";
import { useTranslations } from "next-intl";
import { useFetch } from "@/shared/hooks/useFetch";
import Can from "@/components/Can";
import ConfirmDialog from "@/components/ConfirmDialog";
import LoadingState from "@/components/LoadingState";
import Pagination from "@/components/Pagination";
import { useAttributeValues, valueHasChildren } from "../hooks";
import AttributeValueDialog from "./AttributeValueDialog";
import type { Attribute, AttributeValue } from "../types";

const REFERENCE_DATA_ACTIONS = {
    create: "referenceData:create",
    edit: "referenceData:edit",
    delete: "referenceData:delete",
};

interface AttributeValuesViewProps {
    attribute: Attribute;
}

export default function AttributeValuesView({ attribute }: AttributeValuesViewProps) {
    const t = useTranslations();

    const [parentValueId, setParentValueId] = useState<string | null>(null);
    const [breadcrumb, setBreadcrumb] = useState<AttributeValue[]>([]);
    const [searchText, setSearchText] = useState("");
    const [page, setPage] = useState(1);
    const PAGE_SIZE = 10;

    const [valueDialog, setValueDialog] = useState<{
        open: boolean;
        mode: "add" | "edit";
        value?: AttributeValue;
    }>({ open: false, mode: "add" });

    const [confirmDelete, setConfirmDelete] = useState<AttributeValue | null>(null);

    const { execute: deleteValue } = useFetch();

    const { attributeValues, allValues, loading, refresh } = useAttributeValues(
        attribute.attribute_id,
        parentValueId,
        searchText,
    );

    const isHierarchical = attribute.is_hierarchical;

    // Reset when attribute changes
    useEffect(() => {
        setParentValueId(null);
        setBreadcrumb([]);
        setSearchText("");
        setPage(1);
    }, [attribute.attribute_id]);

    // Reset page when filtered list changes
    useEffect(() => {
        setPage(1);
    }, [searchText, parentValueId]);

    const totalPages = Math.max(1, Math.ceil(attributeValues.length / PAGE_SIZE));
    const currentPage = Math.min(page, totalPages);
    const pageRows = attributeValues.slice(
        (currentPage - 1) * PAGE_SIZE,
        currentPage * PAGE_SIZE,
    );

    const handleDrillDown = (value: AttributeValue) => {
        if (!isHierarchical) return;
        setParentValueId(value.value_id);
        setBreadcrumb((prev) => [...prev, value]);
        setSearchText("");
        setPage(1);
    };

    const handleBreadcrumbClick = (index: number) => {
        if (index < 0) {
            setParentValueId(null);
            setBreadcrumb([]);
        } else {
            const crumb = breadcrumb[index];
            setParentValueId(crumb.value_id);
            setBreadcrumb(breadcrumb.slice(0, index + 1));
        }
        setSearchText("");
        setPage(1);
    };

    const proceedDelete = async () => {
        if (!confirmDelete) return;
        const result = await deleteValue("/api/attributes/delete-attribute-value", {
            method: "POST",
            body: JSON.stringify({
                value_id: confirmDelete.value_id,
                attribute_id: confirmDelete.attribute_id,
            }),
        });
        if (result?.value_id || result?.attribute_id) {
            refresh();
        }
        setConfirmDelete(null);
    };

    return (
        <section className="flex min-h-0 flex-1 flex-col overflow-hidden bg-black text-white">
            <div className="flex flex-1 flex-col border border-[#5A5A5A] min-h-0">
                {/* Header row */}
                <div className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-b border-[#5A5A5A] px-4 py-3">
                    <div className="flex flex-col gap-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                            <span className="text-[16px] font-semibold text-white">
                                {t("attr_values_title")}
                            </span>
                            {breadcrumb.length > 0 && (
                                <div className="flex items-center gap-1 text-[16px] text-white/50">
                                    <button
                                        type="button"
                                        onClick={() => handleBreadcrumbClick(-1)}
                                        className="hover:text-[#F4BB1B] transition-colors"
                                    >
                                        {t("root")}
                                    </button>
                                    {breadcrumb.map((crumb, i) => (
                                        <span key={crumb.value_id} className="flex items-center gap-1">
                                            <ChevronRight size={14} />
                                            <button
                                                type="button"
                                                onClick={() => handleBreadcrumbClick(i)}
                                                className="hover:text-[#F4BB1B] transition-colors max-w-32 truncate"
                                            >
                                                {crumb.value_display || crumb.value_code}
                                            </button>
                                        </span>
                                    ))}
                                </div>
                            )}
                        </div>
                        {isHierarchical && (
                            <span className="text-[14px] text-white/40">
                                {t("attr_hierarchical_hint")}
                            </span>
                        )}
                    </div>

                    <div className="flex items-center gap-3">
                        {/* Search */}
                        <div className="relative">
                            <Search
                                size={14}
                                className="absolute left-3 top-1/2 -translate-y-1/2 text-white/40"
                            />
                            <input
                                type="text"
                                value={searchText}
                                onChange={(e) => setSearchText(e.target.value)}
                                placeholder={t("search_attribute_values")}
                                className="h-9 w-52 rounded-[8px] border border-[#5A5A5A] bg-white/5 pl-8 pr-3 text-[16px] text-white placeholder:text-white/30 focus:border-[#F4BB1B] focus:outline-none"
                            />
                        </div>

                        <Can action={REFERENCE_DATA_ACTIONS.create}>
                            <button
                                type="button"
                                onClick={() =>
                                    setValueDialog({ open: true, mode: "add" })
                                }
                                className="inline-flex h-9 cursor-pointer items-center gap-2 rounded-[10px] bg-[#F4BB1B] px-6 text-[16px] font-medium text-black"
                            >
                                {t("add_attribute_value")}
                                <span className="text-[20px] font-bold leading-none text-black">
                                    +
                                </span>
                            </button>
                        </Can>
                    </div>
                </div>

                {/* Table */}
                {loading ? (
                    <LoadingState compact />
                ) : (
                    <div className="min-h-0 flex-1 overflow-auto">
                        <table className="w-full text-[16px]">
                            <thead className="sticky top-0 z-10">
                                <tr className="border-b border-[#3A3A3A]">
                                    <th className="w-12 bg-black px-4 py-3 text-left font-semibold text-[#F4BB1B]">
                                        {t("col_no")}
                                    </th>
                                    <th className="bg-black px-4 py-3 text-left font-semibold text-[#F4BB1B]">
                                        {t("value_code")}
                                    </th>
                                    <th className="w-28 bg-black px-4 py-3 text-left font-semibold text-[#F4BB1B]">
                                        {t("sort_order")}
                                    </th>
                                    <th className="w-44 bg-black px-4 py-3 text-right font-semibold text-[#F4BB1B]">
                                        {t("col_actions")}
                                    </th>
                                </tr>
                            </thead>
                            <tbody>
                                {pageRows.length === 0 ? (
                                    <tr>
                                        <td
                                            colSpan={4}
                                            className="px-4 py-10 text-center text-white/40"
                                        >
                                            {t("no_results")}
                                        </td>
                                    </tr>
                                ) : (
                                    pageRows.map((item, idx) => {
                                        const hasChildren =
                                            isHierarchical &&
                                            valueHasChildren(item.value_id, allValues);
                                        return (
                                            <tr
                                                key={item.value_id}
                                                className={`border-b border-[#5A5A5A]/40 ${isHierarchical ? "cursor-pointer hover:bg-white/5" : "hover:bg-white/[0.02]"}`}
                                                onClick={() => handleDrillDown(item)}
                                            >
                                                <td className="px-4 py-3 font-medium text-white/50">
                                                    {String(
                                                        (currentPage - 1) * PAGE_SIZE + idx + 1,
                                                    ).padStart(2, "0")}
                                                </td>
                                                <td className="px-4 py-3 font-medium text-white">
                                                    <div className="flex items-center gap-2">
                                                        <span className="truncate">
                                                            {item.value_display || item.value_code}
                                                        </span>
                                                        {hasChildren && (
                                                            <ChevronRight
                                                                size={16}
                                                                className="text-[#F4BB1B] shrink-0"
                                                            />
                                                        )}
                                                    </div>
                                                </td>
                                                <td className="px-4 py-3 font-medium text-white/60">
                                                    {item.sort_order ?? 0}
                                                </td>
                                                <td
                                                    className="px-4 py-3 text-right"
                                                    onClick={(e) => e.stopPropagation()}
                                                >
                                                    <div className="flex items-center justify-end gap-4">
                                                        <Can action={REFERENCE_DATA_ACTIONS.edit}>
                                                            <button
                                                                type="button"
                                                                onClick={() =>
                                                                    setValueDialog({
                                                                        open: true,
                                                                        mode: "edit",
                                                                        value: item,
                                                                    })
                                                                }
                                                                className="font-medium text-white/50 hover:opacity-80 transition-opacity"
                                                            >
                                                                {t("edit")}
                                                            </button>
                                                        </Can>
                                                        <Can action={REFERENCE_DATA_ACTIONS.delete}>
                                                            <button
                                                                type="button"
                                                                onClick={() =>
                                                                    setConfirmDelete(item)
                                                                }
                                                                className="font-medium text-red-400 hover:opacity-80 transition-opacity"
                                                            >
                                                                {t("delete")}
                                                            </button>
                                                        </Can>
                                                    </div>
                                                </td>
                                            </tr>
                                        );
                                    })
                                )}
                            </tbody>
                        </table>
                    </div>
                )}

                {/* Pagination */}
                {attributeValues.length > PAGE_SIZE && (
                    <div className="shrink-0 border-t border-[#5A5A5A] px-4 py-3 flex justify-end">
                        <Pagination
                            page={currentPage}
                            pageSize={PAGE_SIZE}
                            total={attributeValues.length}
                            onPageChange={setPage}
                        />
                    </div>
                )}
            </div>

            {/* Value add/edit dialog */}
            <AttributeValueDialog
                open={valueDialog.open}
                mode={valueDialog.mode}
                attributeId={attribute.attribute_id}
                parentValueId={parentValueId}
                value={valueDialog.value}
                onClose={() => setValueDialog({ open: false, mode: "add" })}
                onSuccess={refresh}
            />

            {/* Delete confirm */}
            <ConfirmDialog
                open={!!confirmDelete}
                title={t("confirm_remove_attribute_value")}
                message={`${t("confirm_remove_attribute_value_msg")} "${confirmDelete?.value_display || confirmDelete?.value_code}"?`}
                danger
                confirmLabel={t("delete")}
                onConfirm={proceedDelete}
                onClose={() => setConfirmDelete(null)}
            />
        </section>
    );
}
