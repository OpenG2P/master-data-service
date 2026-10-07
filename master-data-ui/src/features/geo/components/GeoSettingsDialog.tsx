"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { toast } from "react-toastify";
import Button from "@/components/Button";
import { errorMessage, useCatalogueApi } from "@/features/catalogue/api";
import { PublicationFields, type PublicationValue } from "@/features/catalogue/components/Publication";
import { ErrorBox, Modal } from "@/features/catalogue/components/ui";
import type { GeoSettings, GeoSettingsResponse } from "@/features/catalogue/types";

/**
 * Geography settings (`update_geo_settings`): visibility in the public catalogue and licence.
 * Administrative — applied at once, not versioned. Mount while open to reset the fields.
 */
export default function GeoSettingsDialog({
    settings,
    publicCatalogueEnabled,
    onClose,
    onSaved,
}: {
    settings: GeoSettings | null;
    publicCatalogueEnabled?: boolean;
    onClose: () => void;
    onSaved: (settings: GeoSettings) => void;
}) {
    const t = useTranslations();
    const call = useCatalogueApi();
    const [value, setValue] = useState<PublicationValue>({
        visibility: settings?.visibility ?? "private",
        licenceUri: settings?.licence_uri ?? "",
        licenceLabel: settings?.licence_label ?? "",
    });
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const save = async () => {
        setSaving(true);
        setError(null);
        try {
            const { payload } = await call<GeoSettingsResponse>("update_geo_settings", {
                visibility: value.visibility,
                licence_uri: value.licenceUri.trim(),
                licence_label: value.licenceLabel.trim(),
            });
            toast.success(t("cat_geo_settings_saved"));
            onSaved(payload.settings);
            onClose();
        } catch (e) {
            const message = errorMessage(e);
            setError(message);
            toast.error(message);
        } finally {
            setSaving(false);
        }
    };

    return (
        <Modal open title={t("cat_geo_settings")} onClose={onClose} maxWidth={620}>
            <form
                className="space-y-5"
                onSubmit={(e) => {
                    e.preventDefault();
                    void save();
                }}
            >
                <p className="rounded bg-blue-50 px-3 py-2 text-[13px] text-blue-800">{t("cat_geo_settings_hint")}</p>
                <PublicationFields value={value} onChange={setValue} publicCatalogueEnabled={publicCatalogueEnabled} />
                <ErrorBox message={error} />
                <div className="flex w-full justify-end gap-4 pt-2">
                    <Button variant="secondary" onClick={onClose} disabled={saving}>
                        {t("cancel")}
                    </Button>
                    <Button variant="primary" type="submit" loading={saving}>
                        {saving ? t("saving") : t("save")}
                    </Button>
                </div>
            </form>
        </Modal>
    );
}
