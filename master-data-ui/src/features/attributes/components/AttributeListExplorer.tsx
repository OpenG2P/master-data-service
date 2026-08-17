"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useRouter } from "@/i18n/navigation";
import { Search, Database } from "lucide-react";
import Can from "@/components/Can";
import ConfirmDialog from "@/components/ConfirmDialog";
import LoadingState from "@/components/LoadingState";
import Pagination from "@/components/Pagination";
import { useFetch } from "@/shared/hooks/useFetch";
import { useAllAttributes } from "../hooks";
import AttributeDialog from "./AttributeDialog";
import type { Attribute } from "../types";

const PAGE_SIZE = 10;

const REFERENCE_DATA_ACTIONS = {
    create: "referenceData:create",
    edit: "referenceData:edit",
    delete: "referenceData:delete",
};

export default function AttributeListExplorer() {
    const t = useTranslations();
    const router = useRouter();

    const [page, setPage] = useState(1);
    const [searchText, setSearchText] = useState("");
    const [dialog, setDialog] = useState<{
        open: boolean;
        mode: "add" | "edit";
        attribute?: Attribute;
    }>({ open: false, mode: "add" });
    const [confirmDelete, setConfirmDelete] = useState<Attribute | null>(null);

    const { execute: deleteAttribute } = useFetch();

    const { attributes: filteredAttributes, loading, refresh } = useAllAttributes(searchText);

    const total = filteredAttributes.length;
    const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
    const currentPage = Math.min(page, totalPages);
    const attributes = filteredAttributes.slice(
        (currentPage - 1) * PAGE_SIZE,
        currentPage * PAGE_SIZE,
    );

    const proceedDelete = async () => {
        if (!confirmDelete) return;
        const result = await deleteAttribute("/api/attributes/delete-attribute", {
            method: "POST",
            body: JSON.stringify({ attribute_id: confirmDelete.attribute_id }),
        });
        if (result?.attribute_id) {
            refresh();
        }
        setConfirmDelete(null);
    };

    return (
        <section className="flex h-full min-h-0 flex-col overflow-hidden bg-black p-5 text-white">
            <div className="relative flex min-h-0 flex-1 flex-col border border-[#5A5A5A]">
                {/* Header */}
                <div className="flex shrink-0 flex-wrap items-center justify-between gap-4 border-b border-[#5A5A5A] px-4 py-4">
                    <div className="flex items-center gap-3">
                        <Database size={18} className="text-[#F4BB1B]" />
                        <h1 className="text-[18px] font-semibold text-white">
                            {t("reference_data")}
                        </h1>
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
                                onChange={(e) => {
                                    setSearchText(e.target.value);
                                    setPage(1);
                                }}
                                placeholder={t("search_attributes")}
                                className="h-9 w-56 rounded-[8px] border border-[#5A5A5A] bg-white/5 pl-8 pr-3 text-[16px] text-white placeholder:text-white/30 focus:border-[#F4BB1B] focus:outline-none"
                            />
                        </div>

                        <Can action={REFERENCE_DATA_ACTIONS.create}>
                            <button
                                type="button"
                                onClick={() => setDialog({ open: true, mode: "add" })}
                                className="inline-flex h-9 cursor-pointer items-center gap-2 rounded-[10px] bg-[#F4BB1B] px-6 text-[16px] font-medium text-black"
                            >
                                {t("add_new_attribute")}
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
                                        {t("attribute_code")}
                                    </th>
                                    <th className="w-40 bg-black px-4 py-3 text-left font-semibold text-[#F4BB1B]">
                                        {t("is_hierarchical")}
                                    </th>
                                    <th className="w-48 bg-black px-4 py-3 text-right font-semibold text-[#F4BB1B]">
                                        {t("col_actions")}
                                    </th>
                                </tr>
                            </thead>
                            <tbody>
                                {attributes.length === 0 ? (
                                    <tr>
                                        <td
                                            colSpan={4}
                                            className="px-4 py-10 text-center text-white/40"
                                        >
                                            {t("no_attributes")}
                                        </td>
                                    </tr>
                                ) : (
                                    attributes.map((item, idx) => (
                                        <tr
                                            key={item.attribute_id}
                                            className="cursor-pointer border-b border-[#5A5A5A]/40 hover:bg-white/5"
                                            onClick={() =>
                                                router.push(
                                                    `/reference-data/${encodeURIComponent(item.attribute_id)}`,
                                                )
                                            }
                                        >
                                            <td className="px-4 py-3 font-medium text-white/50">
                                                {String(
                                                    (currentPage - 1) * PAGE_SIZE + idx + 1,
                                                ).padStart(2, "0")}
                                            </td>
                                            <td className="px-4 py-3 font-medium text-white">
                                                {item.attribute_display || item.attribute_code}
                                            </td>
                                            <td className="px-4 py-3 font-medium text-white/60">
                                                {item.is_hierarchical ? t("yes") : t("no")}
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
                                                                setDialog({
                                                                    open: true,
                                                                    mode: "edit",
                                                                    attribute: item,
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
                                    ))
                                )}
                            </tbody>
                        </table>
                    </div>
                )}

                {/* Pagination */}
                {total > PAGE_SIZE && (
                    <div className="shrink-0 border-t border-[#5A5A5A] px-4 py-3 flex justify-end">
                        <Pagination
                            page={currentPage}
                            pageSize={PAGE_SIZE}
                            total={total}
                            onPageChange={setPage}
                        />
                    </div>
                )}
            </div>

            {/* Add / Edit dialog */}
            <AttributeDialog
                open={dialog.open}
                mode={dialog.mode}
                attribute={dialog.attribute}
                onClose={() => setDialog({ open: false, mode: "add" })}
                onSuccess={refresh}
            />

            {/* Delete confirm */}
            <ConfirmDialog
                open={!!confirmDelete}
                title={t("confirm_remove_attribute")}
                message={`${t("confirm_remove_attribute_msg")} "${confirmDelete?.attribute_display || confirmDelete?.attribute_code}"?`}
                danger
                confirmLabel={t("delete")}
                onConfirm={proceedDelete}
                onClose={() => setConfirmDelete(null)}
            />
        </section>
    );
}
