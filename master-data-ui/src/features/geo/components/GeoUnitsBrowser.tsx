"use client";

import { useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { toast } from "react-toastify";
import EditButton from "@/components/EditButton";
import DeleteButton from "@/components/DeleteButton";
import Pagination from "@/components/Pagination";
import SearchInput from "@/components/SearchInput";
import ConfirmDialog from "@/components/ConfirmDialog";
import { errorMessage, useCatalogueApi, useCatalogueQuery } from "@/features/catalogue/api";
import { ErrorBox, StatusBadge, formatDate, localizedLabel, tdClass, thClass } from "@/features/catalogue/components/ui";
import type { CatalogueGeoLevel, GeoUnit, GetGeoUnitsResponse, VersionRef } from "@/features/catalogue/types";
import GeoNodeDialog from "./GeoNodeDialog";

const PAGE_SIZE = 20;

/**
 * Flat, searchable list of a geography version's units (`get_geo_units`, paged on the server):
 * filter by level and parent, search by P-code or name, include retired. In the draft, units can
 * be edited (rename, labels, reparent), retired and re-activated.
 */
export default function GeoUnitsBrowser({
    version,
    levels,
    editable,
    onChanged,
}: {
    version: VersionRef;
    levels: CatalogueGeoLevel[];
    editable: boolean;
    onChanged: () => void;
}) {
    const t = useTranslations();
    const locale = useLocale();
    const call = useCatalogueApi();
    const [level, setLevel] = useState("");
    const [parent, setParent] = useState("");
    const [search, setSearch] = useState("");
    const [includeRetired, setIncludeRetired] = useState(false);
    const [page, setPage] = useState(1);
    const [editing, setEditing] = useState<GeoUnit | null>(null);
    const [retiring, setRetiring] = useState<GeoUnit | null>(null);
    const [busy, setBusy] = useState<string | null>(null);

    const { data, loading, error, reload } = useCatalogueQuery<GetGeoUnitsResponse>(
        "get_geo_units",
        {
            version,
            ...(level ? { level } : {}),
            ...(parent.trim() ? { parent_unit_id: parent.trim() } : {}),
            ...(search.trim() ? { search: search.trim() } : {}),
            include_retired: includeRetired,
        },
        { current_page: page, page_size: PAGE_SIZE },
    );

    const levelName = (id: string) => {
        const l = levels.find((x) => x.level_id === id);
        return l ? localizedLabel(l.display || l.level_mnemonic, l.display_i18n, locale) : id;
    };

    const changed = () => {
        reload();
        onChanged();
    };

    const retire = async () => {
        if (!retiring) return;
        setBusy(retiring.unit_id);
        try {
            const { payload } = await call<{ retired: string[]; removed: string[] }>("retire_draft_units", {
                unit_ids: [retiring.unit_id],
                cascade: true,
            });
            toast.success(t("cat_units_retired", { retired: payload.retired.length, removed: payload.removed.length }));
            changed();
        } catch (e) {
            toast.error(errorMessage(e));
        } finally {
            setBusy(null);
            setRetiring(null);
        }
    };

    const reactivate = async (u: GeoUnit) => {
        setBusy(u.unit_id);
        try {
            await call("upsert_draft_units", {
                units: [{ unit_id: u.unit_id, level_id: u.level_id, name: u.name, status: "ACTIVE" }],
            });
            toast.success(t("cat_unit_reactivated"));
            changed();
        } catch (e) {
            toast.error(errorMessage(e));
        } finally {
            setBusy(null);
        }
    };

    const units = data?.units ?? [];
    const total = data?.total ?? 0;

    return (
        <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-3">
                <select
                    value={level}
                    onChange={(e) => {
                        setLevel(e.target.value);
                        setPage(1);
                    }}
                    className="h-9 rounded border border-gray-300 bg-white px-2 text-[14px] outline-none focus:border-[#EABB13]"
                    aria-label={t("geo_level")}
                >
                    <option value="">{t("cat_all_levels")}</option>
                    {levels.map((l) => (
                        <option key={l.level_id} value={l.level_id}>
                            {levelName(l.level_id)}
                        </option>
                    ))}
                </select>
                <input
                    type="text"
                    value={parent}
                    onChange={(e) => {
                        setParent(e.target.value);
                        setPage(1);
                    }}
                    placeholder={t("cat_parent_unit_filter")}
                    className="h-9 w-48 rounded border border-gray-300 bg-white px-3 font-mono text-[14px] outline-none focus:border-[#EABB13]"
                />
                <SearchInput
                    value={search}
                    onChange={(v) => {
                        setSearch(v);
                        setPage(1);
                    }}
                    placeholder={t("cat_search_units")}
                />
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
                <span className="ml-auto text-[13px] text-gray-500">{t("cat_units_total", { total })}</span>
            </div>

            <ErrorBox message={error} />

            <div className="overflow-auto">
                <table className="w-full min-w-[900px] border-collapse">
                    <thead>
                        <tr>
                            <th className={thClass}>{t("cat_unit_id")}</th>
                            <th className={thClass}>{t("col_name")}</th>
                            <th className={thClass}>{t("geo_level")}</th>
                            <th className={thClass}>{t("cat_parent_unit")}</th>
                            <th className={thClass}>{t("col_status")}</th>
                            <th className={thClass}>{t("cat_valid")}</th>
                            {editable ? <th className={thClass}>{t("col_actions")}</th> : null}
                        </tr>
                    </thead>
                    <tbody>
                        {loading && units.length === 0 ? (
                            <tr>
                                <td colSpan={7} className="py-8 text-center text-gray-500">
                                    {t("loading")}
                                </td>
                            </tr>
                        ) : units.length === 0 ? (
                            <tr>
                                <td colSpan={7} className="py-8 text-center text-gray-500">
                                    {t("no_results")}
                                </td>
                            </tr>
                        ) : (
                            units.map((u, i) => {
                                const retired = u.status === "RETIRED";
                                return (
                                    <tr key={u.unit_id} className={`${i % 2 ? "bg-white" : "bg-gray-50"} ${retired ? "text-gray-400" : ""}`}>
                                        <td className={`${tdClass} font-mono text-[13px]`}>{u.unit_id}</td>
                                        <td className={tdClass}>
                                            <div className={retired ? "line-through" : ""}>{localizedLabel(u.name, u.name_i18n, locale)}</div>
                                            {u.name_i18n && Object.keys(u.name_i18n).length ? (
                                                <div className="text-[12px] text-gray-500">
                                                    {Object.entries(u.name_i18n)
                                                        .map(([l, v]) => `${l}: ${v}`)
                                                        .join(" · ")}
                                                </div>
                                            ) : null}
                                        </td>
                                        <td className={`${tdClass} text-[13px]`}>{levelName(u.level_id)}</td>
                                        <td className={`${tdClass} font-mono text-[13px]`}>{u.parent_unit_id || "—"}</td>
                                        <td className={tdClass}>
                                            <StatusBadge status={u.status} label={t(`cat_status_${u.status}`)} />
                                        </td>
                                        <td className={`${tdClass} text-[12px]`}>
                                            {formatDate(u.valid_from)} – {u.valid_to ? formatDate(u.valid_to) : "…"}
                                        </td>
                                        {editable ? (
                                            <td className={tdClass}>
                                                <div className="flex flex-wrap gap-2">
                                                    {retired ? (
                                                        <EditButton disabled={busy === u.unit_id} onClick={() => void reactivate(u)}>
                                                            {t("cat_reactivate")}
                                                        </EditButton>
                                                    ) : (
                                                        <>
                                                            <EditButton onClick={() => setEditing(u)}>{t("edit")}</EditButton>
                                                            <DeleteButton loading={busy === u.unit_id} onClick={() => setRetiring(u)}>
                                                                {t("cat_retire")}
                                                            </DeleteButton>
                                                        </>
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

            {total > PAGE_SIZE ? (
                <div className="flex justify-end">
                    <Pagination page={page} pageSize={PAGE_SIZE} total={total} onPageChange={setPage} />
                </div>
            ) : null}

            {editing ? (
                <GeoNodeDialog
                    open
                    mode="edit"
                    title={t("geo_edit_level_value")}
                    nameLabel={t("geo_level_value_mnemonic")}
                    levelId={editing.level_id}
                    parentLevelValueId={editing.parent_unit_id ?? null}
                    levelValueId={editing.unit_id}
                    initialName={editing.name}
                    initialNameI18n={editing.name_i18n}
                    onClose={() => setEditing(null)}
                    onSuccess={changed}
                />
            ) : null}

            <ConfirmDialog
                open={Boolean(retiring)}
                title={t("cat_retire_unit_title")}
                message={t("cat_retire_unit_message", { name: retiring?.name ?? "" })}
                confirmLabel={t("cat_retire")}
                confirmingLabel={t("cat_retiring")}
                danger
                confirming={busy !== null}
                onConfirm={() => void retire()}
                onClose={() => setRetiring(null)}
            />
        </div>
    );
}
