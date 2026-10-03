"use client";

import { useMemo, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import Button from "@/components/Button";
import { toast } from "react-toastify";
import { errorMessage, useCatalogueApi } from "@/features/catalogue/api";
import I18nLabelsEditor from "@/features/catalogue/components/I18nLabelsEditor";
import TypedAttributeFields from "@/features/catalogue/components/TypedAttributeFields";
import { ErrorBox, Field, Modal, inputClass, localizedLabel } from "@/features/catalogue/components/ui";
import type { DraftValueInput, ListSummary, ListValue, UpsertDraftValuesResponse } from "@/features/catalogue/types";

type AttributeValueDialogProps = {
    open: boolean;
    mode: "add" | "edit";
    list: ListSummary;
    /** All values of the draft (for the parent picker). */
    allValues: ListValue[];
    parentCode?: string | null;
    value?: ListValue;
    onClose: () => void;
    onSuccess?: () => void;
};

/** Codes of `code` and all its descendants (a value cannot move under itself). */
function subtree(code: string, values: ListValue[]): Set<string> {
    const out = new Set([code]);
    let grew = true;
    while (grew) {
        grew = false;
        for (const v of values) {
            if (v.parent_code && out.has(v.parent_code) && !out.has(v.value_code)) {
                out.add(v.value_code);
                grew = true;
            }
        }
    }
    return out;
}

/**
 * Add or change a value in the list's draft (`upsert_draft_values`): code (a changed code keeps the
 * value id, i.e. a RECODE), label, labels per locale, parent (hierarchical lists), sort order and
 * the typed attributes described by the list's attribute schema. Mount while open to reset.
 */
export default function AttributeValueDialog({
    open,
    mode,
    list,
    allValues,
    parentCode,
    value,
    onClose,
    onSuccess,
}: AttributeValueDialogProps) {
    const t = useTranslations();
    const locale = useLocale();
    const call = useCatalogueApi();

    const [code, setCode] = useState(value?.value_code ?? "");
    const [display, setDisplay] = useState(value?.display ?? "");
    const [displayI18n, setDisplayI18n] = useState<Record<string, string>>(value?.display_i18n ?? {});
    const [parent, setParent] = useState<string>((mode === "edit" ? value?.parent_code : parentCode) ?? "");
    const [sortOrder, setSortOrder] = useState(String(value?.sort_order ?? 0));
    const [attributes, setAttributes] = useState<Record<string, unknown>>(value?.attributes ?? {});
    const [error, setError] = useState("");
    const [saveError, setSaveError] = useState<string | null>(null);
    const [saving, setSaving] = useState(false);

    const parentChoices = useMemo(() => {
        if (!list.is_hierarchical) return [];
        const excluded = value ? subtree(value.value_code, allValues) : new Set<string>();
        return allValues.filter((v) => v.status !== "RETIRED" && !excluded.has(v.value_code));
    }, [list.is_hierarchical, allValues, value]);

    const handleSubmit = async () => {
        if (!code.trim()) {
            setError(t("value_code_required"));
            return;
        }
        setError("");
        setSaveError(null);
        setSaving(true);
        const item: DraftValueInput = {
            value_code: code.trim(),
            display: display.trim() || code.trim(),
            display_i18n: displayI18n,
            sort_order: Number(sortOrder) || 0,
            attributes: Object.keys(attributes).length ? attributes : null,
        };
        if (value) item.value_id = value.value_id;
        if (list.is_hierarchical) item.parent_code = parent || null;
        try {
            await call<UpsertDraftValuesResponse>("upsert_draft_values", {
                list_code: list.list_id,
                values: [item],
            });
            toast.success(mode === "add" ? t("attr_value_added_successfully") : t("attr_value_updated_successfully"));
            onSuccess?.();
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
        <Modal
            open={open}
            title={mode === "edit" ? t("edit_reference_data_value") : t("add_attribute_value")}
            onClose={onClose}
            maxWidth={720}
            zIndex="z-50"
        >
            <form
                onSubmit={(event) => {
                    event.preventDefault();
                    void handleSubmit();
                }}
                className="space-y-4"
            >
                <Field label={t("value_code")} required hint={mode === "edit" ? t("cat_recode_hint") : undefined}>
                    <input
                        type="text"
                        value={code}
                        onChange={(e) => setCode(e.target.value)}
                        autoFocus
                        className={inputClass}
                        placeholder={t("value_code_placeholder")}
                    />
                    {error && <p className="text-[14px] text-red-500">{error}</p>}
                </Field>

                <Field label={t("cat_display")} required={mode === "add"}>
                    <input type="text" value={display} onChange={(e) => setDisplay(e.target.value)} className={inputClass} />
                </Field>

                <Field label={t("cat_display_i18n")} group>
                    <I18nLabelsEditor value={displayI18n} onChange={setDisplayI18n} />
                </Field>

                {list.is_hierarchical ? (
                    <Field label={t("cat_parent_value")}>
                        <select value={parent} onChange={(e) => setParent(e.target.value)} className={inputClass}>
                            <option value="">{t("cat_top_level")}</option>
                            {parentChoices.map((v) => (
                                <option key={v.value_id} value={v.value_code}>
                                    {localizedLabel(v.display, v.display_i18n, locale) || v.value_code} ({v.value_code})
                                </option>
                            ))}
                        </select>
                    </Field>
                ) : null}

                <Field label={t("sort_order")}>
                    <input type="number" value={sortOrder} onChange={(e) => setSortOrder(e.target.value)} className={inputClass} />
                </Field>

                <div className="space-y-3 border-t border-gray-200 pt-4">
                    <h3 className="text-[14px] font-semibold text-black">{t("cat_attributes")}</h3>
                    <TypedAttributeFields schema={list.attribute_schema} value={attributes} onChange={setAttributes} />
                </div>

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
