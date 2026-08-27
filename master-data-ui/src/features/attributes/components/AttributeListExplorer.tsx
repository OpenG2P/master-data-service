"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useRouter } from "@/i18n/navigation";
import { Database } from "lucide-react";
import Can from "@/components/Can";
import SearchInput from "@/components/SearchInput";
import ConfirmDialog from "@/components/ConfirmDialog";
import TableSkeleton from "@/components/TableSkeleton";
import Pagination from "@/components/Pagination";
import AddButton from "@/components/AddButton";
import DeleteButton from "@/components/DeleteButton";
import EditButton from "@/components/EditButton";
import Button from "@/components/Button";
import { useFetch } from "@/shared/hooks/useFetch";
import { useAllAttributes } from "../hooks";
import AttributeDialog from "./AttributeDialog";
import { toast } from "react-toastify";
import { getErrorMessage } from "@/shared/utils/errorHandler";
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
    const [isSaving, setIsSaving] = useState(false);
    const [confirmDelete, setConfirmDelete] = useState<Attribute | null>(null);
    const [isDeleting, setIsDeleting] = useState(false);

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
        setIsDeleting(true);
        const result = await deleteAttribute("/api/attributes/delete-attribute", {
            method: "POST",
            body: JSON.stringify({
                attribute_id: confirmDelete.attribute_id,
                cascade: true,
            }),
        });
        setIsDeleting(false);
        if (result?.attribute_id) {
            toast.success(t("attribute_deleted_successfully"));
            refresh();
        } else {
            const rawError = (result as any)?.error || (result as any)?.statusText;
            const errorCode = (result as any)?.code;
            const errorMessage = getErrorMessage(rawError, errorCode, t);
            toast.error(errorMessage);
        }
        setConfirmDelete(null);
    };

    return (
        <div>
            <div className="flex items-center justify-between gap-4 mb-6">
                <h1 className="font-semibold text-[24px] text-black">{t("reference_data")}</h1>
                <div className="flex items-center gap-3">
                    {/* Search */}
                    <SearchInput
                        value={searchText}
                        onChange={(value) => {
                            setSearchText(value);
                            setPage(1);
                        }}
                        placeholder={t("search_attributes")}
                    />

                    <Can action={REFERENCE_DATA_ACTIONS.create}>
                        <AddButton onClick={() => setDialog({ open: true, mode: "add" })} label={t("add_new_attribute")} />
                    </Can>
                </div>
            </div>

            {/* Table */}
            {loading ? (
                <TableSkeleton rows={10} columns={4} columnWidths={["12%", "38%", "25%", "25%"]} />
            ) : (
                <div className="bg-white rounded-[10px] pt-6 pb-3 shadow-sm">
                    <div className="overflow-auto">
                                <table className="w-full border-collapse bg-white table-fixed">
                            <thead>
                                <tr>
                                    <th className="text-left pb-3 px-9 border-b border-gray-200 font-semibold text-[#ED7C22] text-[16px] tracking-wider" style={{ width: "12%" }}>
                                        {t("col_no")}
                                    </th>
                                    <th className="text-left pb-3 px-9 border-b border-gray-200 font-semibold text-[#ED7C22] text-[16px] tracking-wider" style={{ width: "38%" }}>
                                        {t("attribute_code")}
                                    </th>
                                    <th className="text-left pb-3 px-9 border-b border-gray-200 font-semibold text-[#ED7C22] text-[16px] tracking-wider" style={{ width: "25%" }}>
                                        {t("is_hierarchical")}
                                    </th>
                                    <th className="text-left pb-3 px-9 border-b border-gray-200 font-semibold text-[#ED7C22] text-[16px] tracking-wider" style={{ width: "25%" }}>
                                        {t("col_actions")}
                                    </th>
                                </tr>
                            </thead>
                            <tbody>
                                {attributes.length === 0 ? (
                                    <tr>
                                        <td
                                            colSpan={4}
                                            className="text-center py-10 px-4 text-gray-600"
                                        >
                                            {t("no_attributes")}
                                        </td>
                                    </tr>
                                ) : (
                                    attributes.map((item, idx) => (
                                        <tr
                                            key={item.attribute_id}
                                            className={`cursor-pointer transition-colors duration-150 ${idx % 2 === 1 ? 'bg-white' : 'bg-gray-50'} hover:bg-gray-100`}
                                            onClick={() =>
                                                router.push(
                                                    `/reference-data/${encodeURIComponent(item.attribute_id)}`,
                                                )
                                            }
                                        >
                                            <td className="py-2 px-9 align-middle">
                                                <div className="text-[16px] text-gray-500">
                                                    {String(
                                                        (currentPage - 1) * PAGE_SIZE + idx + 1,
                                                    ).padStart(2, "0")}
                                                </div>
                                            </td>
                                            <td className="py-2 px-9 align-middle">
                                                <div className="text-[16px] text-black truncate" title={item.attribute_display || item.attribute_code}>
                                                    {item.attribute_display || item.attribute_code}
                                                </div>
                                            </td>
                                            <td className="py-2 px-9 align-middle">
                                                <div className="text-[16px] text-gray-600">
                                                    {item.is_hierarchical ? t("yes") : t("no")}
                                                </div>
                                            </td>
                                            <td
                                                className="py-2 px-9 align-middle"
                                                onClick={(e) => e.stopPropagation()}
                                            >
                                                <div className="flex items-center justify-start gap-4">
                                                    <Can action={REFERENCE_DATA_ACTIONS.edit}>
                                                        <EditButton onClick={() =>
                                                            setDialog({
                                                                open: true,
                                                                mode: "edit",
                                                                attribute: item,
                                                            })
                                                        }>
                                                            {t("edit")}
                                                        </EditButton>
                                                    </Can>
                                                    <Can action={REFERENCE_DATA_ACTIONS.delete}>
                                                        <DeleteButton 
                                                            onClick={() => setConfirmDelete(item)}
                                                            loading={isDeleting && confirmDelete?.attribute_id === item.attribute_id}
                                                        >
                                                            {t("delete")}
                                                        </DeleteButton>
                                                    </Can>
                                                </div>
                                            </td>
                                        </tr>
                                    ))
                                )}
                            </tbody>
                        </table>
                    </div>

                    {/* Pagination */}
                    {total > PAGE_SIZE && (
                        <div className="shrink-0 border-t border-gray-200 px-4 pt-3 flex justify-end">
                            <Pagination
                                page={currentPage}
                                pageSize={PAGE_SIZE}
                                total={total}
                                onPageChange={setPage}
                            />
                        </div>
                    )}
                </div>
            )}

            {/* Add / Edit dialog */}
            <AttributeDialog
                open={dialog.open}
                mode={dialog.mode}
                attribute={dialog.attribute}
                onClose={() => {
                    setDialog({ open: false, mode: "add" });
                    setIsSaving(false);
                }}
                onSuccess={() => {
                    toast.success(dialog.mode === "add" ? t("attribute_added_successfully") : t("attribute_updated_successfully"));
                    refresh();
                    setDialog({ open: false, mode: "add" });
                    setIsSaving(false);
                }}
            />

            {/* Delete confirm */}
            <ConfirmDialog
                open={!!confirmDelete}
                title={t("confirm_remove_attribute")}
                message={`${t("confirm_remove_attribute_msg")} "${confirmDelete?.attribute_display || confirmDelete?.attribute_code}"?`}
                danger
                confirmLabel={t("delete")}
                confirming={isDeleting}
                onConfirm={proceedDelete}
                onClose={() => setConfirmDelete(null)}
            />
        </div>
    );
}
