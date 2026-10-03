"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import Button from "@/components/Button";
import { toast } from "react-toastify";
import { errorMessage, useCatalogueApi } from "@/features/catalogue/api";
import I18nLabelsEditor from "@/features/catalogue/components/I18nLabelsEditor";
import { ErrorBox, Field, Modal, inputClass, textareaClass } from "@/features/catalogue/components/ui";
import type { ListAndDraftResponse, ListSummary } from "@/features/catalogue/types";

type AttributeDialogProps = {
    open: boolean;
    mode: "add" | "edit";
    attribute?: ListSummary;
    onClose: () => void;
    onSuccess?: (result: ListAndDraftResponse) => void;
};

/**
 * Create a code list (`create_list`, opens its first draft) or edit a list's metadata
 * (`update_list`): description and owner apply at once; code, label, labels and the hierarchy
 * flag go into the list's draft. Mount while open (or change `key`) to reset the fields.
 */
export default function AttributeDialog({ open, mode, attribute, onClose, onSuccess }: AttributeDialogProps) {
    const t = useTranslations();
    const call = useCatalogueApi();

    const [code, setCode] = useState(attribute?.list_code ?? "");
    const [display, setDisplay] = useState(attribute?.display ?? "");
    const [displayI18n, setDisplayI18n] = useState<Record<string, string>>(attribute?.display_i18n ?? {});
    const [description, setDescription] = useState(attribute?.description ?? "");
    const [ownerOrg, setOwnerOrg] = useState(attribute?.owner_org ?? "");
    const [isHierarchical, setIsHierarchical] = useState(attribute?.is_hierarchical ?? false);
    const [changeNote, setChangeNote] = useState("");
    const [error, setError] = useState("");
    const [saveError, setSaveError] = useState<string | null>(null);
    const [saving, setSaving] = useState(false);

    const handleSubmit = async () => {
        if (!code.trim()) {
            setError(t("attr_code_required"));
            return;
        }
        setError("");
        setSaveError(null);
        setSaving(true);
        try {
            let result: ListAndDraftResponse;
            if (mode === "add") {
                ({ payload: result } = await call<ListAndDraftResponse>("create_list", {
                    list_code: code.trim(),
                    display: display.trim() || code.trim(),
                    display_i18n: Object.keys(displayI18n).length ? displayI18n : undefined,
                    description: description.trim() || undefined,
                    owner_org: ownerOrg.trim() || undefined,
                    is_hierarchical: isHierarchical,
                    change_note: changeNote.trim() || undefined,
                }));
            } else {
                const a = attribute!;
                const payload: Record<string, unknown> = { list_code: a.list_id };
                if ((a.description ?? "") !== description.trim()) payload.description = description.trim();
                if ((a.owner_org ?? "") !== ownerOrg.trim()) payload.owner_org = ownerOrg.trim();
                if ((a.list_code ?? "") !== code.trim()) payload.new_list_code = code.trim();
                if ((a.display ?? "") !== display.trim()) payload.display = display.trim() || code.trim();
                if (JSON.stringify(a.display_i18n ?? {}) !== JSON.stringify(displayI18n)) payload.display_i18n = displayI18n;
                if (a.is_hierarchical !== isHierarchical) payload.is_hierarchical = isHierarchical;
                if (Object.keys(payload).length === 1) {
                    onClose();
                    return;
                }
                ({ payload: result } = await call<ListAndDraftResponse>("update_list", payload));
            }
            toast.success(mode === "add" ? t("attribute_added_successfully") : t("attribute_updated_successfully"));
            onSuccess?.(result);
            onClose();
        } catch (e) {
            const message = errorMessage(e);
            setSaveError(message);
            toast.error(message);
        } finally {
            setSaving(false);
        }
    };

    return (
        <Modal open={open} title={mode === "edit" ? t("edit_reference_data") : t("add_new_attribute")} onClose={onClose} maxWidth={680}>
            <form
                className="space-y-5"
                onSubmit={(e) => {
                    e.preventDefault();
                    void handleSubmit();
                }}
            >
                {mode === "edit" ? (
                    <p className="rounded bg-blue-50 px-3 py-2 text-[13px] text-blue-800">{t("cat_list_edit_hint")}</p>
                ) : (
                    <p className="rounded bg-blue-50 px-3 py-2 text-[13px] text-blue-800">{t("cat_list_create_hint")}</p>
                )}
                <Field label={t("attribute_code")} required>
                    <input
                        type="text"
                        value={code}
                        onChange={(e) => setCode(e.target.value)}
                        autoFocus
                        className={inputClass}
                        placeholder={t("attr_code_placeholder")}
                    />
                    {error && <p className="text-[14px] text-red-500">{error}</p>}
                </Field>
                <Field label={t("cat_display")}>
                    <input type="text" value={display} onChange={(e) => setDisplay(e.target.value)} className={inputClass} />
                </Field>
                <Field label={t("cat_display_i18n")} group>
                    <I18nLabelsEditor value={displayI18n} onChange={setDisplayI18n} />
                </Field>
                <Field label={t("cat_description")}>
                    <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={2} className={textareaClass} />
                </Field>
                <Field label={t("cat_owner_org")} hint={t("cat_owner_org_hint")}>
                    <input type="text" value={ownerOrg} onChange={(e) => setOwnerOrg(e.target.value)} className={inputClass} />
                </Field>
                <label className="flex cursor-pointer items-center gap-3">
                    <input
                        type="checkbox"
                        checked={isHierarchical}
                        onChange={(e) => setIsHierarchical(e.target.checked)}
                        className="h-5 w-5 accent-[#f4bb1b]"
                    />
                    <span className="text-[16px] font-medium text-black">{t("is_hierarchical")}</span>
                </label>
                {mode === "add" ? (
                    <Field label={t("cat_change_note")}>
                        <input type="text" value={changeNote} onChange={(e) => setChangeNote(e.target.value)} className={inputClass} />
                    </Field>
                ) : null}

                <ErrorBox message={saveError} />

                <div className="flex gap-4 w-full justify-end pt-2">
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
