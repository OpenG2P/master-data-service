"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { toast } from "react-toastify";
import Button from "@/components/Button";
import DeleteButton from "@/components/DeleteButton";
import { errorMessage, useCatalogueApi, useCatalogueQuery } from "@/features/catalogue/api";
import {
    ErrorBox,
    Field,
    StatusBadge,
    formatDate,
    formatDateTime,
    inputClass,
    personLabel,
    tdClass,
    textareaClass,
    thClass,
} from "@/features/catalogue/components/ui";
import {
    GEO_CHANGE_TYPES,
    type GeoChangeType,
    type GeoVersionInfo,
    type GetGeoChangesResponse,
} from "@/features/catalogue/types";

function splitUnits(raw: string): string[] {
    return raw
        .split(/[\s,;]+/)
        .map((s) => s.trim())
        .filter(Boolean);
}

/** Change type → which unit lists the form asks for. */
const NEEDS: Record<GeoChangeType, { from: boolean; to: boolean }> = {
    CREATE: { from: false, to: true },
    RETIRE: { from: true, to: false },
    RENAME: { from: true, to: false },
    RECODE: { from: true, to: true },
    SPLIT: { from: true, to: true },
    MERGE: { from: true, to: true },
    REPARENT: { from: true, to: false },
    BOUNDARY_CHANGE: { from: true, to: false },
};

function RecordChangeForm({ onRecorded }: { onRecorded: () => void }) {
    const t = useTranslations();
    const call = useCatalogueApi();
    const [type, setType] = useState<GeoChangeType>("SPLIT");
    const [fromUnits, setFromUnits] = useState("");
    const [toUnits, setToUnits] = useState("");
    const [effectiveDate, setEffectiveDate] = useState("");
    const [note, setNote] = useState("");
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const needs = NEEDS[type];

    const submit = async () => {
        setBusy(true);
        setError(null);
        try {
            await call("record_geo_change", {
                change_type: type,
                from_units: needs.from ? splitUnits(fromUnits) : [],
                to_units: needs.to ? splitUnits(toUnits) : [],
                ...(effectiveDate ? { effective_date: effectiveDate } : {}),
                ...(note.trim() ? { note: note.trim() } : {}),
            });
            toast.success(t("cat_change_recorded"));
            setFromUnits("");
            setToUnits("");
            setNote("");
            onRecorded();
        } catch (e) {
            setError(errorMessage(e));
        } finally {
            setBusy(false);
        }
    };

    return (
        <form
            className="space-y-4 rounded-[10px] border border-gray-200 p-4"
            onSubmit={(e) => {
                e.preventDefault();
                void submit();
            }}
        >
            <h3 className="text-[16px] font-semibold text-black">{t("cat_record_change")}</h3>
            <p className="text-[13px] text-gray-600">{t(`cat_change_rule_${type}`)}</p>
            <div className="grid gap-4 md:grid-cols-2">
                <Field label={t("cat_change_type")} required>
                    <select value={type} onChange={(e) => setType(e.target.value as GeoChangeType)} className={inputClass}>
                        {GEO_CHANGE_TYPES.map((ct) => (
                            <option key={ct} value={ct}>
                                {t(`cat_change_type_${ct}`)}
                            </option>
                        ))}
                    </select>
                </Field>
                <Field label={t("cat_effective_date")} hint={t("cat_effective_date_hint")}>
                    <input type="date" value={effectiveDate} onChange={(e) => setEffectiveDate(e.target.value)} className={inputClass} />
                </Field>
                {needs.from ? (
                    <Field label={t("cat_from_units")} required hint={t("cat_units_input_hint")}>
                        <input
                            type="text"
                            value={fromUnits}
                            onChange={(e) => setFromUnits(e.target.value)}
                            className={`${inputClass} font-mono`}
                        />
                    </Field>
                ) : null}
                {needs.to ? (
                    <Field label={t("cat_to_units")} required hint={t("cat_units_input_hint")}>
                        <input
                            type="text"
                            value={toUnits}
                            onChange={(e) => setToUnits(e.target.value)}
                            className={`${inputClass} font-mono`}
                        />
                    </Field>
                ) : null}
            </div>
            <Field label={t("cat_note")}>
                <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} className={textareaClass} />
            </Field>
            <ErrorBox message={error} />
            <div className="flex justify-end">
                <Button type="submit" loading={busy}>
                    {t("cat_record_change")}
                </Button>
            </div>
        </form>
    );
}

/**
 * Change events (lineage) of a geography version: SPLIT / MERGE / RENAME / RECODE / REPARENT /
 * RETIRE / CREATE / BOUNDARY_CHANGE with from / to units; auto-generated ones (added at submit for
 * anything not covered) are flagged. In the draft, events can be recorded and removed.
 */
export default function GeoChangeEvents({
    shown,
    versions,
    editable,
    onChanged,
}: {
    shown: GeoVersionInfo | null;
    versions: GeoVersionInfo[];
    editable: boolean;
    onChanged: () => void;
}) {
    const t = useTranslations();
    const call = useCatalogueApi();
    const [scope, setScope] = useState<"version" | "all">("version");
    const [unitFilter, setUnitFilter] = useState("");
    const [deleting, setDeleting] = useState<number | null>(null);

    const isOpen = shown?.status === "DRAFT" || shown?.status === "SUBMITTED";
    const maxPublished = versions
        .filter((v) => v.status === "PUBLISHED")
        .reduce((m, v) => Math.max(m, v.version_no), 0);

    let payload: Record<string, unknown> | null = null;
    if (shown) {
        if (scope === "all") {
            payload = { from_version: 0, include_draft: true, ...(maxPublished ? { to_version: maxPublished } : {}) };
        } else if (isOpen) {
            payload = {
                from_version: maxPublished,
                include_draft: true,
                ...(maxPublished ? { to_version: maxPublished } : {}),
            };
        } else {
            payload = { from_version: Math.max(0, shown.version_no - 1), to_version: shown.version_no };
        }
        if (unitFilter.trim()) payload.unit_id = unitFilter.trim();
    }

    const { data, loading, error, reload } = useCatalogueQuery<GetGeoChangesResponse>("get_geo_changes", payload);
    const changes = (data?.changes ?? []).filter((c) => scope === "all" || !shown || c.version_no === shown.version_no);

    const remove = async (changeId: number) => {
        setDeleting(changeId);
        try {
            await call("delete_geo_change", { change_id: changeId });
            toast.success(t("cat_change_deleted"));
            reload();
            onChanged();
        } catch (e) {
            toast.error(errorMessage(e));
        } finally {
            setDeleting(null);
        }
    };

    return (
        <div className="space-y-5">
            {editable ? (
                <RecordChangeForm
                    onRecorded={() => {
                        reload();
                        onChanged();
                    }}
                />
            ) : null}

            <div className="flex flex-wrap items-center gap-3">
                <select
                    value={scope}
                    onChange={(e) => setScope(e.target.value as "version" | "all")}
                    className="h-9 rounded border border-gray-300 bg-white px-2 text-[14px] outline-none focus:border-[#EABB13]"
                >
                    <option value="version">{t("cat_changes_this_version", { no: shown?.version_no ?? "" })}</option>
                    <option value="all">{t("cat_changes_all_versions")}</option>
                </select>
                <input
                    type="text"
                    value={unitFilter}
                    onChange={(e) => setUnitFilter(e.target.value)}
                    placeholder={t("cat_filter_by_unit")}
                    className="h-9 w-56 rounded border border-gray-300 bg-white px-3 font-mono text-[14px] outline-none focus:border-[#EABB13]"
                />
                {shown?.status === "DRAFT" ? (
                    <span className="text-[13px] text-gray-500">{t("cat_auto_events_hint")}</span>
                ) : null}
            </div>

            <ErrorBox message={error} />

            <div className="overflow-auto">
                <table className="w-full min-w-[900px] border-collapse">
                    <thead>
                        <tr>
                            <th className={thClass}>{t("cat_version")}</th>
                            <th className={thClass}>{t("cat_change_type")}</th>
                            <th className={thClass}>{t("cat_from_units")}</th>
                            <th className={thClass}>{t("cat_to_units")}</th>
                            <th className={thClass}>{t("cat_effective_date")}</th>
                            <th className={thClass}>{t("cat_note")}</th>
                            <th className={thClass}>{t("cat_recorded")}</th>
                            {editable ? <th className={thClass}>{t("col_actions")}</th> : null}
                        </tr>
                    </thead>
                    <tbody>
                        {loading && changes.length === 0 ? (
                            <tr>
                                <td colSpan={8} className="py-8 text-center text-gray-500">{t("loading")}</td>
                            </tr>
                        ) : changes.length === 0 ? (
                            <tr>
                                <td colSpan={8} className="py-8 text-center text-gray-500">{t("cat_no_changes")}</td>
                            </tr>
                        ) : (
                            changes.map((c, i) => (
                                <tr key={c.change_id} className={i % 2 ? "bg-white" : "bg-gray-50"}>
                                    <td className={`${tdClass} text-[13px]`}>v{c.version_no}</td>
                                    <td className={tdClass}>
                                        <div className="flex flex-wrap gap-1">
                                            <StatusBadge status="DRAFT" label={t(`cat_change_type_${c.change_type}`)} />
                                            {c.is_auto ? <StatusBadge status="AUTO" label={t("cat_auto")} title={t("cat_auto_hint")} /> : null}
                                        </div>
                                    </td>
                                    <td className={`${tdClass} break-all font-mono text-[12px]`}>{c.from_units.join(", ") || "—"}</td>
                                    <td className={`${tdClass} break-all font-mono text-[12px]`}>{c.to_units.join(", ") || "—"}</td>
                                    <td className={`${tdClass} text-[13px]`}>{formatDate(c.effective_date)}</td>
                                    <td className={`${tdClass} max-w-xs break-words text-[13px]`}>{c.note || "—"}</td>
                                    <td className={`${tdClass} text-[12px] text-gray-600`}>
                                        {personLabel(c.created_by, c.created_by_name)}
                                        <div>{formatDateTime(c.created_at)}</div>
                                    </td>
                                    {editable ? (
                                        <td className={tdClass}>
                                            {c.version_no === shown?.version_no ? (
                                                <DeleteButton loading={deleting === c.change_id} onClick={() => void remove(c.change_id)}>
                                                    {t("delete")}
                                                </DeleteButton>
                                            ) : null}
                                        </td>
                                    ) : null}
                                </tr>
                            ))
                        )}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
