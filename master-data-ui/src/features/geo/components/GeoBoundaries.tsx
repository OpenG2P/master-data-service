"use client";

import { useRef, useState } from "react";
import { Download, Upload } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { toast } from "react-toastify";
import { errorMessage, useCatalogueApi } from "@/features/catalogue/api";
import { ErrorBox, localizedLabel, tdClass, thClass } from "@/features/catalogue/components/ui";
import type { CatalogueGeoLevel, GeoVersionInfo, UploadDraftBoundaryResponse } from "@/features/catalogue/types";

/**
 * Boundary GeoJSON per level of a geography version (stored in MinIO / S3 under immutable
 * per-version keys). Download for any version that has one; upload a level's FeatureCollection into
 * the open draft. Only shown when the boundary store is enabled.
 */
export default function GeoBoundaries({
    shown,
    levels,
    editable,
    onChanged,
}: {
    shown: GeoVersionInfo | null;
    levels: CatalogueGeoLevel[];
    editable: boolean;
    onChanged: () => void;
}) {
    const t = useTranslations();
    const locale = useLocale();
    const call = useCatalogueApi();
    const fileInputs = useRef<Record<string, HTMLInputElement | null>>({});
    const [uploading, setUploading] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);

    if (!shown) return null;
    const isOpen = shown.status === "DRAFT" || shown.status === "SUBMITTED";
    const versionParam = isOpen ? "draft" : String(shown.version_no);
    const objects = shown.boundary_objects ?? {};

    const upload = async (level: CatalogueGeoLevel, file: File) => {
        setUploading(level.level_mnemonic);
        setError(null);
        try {
            let geojson: unknown;
            try {
                geojson = JSON.parse(await file.text());
            } catch {
                throw new Error(t("cat_boundary_not_json"));
            }
            const obj = geojson as { type?: unknown };
            if (!obj || obj.type !== "FeatureCollection") throw new Error(t("cat_boundary_not_fc"));
            const { payload } = await call<UploadDraftBoundaryResponse>("upload_draft_boundary", {
                level: level.level_mnemonic,
                geojson,
            });
            toast.success(t("cat_boundary_uploaded", { features: payload.features, level: payload.level }));
            onChanged();
        } catch (e) {
            const message = errorMessage(e);
            setError(message);
            toast.error(message);
        } finally {
            setUploading(null);
            const input = fileInputs.current[level.level_mnemonic];
            if (input) input.value = "";
        }
    };

    return (
        <div className="space-y-4">
            <p className="text-[13px] text-gray-600">{editable ? t("cat_boundary_draft_hint") : t("cat_boundary_hint")}</p>
            <ErrorBox message={error} />
            <table className="w-full table-fixed border-collapse">
                <thead>
                    <tr>
                        <th className={thClass} style={{ width: "25%" }}>{t("geo_level")}</th>
                        <th className={thClass} style={{ width: "45%" }}>{t("cat_object_key")}</th>
                        <th className={thClass} style={{ width: "30%" }}>{t("col_actions")}</th>
                    </tr>
                </thead>
                <tbody>
                    {levels.map((level, i) => {
                        const key = objects[level.level_mnemonic];
                        const ownKey = key ? key.includes(`/v${shown.version_no}/`) : false;
                        return (
                            <tr key={level.level_id} className={i % 2 ? "bg-white" : "bg-gray-50"}>
                                <td className={tdClass}>
                                    {localizedLabel(level.display || level.level_mnemonic, level.display_i18n, locale)}
                                    <div className="font-mono text-[12px] text-gray-500">{level.level_mnemonic}</div>
                                </td>
                                <td className={`${tdClass} break-all font-mono text-[12px]`}>
                                    {key ? (
                                        <>
                                            {key}
                                            {!ownKey ? (
                                                <div className="font-sans text-[12px] text-gray-500">{t("cat_boundary_inherited")}</div>
                                            ) : null}
                                        </>
                                    ) : (
                                        <span className="font-sans text-gray-500">{t("cat_boundary_none")}</span>
                                    )}
                                </td>
                                <td className={tdClass}>
                                    <div className="flex flex-wrap gap-2">
                                        {key ? (
                                            <a
                                                href={`/api/catalogue-boundary?level=${encodeURIComponent(level.level_mnemonic)}&version=${encodeURIComponent(versionParam)}`}
                                                className="inline-flex items-center gap-1 rounded-[10px] bg-[rgba(0,0,0,0.05)] px-3 py-2 text-[14px] font-medium text-black hover:bg-[rgba(0,0,0,0.1)]"
                                            >
                                                <Download size={14} /> {t("cat_download")}
                                            </a>
                                        ) : null}
                                        {editable ? (
                                            <>
                                                <input
                                                    ref={(el) => {
                                                        fileInputs.current[level.level_mnemonic] = el;
                                                    }}
                                                    type="file"
                                                    accept=".geojson,.json,application/geo+json,application/json"
                                                    className="hidden"
                                                    onChange={(e) => {
                                                        const file = e.target.files?.[0];
                                                        if (file) void upload(level, file);
                                                    }}
                                                />
                                                <button
                                                    type="button"
                                                    disabled={uploading !== null}
                                                    onClick={() => fileInputs.current[level.level_mnemonic]?.click()}
                                                    className="inline-flex cursor-pointer items-center gap-1 rounded-[10px] bg-[#f4bb1b] px-3 py-2 text-[14px] font-medium text-black hover:bg-[#e5a818] disabled:opacity-50"
                                                >
                                                    <Upload size={14} />
                                                    {uploading === level.level_mnemonic ? t("cat_uploading") : t("cat_upload_geojson")}
                                                </button>
                                            </>
                                        ) : null}
                                    </div>
                                </td>
                            </tr>
                        );
                    })}
                </tbody>
            </table>
        </div>
    );
}
