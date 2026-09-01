"use client";

import { useEffect, useState } from "react";
import { ChevronRight, ArrowLeft } from "lucide-react";
import { useTranslations } from "next-intl";
import { useRouter } from "@/i18n/navigation";
import { useFetch } from "@/shared/hooks/useFetch";
import Can from "@/components/Can";
import ConfirmDialog from "@/components/ConfirmDialog";
import SearchInput from "@/components/SearchInput";
import TableSkeleton from "@/components/TableSkeleton";
import Pagination from "@/components/Pagination";
import { toast } from "react-toastify";
import { getErrorMessage } from "@/shared/utils/errorHandler";
import AddButton from "@/components/AddButton";
import EditButton from "@/components/EditButton";
import DeleteButton from "@/components/DeleteButton";
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
    const router = useRouter();

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
    const [isDeleting, setIsDeleting] = useState(false);

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
        setIsDeleting(true);
        const result = await deleteValue("/api/attributes/delete-attribute-value", {
            method: "POST",
            body: JSON.stringify({
                value_id: confirmDelete.value_id,
                attribute_id: confirmDelete.attribute_id,
            }),
        });
        setIsDeleting(false);
        if (result?.value_id || result?.attribute_id) {
            toast.success(t("attr_value_updated_successfully"));
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
                <div className="flex flex-col gap-1">
                    <div className="flex items-center gap-2">
                        <button
                            type="button"
                            onClick={() => router.push("/reference-data")}
                            className="flex items-center gap-2 text-[18px] font-semibold text-black/80 hover:text-black transition-colors"
                        >
                            <ArrowLeft size={18} />
                            {t("reference_data")}
                        </button>
                        <span className="text-[22px] text-black">&gt;</span>
                        <h1 className="font-semibold text-[18px] text-black">{attribute.attribute_display || attribute.attribute_code}</h1>
                    </div>
                    {isHierarchical && (
                        <span className="text-[14px] text-gray-400">
                            {t("attr_hierarchical_hint")}
                        </span>
                    )}
                    {breadcrumb.length > 0 && (
                        <div className="flex items-center gap-1 text-[16px] text-gray-500">
                            <button
                                type="button"
                                onClick={() => handleBreadcrumbClick(-1)}
                                className="hover:text-[#ED7C22] transition-colors"
                            >
                                {t("root")}
                            </button>
                            {breadcrumb.map((crumb, i) => (
                                <span key={crumb.value_id} className="flex items-center gap-1">
                                    <ChevronRight size={14} />
                                    <button
                                        type="button"
                                        onClick={() => handleBreadcrumbClick(i)}
                                        className="hover:text-[#ED7C22] transition-colors max-w-32 truncate"
                                    >
                                        {crumb.value_display || crumb.value_code}
                                    </button>
                                </span>
                            ))}
                        </div>
                    )}
                </div>
                <div className="flex items-center gap-3">
                    {/* Search */}
                    <SearchInput
                        value={searchText}
                        onChange={setSearchText}
                        placeholder={t("search_attribute_values")}
                    />

                    <Can action={REFERENCE_DATA_ACTIONS.create}>
                        <AddButton
                            onClick={() => setValueDialog({ open: true, mode: "add" })}
                            label={t("add_attribute_value")}
                        />
                    </Can>
                </div>
            </div>

            {/* Table */}
            {loading ? (
                <TableSkeleton rows={10} columns={4} columnWidths={["25%", "25%", "25%", "25%"]} />
            ) : (
                <div className="bg-white rounded-[10px] pt-6 pb-3 shadow-sm">
                    <div className="overflow-auto">
                        <table className="w-full border-collapse bg-white table-fixed">
                            <thead>
                                <tr>
                                    <th className="text-left pb-3 px-9 border-b border-gray-200 font-semibold text-[#ED7C22] text-[16px] tracking-wider" style={{ width: "25%" }}>
                                        {t("col_no")}
                                    </th>
                                    <th className="text-left pb-3 px-9 border-b border-gray-200 font-semibold text-[#ED7C22] text-[16px] tracking-wider" style={{ width: "25%" }}>
                                        {t("value_display")}
                                    </th>
                                    <th className="text-left pb-3 px-9 border-b border-gray-200 font-semibold text-[#ED7C22] text-[16px] tracking-wider" style={{ width: "25%" }}>
                                        {t("sort_order")}
                                    </th>
                                    <th className="text-left pb-3 px-9 border-b border-gray-200 font-semibold text-[#ED7C22] text-[16px] tracking-wider" style={{ width: "25%" }}>
                                        {t("col_actions")}
                                    </th>
                                </tr>
                            </thead>
                            <tbody>
                                {pageRows.length === 0 ? (
                                    <tr>
                                        <td
                                            colSpan={4}
                                            className="text-center py-10 px-4 text-gray-600"
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
                                                className={`cursor-pointer transition-colors duration-150 ${idx % 2 === 1 ? 'bg-white' : 'bg-gray-50'} hover:bg-gray-100`}
                                                onClick={() => handleDrillDown(item)}
                                            >
                                                <td className="py-2 px-9 align-middle">
                                                    <div className="text-[16px] text-gray-500">
                                                        {String(
                                                            (currentPage - 1) * PAGE_SIZE + idx + 1,
                                                        ).padStart(2, "0")}
                                                    </div>
                                                </td>
                                                <td className="py-2 px-9 align-middle">
                                                    <div className="flex items-center gap-2">
                                                        <div className="text-[16px] text-black truncate" title={item.value_display || item.value_code}>
                                                            {item.value_display || item.value_code}
                                                        </div>
                                                        {hasChildren && (
                                                            <ChevronRight
                                                                size={16}
                                                                className="text-[#ED7C22] shrink-0"
                                                            />
                                                        )}
                                                    </div>
                                                </td>
                                                <td className="py-2 px-9 align-middle">
                                                    <div className="text-[16px] text-gray-600">
                                                        {item.sort_order ?? 0}
                                                    </div>
                                                </td>
                                                <td
                                                    className="py-2 px-9 align-middle"
                                                    onClick={(e) => e.stopPropagation()}
                                                >
                                                    <div className="flex items-center justify-start gap-4">
                                                        <Can action={REFERENCE_DATA_ACTIONS.edit}>
                                                            <EditButton
                                                                onClick={() =>
                                                                    setValueDialog({
                                                                        open: true,
                                                                        mode: "edit",
                                                                        value: item,
                                                                    })
                                                                }
                                                                title={t("edit")}
                                                            >
                                                                {t("edit")}
                                                            </EditButton>
                                                        </Can>
                                                        <Can action={REFERENCE_DATA_ACTIONS.delete}>
                                                            <DeleteButton
                                                                onClick={() =>
                                                                    setConfirmDelete(item)
                                                                }
                                                                loading={isDeleting && confirmDelete?.value_id === item.value_id}
                                                                title={t("delete")}
                                                            >
                                                                {isDeleting && confirmDelete?.value_id === item.value_id ? "Deleting" : t("delete")}
                                                            </DeleteButton>
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

                    {/* Pagination */}
                    {attributeValues.length > PAGE_SIZE && (
                        <div className="shrink-0 border-t border-gray-200 px-4 pt-3 flex justify-end">
                            <Pagination
                                page={currentPage}
                                pageSize={PAGE_SIZE}
                                total={attributeValues.length}
                                onPageChange={setPage}
                            />
                        </div>
                    )}
                </div>
            )}

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
                confirming={isDeleting}
                confirmLabel={t("delete")}
                onConfirm={proceedDelete}
                onClose={() => setConfirmDelete(null)}
            />
        </div>
    );
}
