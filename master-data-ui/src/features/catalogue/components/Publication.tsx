"use client";

import { useTranslations } from "next-intl";
import { Field, StatusBadge, inputClass } from "./ui";
import type { Visibility } from "../types";

/** Common licences offered in the licence field (free text is allowed too). */
export const LICENCE_PRESETS: { label: string; uri: string }[] = [
    { label: "CC BY 4.0", uri: "https://creativecommons.org/licenses/by/4.0/" },
    { label: "CC BY-SA 4.0", uri: "https://creativecommons.org/licenses/by-sa/4.0/" },
    { label: "CC0 1.0", uri: "https://creativecommons.org/publicdomain/zero/1.0/" },
    { label: "CC BY-IGO", uri: "https://creativecommons.org/licenses/by/3.0/igo/" },
    { label: "ODbL 1.0", uri: "https://opendatacommons.org/licenses/odbl/1-0/" },
];

/** Public / Private pill. */
export function VisibilityBadge({ visibility }: { visibility?: Visibility | null }) {
    const t = useTranslations();
    const isPublic = visibility === "public";
    return (
        <StatusBadge
            status={isPublic ? "PUBLIC" : "PRIVATE"}
            label={isPublic ? t("cat_visibility_public") : t("cat_visibility_private")}
            title={isPublic ? t("cat_visibility_public_hint") : t("cat_visibility_private_hint")}
        />
    );
}

/** "Licence: <label or link>", or nothing when no licence is set. */
export function LicenceText({ uri, label }: { uri?: string | null; label?: string | null }) {
    const t = useTranslations();
    if (!uri && !label) return null;
    return (
        <span>
            {t("cat_licence")}:{" "}
            {uri ? (
                <a href={uri} target="_blank" rel="noreferrer" className="text-blue-700 underline">
                    {label || uri}
                </a>
            ) : (
                <span className="text-gray-800">{label}</span>
            )}
        </span>
    );
}

export interface PublicationValue {
    visibility: Visibility;
    licenceUri: string;
    licenceLabel: string;
}

/**
 * Visibility (private / public) and licence (label + URI) fields, shared by the dataset
 * dialog and the geography settings. Picking a known licence label fills its URI.
 */
export function PublicationFields({
    value,
    onChange,
    publicCatalogueEnabled,
}: {
    value: PublicationValue;
    onChange: (next: PublicationValue) => void;
    publicCatalogueEnabled?: boolean;
}) {
    const t = useTranslations();
    const setLabel = (label: string) => {
        const preset = LICENCE_PRESETS.find((p) => p.label === label.trim());
        onChange({ ...value, licenceLabel: label, licenceUri: preset && !value.licenceUri ? preset.uri : value.licenceUri });
    };
    return (
        <>
            <Field label={t("cat_visibility")} hint={t("cat_visibility_hint")}>
                <select
                    value={value.visibility}
                    onChange={(e) => onChange({ ...value, visibility: e.target.value as Visibility })}
                    className={inputClass}
                >
                    <option value="private">{t("cat_visibility_private")}</option>
                    <option value="public">{t("cat_visibility_public")}</option>
                </select>
                {value.visibility === "public" && publicCatalogueEnabled === false ? (
                    <span className="block text-[12px] text-amber-700">{t("cat_public_catalogue_off_hint")}</span>
                ) : null}
            </Field>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <Field label={t("cat_licence_label")}>
                    <input
                        type="text"
                        value={value.licenceLabel}
                        onChange={(e) => setLabel(e.target.value)}
                        className={inputClass}
                        list="licence-presets"
                        placeholder="CC BY 4.0"
                    />
                    <datalist id="licence-presets">
                        {LICENCE_PRESETS.map((p) => (
                            <option key={p.label} value={p.label} />
                        ))}
                    </datalist>
                </Field>
                <Field label={t("cat_licence_uri")}>
                    <input
                        type="url"
                        value={value.licenceUri}
                        onChange={(e) => onChange({ ...value, licenceUri: e.target.value })}
                        className={inputClass}
                        placeholder="https://creativecommons.org/licenses/by/4.0/"
                    />
                </Field>
            </div>
        </>
    );
}
