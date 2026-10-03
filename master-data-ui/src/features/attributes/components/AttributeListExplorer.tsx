"use client";

import { useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useRouter } from "@/i18n/navigation";
import Can from "@/components/Can";
import SearchInput from "@/components/SearchInput";
import ConfirmDialog from "@/components/ConfirmDialog";
import TableSkeleton from "@/components/TableSkeleton";
import Pagination from "@/components/Pagination";
import AddButton from "@/components/AddButton";
import DeleteButton from "@/components/DeleteButton";
import EditButton from "@/components/EditButton";
import { useFetch } from "@/shared/hooks/useFetch";
import { useCatalogueLists } from "../hooks";
import AttributeDialog from "./AttributeDialog";
import { toast } from "react-toastify";
import { getErrorMessage } from "@/shared/utils/errorHandler";
import { ErrorBox, StatusBadge, localizedLabel } from "@/features/catalogue/components/ui";
import type { ListSummary } from "../types";

const PAGE_SIZE = 10;

export const REFERENCE_DATA_ACTIONS = {
    create: "referenceData:create",
    edit: "referenceData:edit",
    delete: "referenceData:delete",
    publish: "referenceData:publish",
};

const th = "text-left pb-3 px-6 border-b border-gray-200 font-semibold text-[#ED7C22] text-[16px] tracking-wider";

export default function AttributeListExplorer() {
    const t = useTranslations();
    const locale = useLocale();
    const router = useRouter();

    const [page, setPage] = useState(1);
    const [searchText, setSearchText] = useState("");
    const [dialog, setDialog] = useState<{ open: boolean; mode: "add" | "edit"; attribute?: ListSummary }>({
        open: false,
        mode: "add",
    });
    const [confirmDelete, setConfirmDelete] = useState<ListSummary | null>(null);
    const [isDeleting, setIsDeleting] = useState(false);

    const { execute: deleteAttribute } = useFetch();
    const { lists: filtered, loading, error, refresh } = useCatalogueLists(searchText);

    const total = filtered.length;
    const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
    const currentPage = Math.min(page, totalPages);
    const lists = filtered.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);

    // Only a list that was never published can be deleted; a published list is kept forever
    // (its values are retired in a draft instead), so old references still resolve.
    const proceedDelete = async () => {
        if (!confirmDelete) return;
        setIsDeleting(true);
        const result = await deleteAttribute("/api/attributes/delete-attribute", {
            method: "POST",
            body: JSON.stringify({ attribute_id: confirmDelete.list_id, cascade: true }),
        });
        setIsDeleting(false);
        if (result?.attribute_id) {
            toast.success(t("attribute_deleted_successfully"));
            refresh();
        } else {
            const rawError = result?.error || result?.statusText;
            toast.error(getErrorMessage(rawError, result?.code, t));
        }
        setConfirmDelete(null);
    };

    const openDetail = (item: ListSummary) => router.push(`/reference-data/${encodeURIComponent(item.list_id)}`);

    return (
        <div>
            <div className="flex items-center justify-between gap-4 mb-6">
                <h1 className="font-semibold text-[24px] text-black">{t("reference_data")}</h1>
                <div className="flex items-center gap-3">
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

            <ErrorBox message={error} />

            {loading ? (
                <TableSkeleton rows={10} columns={6} />
            ) : (
                <div className="bg-white rounded-[10px] pt-6 pb-3 shadow-sm">
                    <div className="overflow-auto">
                        <table className="w-full min-w-[960px] border-collapse bg-white table-fixed">
                            <thead>
                                <tr>
                                    <th className={th} style={{ width: "6%" }}>{t("col_no")}</th>
                                    <th className={th} style={{ width: "26%" }}>{t("attribute_code")}</th>
                                    <th className={th} style={{ width: "16%" }}>{t("cat_owner_org")}</th>
                                    <th className={th} style={{ width: "13%" }}>{t("cat_published_version")}</th>
                                    <th className={th} style={{ width: "17%" }}>{t("cat_draft")}</th>
                                    <th className={th} style={{ width: "8%" }}>{t("is_hierarchical")}</th>
                                    <th className={th} style={{ width: "14%" }}>{t("col_actions")}</th>
                                </tr>
                            </thead>
                            <tbody>
                                {lists.length === 0 ? (
                                    <tr>
                                        <td colSpan={7} className="text-center py-10 px-4 text-gray-600">
                                            {t("no_attributes")}
                                        </td>
                                    </tr>
                                ) : (
                                    lists.map((item, idx) => {
                                        const label = localizedLabel(item.display, item.display_i18n, locale) || item.list_code || item.list_id;
                                        const pendingNo =
                                            item.latest_published_version_no != null &&
                                            (item.current_version_no == null || item.latest_published_version_no > item.current_version_no)
                                                ? item.latest_published_version_no
                                                : null;
                                        const neverPublished = item.latest_published_version_no == null;
                                        return (
                                            <tr
                                                key={item.list_id}
                                                className={`cursor-pointer transition-colors duration-150 ${idx % 2 === 1 ? "bg-white" : "bg-gray-50"} hover:bg-gray-100`}
                                                onClick={() => openDetail(item)}
                                            >
                                                <td className="py-2 px-6 align-middle text-[16px] text-gray-500">
                                                    {String((currentPage - 1) * PAGE_SIZE + idx + 1).padStart(2, "0")}
                                                </td>
                                                <td className="py-2 px-6 align-middle">
                                                    <div className="text-[16px] text-black truncate" title={label}>{label}</div>
                                                    <div className="text-[12px] font-mono text-gray-500 truncate">{item.list_code}</div>
                                                </td>
                                                <td className="py-2 px-6 align-middle text-[15px] text-gray-700 truncate" title={item.owner_org ?? ""}>
                                                    {item.owner_org || "—"}
                                                </td>
                                                <td className="py-2 px-6 align-middle text-[15px]">
                                                    {item.current_version_no != null ? (
                                                        <span className="font-semibold">v{item.current_version_no}</span>
                                                    ) : (
                                                        <span className="text-gray-500">{t("cat_not_published")}</span>
                                                    )}
                                                </td>
                                                <td className="py-2 px-6 align-middle">
                                                    <div className="flex flex-wrap gap-1">
                                                        {item.open_draft_status ? (
                                                            <StatusBadge
                                                                status={item.open_draft_status}
                                                                label={`${t(`cat_status_${item.open_draft_status}`)} v${item.open_draft_version_no}`}
                                                            />
                                                        ) : null}
                                                        {pendingNo ? (
                                                            <StatusBadge
                                                                status="PENDING"
                                                                label={t("cat_changes_pending")}
                                                                title={t("cat_changes_pending_hint", { no: pendingNo })}
                                                            />
                                                        ) : null}
                                                        {!item.open_draft_status && !pendingNo ? <span className="text-gray-400">—</span> : null}
                                                    </div>
                                                </td>
                                                <td className="py-2 px-6 align-middle text-[15px] text-gray-600">
                                                    {item.is_hierarchical ? t("yes") : t("no")}
                                                </td>
                                                <td className="py-2 px-6 align-middle" onClick={(e) => e.stopPropagation()}>
                                                    <div className="flex flex-wrap items-center justify-start gap-2">
                                                        <Can action={REFERENCE_DATA_ACTIONS.edit}>
                                                            <EditButton onClick={() => setDialog({ open: true, mode: "edit", attribute: item })}>
                                                                {t("edit")}
                                                            </EditButton>
                                                        </Can>
                                                        {neverPublished ? (
                                                            <Can action={REFERENCE_DATA_ACTIONS.delete}>
                                                                <DeleteButton
                                                                    onClick={() => setConfirmDelete(item)}
                                                                    loading={isDeleting && confirmDelete?.list_id === item.list_id}
                                                                >
                                                                    {t("delete")}
                                                                </DeleteButton>
                                                            </Can>
                                                        ) : null}
                                                    </div>
                                                </td>
                                            </tr>
                                        );
                                    })
                                )}
                            </tbody>
                        </table>
                    </div>

                    {total > PAGE_SIZE && (
                        <div className="shrink-0 border-t border-gray-200 px-4 pt-3 flex justify-end">
                            <Pagination page={currentPage} pageSize={PAGE_SIZE} total={total} onPageChange={setPage} />
                        </div>
                    )}
                </div>
            )}

            {dialog.open ? (
                <AttributeDialog
                    open
                    mode={dialog.mode}
                    attribute={dialog.attribute}
                    onClose={() => setDialog({ open: false, mode: "add" })}
                    onSuccess={(result) => {
                        refresh();
                        if (dialog.mode === "add") {
                            router.push(`/reference-data/${encodeURIComponent(result.list.list_id)}`);
                        }
                    }}
                />
            ) : null}

            <ConfirmDialog
                open={!!confirmDelete}
                title={t("confirm_remove_attribute")}
                message={`${t("confirm_remove_attribute_msg")} "${confirmDelete?.display || confirmDelete?.list_code}"?`}
                danger
                confirmLabel={t("delete")}
                confirming={isDeleting}
                onConfirm={proceedDelete}
                onClose={() => setConfirmDelete(null)}
            />
        </div>
    );
}
