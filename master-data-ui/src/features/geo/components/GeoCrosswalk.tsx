"use client";

import { useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import Button from "@/components/Button";
import { errorMessage, useCatalogueApi } from "@/features/catalogue/api";
import { ErrorBox, Field, StatusBadge, inputClass, localizedLabel, tdClass, thClass } from "@/features/catalogue/components/ui";
import type { GeoCrosswalkResponse, GeoVersionInfo } from "@/features/catalogue/types";

/**
 * Crosswalk lookup (`get_geo_crosswalk`): where a unit of one geography version went in another
 * (successors going forward, predecessors going backward) and the change events on the way.
 */
export default function GeoCrosswalk({ versions }: { versions: GeoVersionInfo[] }) {
    const t = useTranslations();
    const locale = useLocale();
    const call = useCatalogueApi();
    const published = [...versions].filter((v) => v.status === "PUBLISHED").sort((a, b) => b.version_no - a.version_no);
    const hasDraft = versions.some((v) => v.status === "DRAFT" || v.status === "SUBMITTED");

    const [unitId, setUnitId] = useState("");
    const [fromVersion, setFromVersion] = useState<string>(() => String(published[published.length - 1]?.version_no ?? ""));
    const [toVersion, setToVersion] = useState<string>("latest");
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [result, setResult] = useState<GeoCrosswalkResponse | null>(null);

    const lookup = async () => {
        if (!unitId.trim() || !fromVersion) return;
        setBusy(true);
        setError(null);
        setResult(null);
        try {
            const { payload } = await call<GeoCrosswalkResponse>("get_geo_crosswalk", {
                unit_id: unitId.trim(),
                from_version: Number(fromVersion),
                to_version: toVersion === "latest" || toVersion === "draft" ? toVersion : Number(toVersion),
            });
            setResult(payload);
        } catch (e) {
            setError(errorMessage(e));
        } finally {
            setBusy(false);
        }
    };

    return (
        <div className="space-y-5">
            <p className="text-[13px] text-gray-600">{t("cat_crosswalk_hint")}</p>
            <form
                className="grid items-end gap-4 md:grid-cols-[2fr_1fr_1fr_auto]"
                onSubmit={(e) => {
                    e.preventDefault();
                    void lookup();
                }}
            >
                <Field label={t("cat_unit_id")} required>
                    <input value={unitId} onChange={(e) => setUnitId(e.target.value)} className={`${inputClass} font-mono`} />
                </Field>
                <Field label={t("cat_from_version")} required>
                    <select value={fromVersion} onChange={(e) => setFromVersion(e.target.value)} className={inputClass}>
                        {published.map((v) => (
                            <option key={v.version_no} value={String(v.version_no)}>
                                v{v.version_no}
                            </option>
                        ))}
                    </select>
                </Field>
                <Field label={t("cat_to_version")}>
                    <select value={toVersion} onChange={(e) => setToVersion(e.target.value)} className={inputClass}>
                        <option value="latest">{t("cat_version_latest")}</option>
                        {hasDraft ? <option value="draft">{t("cat_version_draft")}</option> : null}
                        {published.map((v) => (
                            <option key={v.version_no} value={String(v.version_no)}>
                                v{v.version_no}
                            </option>
                        ))}
                    </select>
                </Field>
                <Button type="submit" loading={busy} disabled={!unitId.trim() || !fromVersion}>
                    {t("cat_lookup")}
                </Button>
            </form>

            <ErrorBox message={error} />

            {result ? (
                <div className="space-y-4">
                    <div className="flex flex-wrap items-center gap-2 text-[14px]">
                        <span className="font-mono">{result.unit_id}</span>
                        <span>
                            v{result.from_version} → v{result.to_version}
                        </span>
                        <StatusBadge status="DRAFT" label={t(`cat_direction_${result.direction}`)} />
                        {result.unchanged ? <StatusBadge status="ACTIVE" label={t("cat_unchanged")} /> : null}
                    </div>

                    <section className="space-y-2">
                        <h3 className="text-[15px] font-semibold">
                            {result.direction === "backward" ? t("cat_predecessors") : t("cat_successors")}
                        </h3>
                        {result.units.length === 0 ? (
                            <p className="text-[13px] text-gray-500">{t("cat_no_successors")}</p>
                        ) : (
                            <table className="w-full table-fixed border-collapse">
                                <thead>
                                    <tr>
                                        <th className={thClass}>{t("cat_unit_id")}</th>
                                        <th className={thClass}>{t("col_name")}</th>
                                        <th className={thClass}>{t("cat_parent_unit")}</th>
                                        <th className={thClass}>{t("col_status")}</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {result.units.map((u, i) => (
                                        <tr key={u.unit_id} className={i % 2 ? "bg-white" : "bg-gray-50"}>
                                            <td className={`${tdClass} font-mono text-[13px]`}>{u.unit_id}</td>
                                            <td className={tdClass}>{localizedLabel(u.name, u.name_i18n, locale)}</td>
                                            <td className={`${tdClass} font-mono text-[13px]`}>{u.parent_unit_id || "—"}</td>
                                            <td className={tdClass}>
                                                <StatusBadge status={u.status} label={t(`cat_status_${u.status}`)} />
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        )}
                    </section>

                    {result.unmapped.length ? (
                        <p className="text-[13px] text-amber-800">
                            {t("cat_unmapped")}: <span className="font-mono">{result.unmapped.join(", ")}</span>
                        </p>
                    ) : null}

                    {result.path.length ? (
                        <section className="space-y-2">
                            <h3 className="text-[15px] font-semibold">{t("cat_crosswalk_path")}</h3>
                            <ol className="list-decimal space-y-1 pl-6 text-[13px]">
                                {result.path.map((step) => (
                                    <li key={step.change_id}>
                                        v{step.version_no} · {t(`cat_change_type_${step.change_type}`)} ·{" "}
                                        <span className="font-mono">
                                            {step.from_units.join(", ") || "∅"} → {step.to_units.join(", ") || "∅"}
                                        </span>
                                    </li>
                                ))}
                            </ol>
                        </section>
                    ) : null}
                </div>
            ) : null}
        </div>
    );
}
