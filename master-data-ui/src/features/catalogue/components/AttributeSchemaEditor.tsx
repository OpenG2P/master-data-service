"use client";

import { useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import Button from "@/components/Button";
import { EXAMPLE_ATTRIBUTE_SCHEMA, schemaProperties, listRefOf, validateAttributeSchema } from "../schema";
import type { JsonSchema } from "../types";
import { ErrorBox, tdClass, thClass } from "./ui";

function pretty(schema: JsonSchema | null | undefined): string {
    return schema ? JSON.stringify(schema, null, 2) : "";
}

/**
 * JSON editor for a list's `attribute_schema` (JSON Schema for each value's `attributes`, with
 * `x-list-ref` to other lists). Validates as you type; saving writes into the list's draft.
 * Remount with a new `key` to reset the text from `value`.
 */
export default function AttributeSchemaEditor({
    value,
    knownLists,
    readOnly,
    onSave,
}: {
    value: JsonSchema | null | undefined;
    knownLists: string[];
    readOnly: boolean;
    onSave: (schema: JsonSchema | null) => Promise<void>;
}) {
    const t = useTranslations();
    const [text, setText] = useState(() => pretty(value));
    const [saving, setSaving] = useState(false);
    const [saveError, setSaveError] = useState<string | null>(null);

    const parsed = useMemo((): { schema: JsonSchema | null; error?: string } => {
        if (!text.trim()) return { schema: null };
        try {
            return { schema: JSON.parse(text) as JsonSchema };
        } catch (e) {
            return { schema: null, error: e instanceof Error ? e.message : String(e) };
        }
    }, [text]);

    const issues = useMemo(
        () => (parsed.error || !parsed.schema ? [] : validateAttributeSchema(parsed.schema, knownLists)),
        [parsed, knownLists],
    );
    const dirty = text.trim() !== pretty(value).trim();
    const valid = !parsed.error && issues.length === 0;
    const props = schemaProperties(parsed.schema ?? value ?? null);

    const save = async () => {
        setSaving(true);
        setSaveError(null);
        try {
            await onSave(parsed.schema);
        } catch (e) {
            setSaveError(e instanceof Error ? e.message : String(e));
        } finally {
            setSaving(false);
        }
    };

    return (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
            <div className="space-y-3">
                <p className="text-[13px] text-gray-600">{t("cat_schema_help")}</p>
                <textarea
                    value={text}
                    onChange={(e) => setText(e.target.value)}
                    readOnly={readOnly}
                    spellCheck={false}
                    rows={22}
                    aria-label={t("cat_attribute_schema")}
                    placeholder={readOnly ? t("cat_schema_none") : t("cat_schema_placeholder")}
                    className={`w-full rounded border bg-white p-3 font-mono text-[13px] leading-5 text-black outline-none focus:border-[#EABB13] ${
                        parsed.error || issues.length ? "border-red-300" : "border-gray-300"
                    } ${readOnly ? "bg-gray-50" : ""}`}
                />
                {parsed.error ? <ErrorBox message={t("cat_schema_invalid_json", { error: parsed.error })} /> : null}
                {issues.length > 0 ? (
                    <ul className="list-disc space-y-1 rounded border border-red-200 bg-red-50 py-2 pl-8 pr-3 text-[13px] text-red-700">
                        {issues.map((issue, i) => (
                            <li key={i}>{t(issue.key, issue.values ?? {})}</li>
                        ))}
                    </ul>
                ) : null}
                {!parsed.error && issues.length === 0 && text.trim() ? (
                    <p className="text-[13px] text-green-700">{t("cat_schema_valid")}</p>
                ) : null}
                <ErrorBox message={saveError} />
                {!readOnly ? (
                    <div className="flex flex-wrap gap-3">
                        <Button variant="primary" onClick={() => void save()} disabled={!dirty || !valid} loading={saving}>
                            {t("cat_schema_save")}
                        </Button>
                        <Button variant="secondary" onClick={() => setText(pretty(value))} disabled={!dirty || saving}>
                            {t("cat_reset")}
                        </Button>
                        <Button
                            variant="secondary"
                            onClick={() => setText(JSON.stringify(EXAMPLE_ATTRIBUTE_SCHEMA, null, 2))}
                            disabled={saving}
                        >
                            {t("cat_schema_example")}
                        </Button>
                        {value ? (
                            <Button variant="secondary" onClick={() => setText("")} disabled={saving}>
                                {t("cat_schema_clear")}
                            </Button>
                        ) : null}
                    </div>
                ) : (
                    <p className="text-[13px] text-gray-500">{t("cat_schema_readonly")}</p>
                )}
            </div>

            <div className="space-y-2">
                <h3 className="text-[16px] font-semibold text-black">{t("cat_schema_fields")}</h3>
                {props.length === 0 ? (
                    <p className="text-[13px] text-gray-500">{t("cat_schema_none")}</p>
                ) : (
                    <table className="w-full table-fixed border-collapse">
                        <thead>
                            <tr>
                                <th className={thClass}>{t("cat_field")}</th>
                                <th className={thClass}>{t("cat_type")}</th>
                                <th className={thClass}>{t("cat_list_ref")}</th>
                            </tr>
                        </thead>
                        <tbody>
                            {props.map((p, i) => {
                                const ref = listRefOf(p.schema);
                                return (
                                    <tr key={p.name} className={i % 2 ? "bg-white" : "bg-gray-50"}>
                                        <td className={`${tdClass} break-all font-mono text-[13px]`}>
                                            {p.name}
                                            {p.required ? <span className="ml-1 text-red-500">*</span> : null}
                                        </td>
                                        <td className={`${tdClass} text-[13px]`}>
                                            {String(p.schema.type ?? (Array.isArray(p.schema.enum) ? "enum" : "any"))}
                                        </td>
                                        <td className={`${tdClass} font-mono text-[13px]`}>
                                            {ref ? `${ref.ref}${ref.multiple ? " []" : ""}` : "—"}
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                )}
            </div>
        </div>
    );
}
