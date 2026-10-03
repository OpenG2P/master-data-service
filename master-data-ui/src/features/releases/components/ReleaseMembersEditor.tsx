"use client";

import { useState } from "react";
import { Trash2 } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import Button from "@/components/Button";
import { useCatalogueQuery } from "@/features/catalogue/api";
import { ErrorBox, inputClass, localizedLabel, tdClass, thClass } from "@/features/catalogue/components/ui";
import type {
    GeoVersionInfo,
    GetListVersionsResponse,
    ListSummary,
    ReleaseMember,
} from "@/features/catalogue/types";

export interface MemberRow {
    list_code: string;
    version_no: number | null;
}

/** Published versions of one list, as options. */
function ListVersionSelect({
    listCode,
    value,
    onChange,
}: {
    listCode: string;
    value: number | null;
    onChange: (v: number | null) => void;
}) {
    const t = useTranslations();
    const { data, loading } = useCatalogueQuery<GetListVersionsResponse>(
        "get_list_versions",
        listCode ? { list_code: listCode } : null,
    );
    const published = (data?.versions ?? []).filter((v) => v.status === "PUBLISHED");
    return (
        <select
            value={value == null ? "" : String(value)}
            onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}
            disabled={!listCode || loading}
            className={inputClass}
        >
            <option value="">{loading ? t("loading") : t("cat_select_version")}</option>
            {published.map((v) => (
                <option key={v.version_no} value={String(v.version_no)}>
                    v{v.version_no}
                    {v.is_latest ? ` · ${t("cat_in_effect")}` : ""}
                </option>
            ))}
        </select>
    );
}

/**
 * Edits a draft release's pins: list → published version, plus one published geography version.
 * Saves with `set_release_members` (replace all).
 */
export default function ReleaseMembersEditor({
    members,
    geoVersionNo,
    lists,
    geoVersions,
    onSave,
    onCancel,
}: {
    members: ReleaseMember[];
    geoVersionNo: number | null | undefined;
    lists: ListSummary[];
    geoVersions: GeoVersionInfo[];
    onSave: (rows: { list_code: string; version_no: number }[], geoVersionNo: number | null) => Promise<void>;
    onCancel: () => void;
}) {
    const t = useTranslations();
    const locale = useLocale();
    const [rows, setRows] = useState<MemberRow[]>(() =>
        members.map((m) => ({ list_code: m.list_code, version_no: m.version_no })),
    );
    const [geo, setGeo] = useState<string>(geoVersionNo != null ? String(geoVersionNo) : "");
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const publishedLists = lists.filter((l) => l.latest_published_version_no != null);
    const publishedGeo = geoVersions.filter((v) => v.status === "PUBLISHED").sort((a, b) => b.version_no - a.version_no);
    const used = new Set(rows.map((r) => r.list_code));

    const pinAllCurrent = () => {
        setRows(
            publishedLists
                .filter((l) => l.current_version_no != null)
                .map((l) => ({ list_code: l.list_code || l.list_id, version_no: l.current_version_no ?? null })),
        );
        const geoCurrent = geoVersions.find((v) => v.is_latest);
        if (geoCurrent) setGeo(String(geoCurrent.version_no));
    };

    const save = async () => {
        const incomplete = rows.some((r) => !r.list_code || r.version_no == null);
        if (incomplete) {
            setError(t("cat_release_members_incomplete"));
            return;
        }
        setSaving(true);
        setError(null);
        try {
            await onSave(
                rows.map((r) => ({ list_code: r.list_code, version_no: r.version_no as number })),
                geo ? Number(geo) : null,
            );
        } catch (e) {
            setError(e instanceof Error ? e.message : String(e));
        } finally {
            setSaving(false);
        }
    };

    return (
        <div className="space-y-4">
            <div className="flex flex-wrap items-end gap-4">
                <label className="block space-y-1.5">
                    <span className="text-[12px] font-semibold uppercase tracking-wide text-black">{t("cat_geo_version")}</span>
                    <select value={geo} onChange={(e) => setGeo(e.target.value)} className={`${inputClass} w-56`}>
                        <option value="">{t("cat_no_geo_pin")}</option>
                        {publishedGeo.map((v) => (
                            <option key={v.version_no} value={String(v.version_no)}>
                                v{v.version_no}
                                {v.is_latest ? ` · ${t("cat_in_effect")}` : ""}
                            </option>
                        ))}
                    </select>
                </label>
                <Button variant="secondary" onClick={pinAllCurrent}>
                    {t("cat_pin_all_current")}
                </Button>
            </div>

            <table className="w-full table-fixed border-collapse">
                <thead>
                    <tr>
                        <th className={thClass} style={{ width: "55%" }}>{t("cat_list")}</th>
                        <th className={thClass} style={{ width: "35%" }}>{t("cat_version")}</th>
                        <th className={thClass} style={{ width: "10%" }} />
                    </tr>
                </thead>
                <tbody>
                    {rows.length === 0 ? (
                        <tr>
                            <td colSpan={3} className="py-6 text-center text-[14px] text-gray-500">
                                {t("cat_release_no_members")}
                            </td>
                        </tr>
                    ) : (
                        rows.map((row, idx) => (
                            <tr key={idx} className={idx % 2 ? "bg-white" : "bg-gray-50"}>
                                <td className={tdClass}>
                                    <select
                                        value={row.list_code}
                                        onChange={(e) =>
                                            setRows(rows.map((r, i) => (i === idx ? { list_code: e.target.value, version_no: null } : r)))
                                        }
                                        className={inputClass}
                                    >
                                        <option value="">{t("cat_select_list")}</option>
                                        {publishedLists
                                            .filter((l) => (l.list_code || l.list_id) === row.list_code || !used.has(l.list_code || l.list_id))
                                            .map((l) => (
                                                <option key={l.list_id} value={l.list_code || l.list_id}>
                                                    {localizedLabel(l.display, l.display_i18n, locale) || l.list_code} ({l.list_code})
                                                </option>
                                            ))}
                                    </select>
                                </td>
                                <td className={tdClass}>
                                    <ListVersionSelect
                                        listCode={row.list_code}
                                        value={row.version_no}
                                        onChange={(v) => setRows(rows.map((r, i) => (i === idx ? { ...r, version_no: v } : r)))}
                                    />
                                </td>
                                <td className={tdClass}>
                                    <button
                                        type="button"
                                        onClick={() => setRows(rows.filter((_, i) => i !== idx))}
                                        className="cursor-pointer rounded p-2 text-gray-500 hover:bg-gray-100 hover:text-red-600"
                                        aria-label={t("delete")}
                                        title={t("delete")}
                                    >
                                        <Trash2 size={16} />
                                    </button>
                                </td>
                            </tr>
                        ))
                    )}
                </tbody>
            </table>

            <button
                type="button"
                onClick={() => setRows([...rows, { list_code: "", version_no: null }])}
                className="cursor-pointer text-[14px] font-medium text-gray-700 hover:text-black hover:underline"
            >
                + {t("cat_add_member")}
            </button>

            <ErrorBox message={error} />

            <div className="flex justify-end gap-3">
                <Button variant="secondary" onClick={onCancel} disabled={saving}>
                    {t("cancel")}
                </Button>
                <Button onClick={() => void save()} loading={saving}>
                    {t("save")}
                </Button>
            </div>
        </div>
    );
}
