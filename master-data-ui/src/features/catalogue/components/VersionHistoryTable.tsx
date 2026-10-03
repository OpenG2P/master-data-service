"use client";

import type { ReactNode } from "react";
import { useTranslations } from "next-intl";
import EditButton from "@/components/EditButton";
import type { VersionInfo, VersionRef } from "../types";
import { StatusBadge, formatDateTime, personLabel, tdClass, thClass } from "./ui";

/** Version history (newest first) with a "View" action per version. */
export default function VersionHistoryTable<V extends VersionInfo>({
    versions,
    onView,
    extraHeader,
    extraCell,
}: {
    versions: V[];
    onView: (ref: VersionRef) => void;
    extraHeader?: string;
    extraCell?: (v: V) => ReactNode;
}) {
    const t = useTranslations();
    const sorted = [...versions].sort((a, b) => b.version_no - a.version_no);

    if (sorted.length === 0) {
        return <p className="py-6 text-center text-[14px] text-gray-500">{t("cat_no_versions")}</p>;
    }

    return (
        <div className="overflow-auto">
            <table className="w-full min-w-[900px] border-collapse">
                <thead>
                    <tr>
                        <th className={thClass}>{t("cat_version")}</th>
                        <th className={thClass}>{t("col_status")}</th>
                        <th className={thClass}>{t("cat_effective_from")}</th>
                        <th className={thClass}>{t("cat_made_by")}</th>
                        <th className={thClass}>{t("cat_decided")}</th>
                        {extraHeader ? <th className={thClass}>{extraHeader}</th> : null}
                        <th className={thClass}>{t("cat_notes")}</th>
                        <th className={thClass}>{t("col_actions")}</th>
                    </tr>
                </thead>
                <tbody>
                    {sorted.map((v, i) => {
                        const open = v.status === "DRAFT" || v.status === "SUBMITTED";
                        return (
                            <tr key={v.version_no} className={i % 2 ? "bg-white" : "bg-gray-50"}>
                                <td className={`${tdClass} font-semibold`}>v{v.version_no}</td>
                                <td className={tdClass}>
                                    <div className="flex flex-wrap gap-1">
                                        <StatusBadge status={v.status} label={t(`cat_status_${v.status}`)} />
                                        {v.is_latest ? <StatusBadge status="LATEST" label={t("cat_in_effect")} /> : null}
                                    </div>
                                </td>
                                <td className={`${tdClass} text-[13px]`}>{formatDateTime(v.effective_from)}</td>
                                <td className={`${tdClass} text-[13px]`}>
                                    <div>{personLabel(v.created_by, v.created_by_name)}</div>
                                    {v.submitted_by ? (
                                        <div className="text-gray-500">
                                            {t("cat_submitted_by_at", {
                                                by: personLabel(v.submitted_by, v.submitted_by_name),
                                                at: formatDateTime(v.submitted_at),
                                            })}
                                        </div>
                                    ) : null}
                                </td>
                                <td className={`${tdClass} text-[13px]`}>
                                    {v.decided_by ? (
                                        <>
                                            <div>{personLabel(v.decided_by, v.decided_by_name)}</div>
                                            <div className="text-gray-500">{formatDateTime(v.decided_at || v.published_at)}</div>
                                        </>
                                    ) : (
                                        "—"
                                    )}
                                </td>
                                {extraHeader ? <td className={`${tdClass} text-[13px]`}>{extraCell?.(v)}</td> : null}
                                <td className={`${tdClass} max-w-xs text-[13px]`}>
                                    {v.change_note ? <div className="break-words">{v.change_note}</div> : null}
                                    {v.decision_note ? (
                                        <div className="break-words text-gray-500">
                                            {t("cat_decision_note")}: {v.decision_note}
                                        </div>
                                    ) : null}
                                    {!v.change_note && !v.decision_note ? "—" : null}
                                </td>
                                <td className={tdClass}>
                                    <EditButton title={t("view")} onClick={() => onView(open ? "draft" : v.version_no)}>
                                        {t("view")}
                                    </EditButton>
                                </td>
                            </tr>
                        );
                    })}
                </tbody>
            </table>
        </div>
    );
}
