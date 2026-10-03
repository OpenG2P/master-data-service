"use client";

import { useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { toast } from "react-toastify";
import Button from "@/components/Button";
import ConfirmDialog from "@/components/ConfirmDialog";
import { useRbac } from "@/context/RbacContext";
import { errorMessage, useCatalogueApi } from "../api";
import { useIsMaker } from "../hooks";
import type { VersionInfo, VersionRef } from "../types";
import NoteDialog, { type NoteDialogResult } from "./NoteDialog";
import { StatusBadge, formatDateTime, personLabel } from "./ui";

export interface DraftOps {
    create: string;
    update: string;
    submit: string;
    approve: string;
    reject: string;
    discard: string;
}

export const LIST_DRAFT_OPS: DraftOps = {
    create: "create_list_draft",
    update: "update_list_draft",
    submit: "submit_draft",
    approve: "approve_draft",
    reject: "reject_draft",
    discard: "discard_draft",
};

export const GEO_DRAFT_OPS: DraftOps = {
    create: "create_geo_draft",
    update: "update_geo_draft",
    submit: "submit_geo_draft",
    approve: "approve_geo_draft",
    reject: "reject_geo_draft",
    discard: "discard_geo_draft",
};

export function versionRefToString(ref: VersionRef): string {
    return String(ref);
}

export function parseVersionRef(value: string): VersionRef {
    if (value === "latest" || value === "draft") return value;
    const n = Number(value);
    return Number.isInteger(n) ? n : "latest";
}

/** The open draft (DRAFT or SUBMITTED) among the versions, if any. */
export function findOpenDraft<V extends VersionInfo>(versions: V[] | undefined): V | null {
    return versions?.find((v) => v.status === "DRAFT" || v.status === "SUBMITTED") ?? null;
}

interface VersionBarProps {
    versions: VersionInfo[];
    selected: VersionRef;
    onSelect: (ref: VersionRef) => void;
    /** Version info of the data on screen (from the read's `version` object). */
    shown?: VersionInfo | null;
    /** Payload identifying the subject (e.g. `{list_code}`); `{}` for geography. */
    subject: Record<string, unknown>;
    ops: DraftOps;
    editPermission: string;
    publishPermission: string;
    approvalMode?: "permission" | "awe" | null;
    /** Called after any lifecycle action; `select` is the version to show next. */
    onChanged: (select?: VersionRef) => void;
}

type Pending =
    | { kind: "create"; copyFrom?: number }
    | { kind: "update" }
    | { kind: "submit" }
    | { kind: "approve" }
    | { kind: "reject" }
    | null;

/**
 * Version selector, version badge and the draft lifecycle actions (open / edit details / submit /
 * approve / reject / discard) shared by lists and geography.
 */
export default function VersionBar({
    versions,
    selected,
    onSelect,
    shown,
    subject,
    ops,
    editPermission,
    publishPermission,
    approvalMode,
    onChanged,
}: VersionBarProps) {
    const t = useTranslations();
    const call = useCatalogueApi();
    const { can } = useRbac();
    const isMaker = useIsMaker();
    const [pending, setPending] = useState<Pending>(null);
    const [confirmDiscard, setConfirmDiscard] = useState(false);
    const [discarding, setDiscarding] = useState(false);

    const draft = findOpenDraft(versions);
    const latest = versions.find((v) => v.is_latest) ?? null;
    const canEdit = can(editPermission);
    const canPublish = can(publishPermission);
    const sorted = useMemo(() => [...versions].sort((a, b) => b.version_no - a.version_no), [versions]);

    const selectedValue = String(selected);
    const shownVersion =
        shown ??
        (selected === "draft"
            ? draft
            : selected === "latest"
              ? latest
              : versions.find((v) => v.version_no === selected) ?? null);

    const run = async (op: string, payload: Record<string, unknown>, success: string, select?: VersionRef) => {
        await call(op, { ...subject, ...payload });
        toast.success(success);
        setPending(null);
        onChanged(select);
    };

    const onNoteConfirm = async (r: NoteDialogResult) => {
        if (!pending) return;
        switch (pending.kind) {
            case "create":
                return run(
                    ops.create,
                    {
                        change_note: r.note,
                        effective_from: r.effective_from,
                        ...(pending.copyFrom ? { copy_from_version: pending.copyFrom } : {}),
                    },
                    t("cat_draft_opened"),
                    "draft",
                );
            case "update":
                return run(
                    ops.update,
                    { change_note: r.note ?? null, effective_from: r.effective_from ?? null },
                    t("cat_draft_updated"),
                    "draft",
                );
            case "submit":
                return run(
                    ops.submit,
                    { change_note: r.note, effective_from: r.effective_from },
                    t("cat_draft_submitted"),
                    "draft",
                );
            case "approve":
                return run(
                    ops.approve,
                    { version_no: draft?.version_no, decision_note: r.note, effective_from: r.effective_from },
                    t("cat_draft_approved"),
                    draft?.version_no,
                );
            case "reject":
                return run(
                    ops.reject,
                    { version_no: draft?.version_no, decision_note: r.note },
                    t("cat_draft_rejected"),
                    draft?.version_no,
                );
        }
    };

    const discard = async () => {
        setDiscarding(true);
        try {
            await call(ops.discard, { ...subject });
            toast.success(t("cat_draft_discarded"));
            setConfirmDiscard(false);
            onChanged("latest");
        } catch (e) {
            toast.error(errorMessage(e));
        } finally {
            setDiscarding(false);
        }
    };

    const optionLabel = (v: VersionInfo) => {
        const parts = [`v${v.version_no}`, t(`cat_status_${v.status}`)];
        if (v.is_latest) parts.push(t("cat_in_effect"));
        else if (v.status === "PUBLISHED" && v.effective_from && new Date(v.effective_from) > new Date())
            parts.push(t("cat_from_date", { date: formatDateTime(v.effective_from) }));
        return parts.join(" · ");
    };

    const maker = isMaker(draft);
    const showDecide = draft?.status === "SUBMITTED" && approvalMode === "permission" && canPublish;
    const rejectedSelected =
        shownVersion?.status === "REJECTED" && !draft && canEdit ? shownVersion.version_no : undefined;

    return (
        <div className="bg-white rounded-[10px] px-5 py-4 shadow-sm space-y-3">
            <div className="flex flex-wrap items-center gap-3">
                <label className="flex items-center gap-2 text-[14px] font-semibold text-black">
                    {t("cat_version")}
                    <select
                        value={selectedValue}
                        onChange={(e) => onSelect(parseVersionRef(e.target.value))}
                        className="h-9 rounded border border-gray-300 bg-white px-2 text-[14px] font-normal outline-none focus:border-[#EABB13]"
                    >
                        {latest || !draft ? (
                            <option value="latest">
                                {latest ? t("cat_version_latest_no", { no: latest.version_no }) : t("cat_version_latest")}
                            </option>
                        ) : null}
                        {draft ? (
                            <option value="draft">
                                {t("cat_version_draft_no", {
                                    no: draft.version_no,
                                    status: t(`cat_status_${draft.status}`),
                                })}
                            </option>
                        ) : null}
                        {sorted
                            .filter((v) => v.version_no !== draft?.version_no)
                            .map((v) => (
                                <option key={v.version_no} value={String(v.version_no)}>
                                    {optionLabel(v)}
                                </option>
                            ))}
                    </select>
                </label>

                {shownVersion ? (
                    <div className="flex flex-wrap items-center gap-2 text-[13px] text-gray-600">
                        <span className="font-semibold text-black">v{shownVersion.version_no}</span>
                        <StatusBadge
                            status={shownVersion.status}
                            label={t(`cat_status_${shownVersion.status}`)}
                        />
                        {shownVersion.is_latest ? <StatusBadge status="LATEST" label={t("cat_in_effect")} /> : null}
                        {shownVersion.effective_from ? (
                            <span>
                                {t("cat_effective_from")}: {formatDateTime(shownVersion.effective_from)}
                            </span>
                        ) : null}
                        {shownVersion.status === "PUBLISHED" ? (
                            <span>
                                {t("cat_published_by_at", {
                                    by: personLabel(shownVersion.decided_by, shownVersion.decided_by_name),
                                    at: formatDateTime(shownVersion.published_at),
                                })}
                            </span>
                        ) : null}
                        {shownVersion.status === "DRAFT" || shownVersion.status === "SUBMITTED" ? (
                            <span>
                                {t("cat_created_by_at", {
                                    by: personLabel(shownVersion.created_by, shownVersion.created_by_name),
                                    at: formatDateTime(shownVersion.created_at),
                                })}
                                {shownVersion.base_version_no
                                    ? ` · ${t("cat_based_on", { no: shownVersion.base_version_no })}`
                                    : ""}
                            </span>
                        ) : null}
                        {shownVersion.status === "SUBMITTED" ? (
                            <span>
                                {t("cat_submitted_by_at", {
                                    by: personLabel(shownVersion.submitted_by, shownVersion.submitted_by_name),
                                    at: formatDateTime(shownVersion.submitted_at),
                                })}
                            </span>
                        ) : null}
                        {shownVersion.status === "REJECTED" ? (
                            <span>
                                {t("cat_rejected_by_at", {
                                    by: personLabel(shownVersion.decided_by, shownVersion.decided_by_name),
                                    at: formatDateTime(shownVersion.decided_at),
                                })}
                            </span>
                        ) : null}
                    </div>
                ) : null}

                <div className="ml-auto flex flex-wrap items-center gap-2">
                    {!draft && canEdit ? (
                        <Button variant="warning" onClick={() => setPending({ kind: "create" })}>
                            {t("cat_open_draft")}
                        </Button>
                    ) : null}
                    {rejectedSelected ? (
                        <Button
                            variant="secondary"
                            onClick={() => setPending({ kind: "create", copyFrom: rejectedSelected })}
                        >
                            {t("cat_rework_rejected")}
                        </Button>
                    ) : null}
                    {draft && selected !== "draft" ? (
                        <Button variant="secondary" onClick={() => onSelect("draft")}>
                            {t("cat_view_draft")}
                        </Button>
                    ) : null}
                    {draft?.status === "DRAFT" && canEdit ? (
                        <>
                            <Button variant="secondary" onClick={() => setPending({ kind: "update" })}>
                                {t("cat_edit_draft_details")}
                            </Button>
                            <Button variant="primary" onClick={() => setPending({ kind: "submit" })}>
                                {t("cat_submit")}
                            </Button>
                        </>
                    ) : null}
                    {showDecide && !maker ? (
                        <>
                            <Button variant="primary" onClick={() => setPending({ kind: "approve" })}>
                                {t("cat_approve")}
                            </Button>
                            <Button variant="danger" onClick={() => setPending({ kind: "reject" })}>
                                {t("cat_reject")}
                            </Button>
                        </>
                    ) : null}
                    {draft && canEdit && (draft.status === "DRAFT" || approvalMode === "permission") ? (
                        <Button variant="secondary" onClick={() => setConfirmDiscard(true)}>
                            {t("cat_discard")}
                        </Button>
                    ) : null}
                </div>
            </div>

            {draft?.status === "SUBMITTED" ? (
                <p className="rounded bg-amber-50 px-3 py-2 text-[13px] text-amber-800">
                    {approvalMode === "awe"
                        ? t("cat_awaiting_awe", { ref: draft.approval_ref || "—" })
                        : showDecide && maker
                          ? t("cat_maker_cannot_approve")
                          : t("cat_awaiting_approval")}
                </p>
            ) : null}
            {shownVersion?.change_note ? (
                <p className="text-[13px] text-gray-600">
                    <span className="font-semibold">{t("cat_change_note")}:</span> {shownVersion.change_note}
                </p>
            ) : null}
            {shownVersion?.decision_note ? (
                <p className="text-[13px] text-gray-600">
                    <span className="font-semibold">{t("cat_decision_note")}:</span> {shownVersion.decision_note}
                </p>
            ) : null}

            {pending ? (
                <NoteDialog
                    open
                    title={
                        pending.kind === "create"
                            ? pending.copyFrom
                                ? t("cat_rework_rejected")
                                : t("cat_open_draft")
                            : pending.kind === "update"
                              ? t("cat_edit_draft_details")
                              : pending.kind === "submit"
                                ? t("cat_submit_title")
                                : pending.kind === "approve"
                                  ? t("cat_approve_title", { no: draft?.version_no ?? "" })
                                  : t("cat_reject_title", { no: draft?.version_no ?? "" })
                    }
                    message={
                        pending.kind === "submit"
                            ? t("cat_submit_message")
                            : pending.kind === "approve"
                              ? t("cat_approve_message")
                              : undefined
                    }
                    noteLabel={
                        pending.kind === "approve" || pending.kind === "reject"
                            ? t("cat_decision_note")
                            : t("cat_change_note")
                    }
                    noteRequired={pending.kind === "reject"}
                    initialNote={
                        pending.kind === "update" || pending.kind === "submit" ? draft?.change_note : undefined
                    }
                    showEffectiveFrom={pending.kind !== "reject"}
                    initialEffectiveFrom={
                        pending.kind === "update" || pending.kind === "submit" || pending.kind === "approve"
                            ? draft?.effective_from
                            : undefined
                    }
                    effectiveFromHint={pending.kind === "approve" ? t("cat_effective_from_approve_hint") : undefined}
                    confirmLabel={
                        pending.kind === "create"
                            ? t("cat_open_draft")
                            : pending.kind === "update"
                              ? t("save")
                              : pending.kind === "submit"
                                ? t("cat_submit")
                                : pending.kind === "approve"
                                  ? t("cat_approve")
                                  : t("cat_reject")
                    }
                    confirmVariant={pending.kind === "reject" ? "danger" : "primary"}
                    onConfirm={onNoteConfirm}
                    onClose={() => setPending(null)}
                />
            ) : null}

            <ConfirmDialog
                open={confirmDiscard}
                title={t("cat_discard_title")}
                message={t("cat_discard_message", { no: draft?.version_no ?? "" })}
                confirmLabel={t("cat_discard")}
                confirmingLabel={t("cat_discarding")}
                danger
                confirming={discarding}
                onConfirm={() => void discard()}
                onClose={() => setConfirmDiscard(false)}
            />
        </div>
    );
}
