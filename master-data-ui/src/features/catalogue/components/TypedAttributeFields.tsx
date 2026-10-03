"use client";

import { useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useCatalogueQuery } from "../api";
import { listRefOf, schemaProperties, type SchemaProperty } from "../schema";
import type { GetListValuesResponse, JsonSchema } from "../types";
import { Field, inputClass, localizedLabel, textareaClass } from "./ui";

type Attrs = Record<string, unknown>;

const PAGE = { current_page: 1, page_size: 1000 };

/**
 * Dropdown of the referenced list's active values in its published version in effect. A draft of
 * the referenced list never counts (the backend accepts only published values), so a list with
 * nothing in effect falls back to typing codes, which the backend then checks.
 */
function ListRefSelect({
    listCode,
    multiple,
    value,
    disabled,
    onChange,
}: {
    listCode: string;
    multiple: boolean;
    value: unknown;
    disabled?: boolean;
    onChange: (next: unknown) => void;
}) {
    const t = useTranslations();
    const locale = useLocale();
    const latest = useCatalogueQuery<GetListValuesResponse>("get_list_values", { list_code: listCode, version: "latest" }, PAGE);
    const values = latest.data?.values ?? [];
    const loading = latest.loading;
    const failed = latest.error;

    if (failed) {
        // Referenced list not readable: let the user type codes; the backend validates them.
        return (
            <input
                type="text"
                disabled={disabled}
                value={Array.isArray(value) ? value.join(", ") : value == null ? "" : String(value)}
                onChange={(e) => {
                    const raw = e.target.value;
                    onChange(
                        multiple
                            ? raw.split(",").map((s) => s.trim()).filter(Boolean)
                            : raw.trim() || undefined,
                    );
                }}
                placeholder={t("cat_ref_codes_placeholder", { list: listCode })}
                className={inputClass}
            />
        );
    }

    const options = values.map((v) => (
        <option key={v.value_id} value={v.value_code}>
            {localizedLabel(v.display, v.display_i18n, locale) || v.value_code} ({v.value_code})
        </option>
    ));

    if (multiple) {
        const selected = Array.isArray(value) ? value.map(String) : [];
        return (
            <select
                multiple
                disabled={disabled || loading}
                value={selected}
                onChange={(e) => {
                    const next = Array.from(e.target.selectedOptions).map((o) => o.value);
                    onChange(next.length ? next : undefined);
                }}
                className={`${textareaClass} min-h-28`}
            >
                {options}
            </select>
        );
    }

    return (
        <select
            disabled={disabled || loading}
            value={value == null ? "" : String(value)}
            onChange={(e) => onChange(e.target.value || undefined)}
            className={inputClass}
        >
            <option value="">{loading ? t("loading") : t("cat_select_value")}</option>
            {/* Keep a stored code visible even if it is no longer active in the referenced list. */}
            {value != null && value !== "" && !values.some((v) => v.value_code === value) && !loading ? (
                <option value={String(value)}>{String(value)}</option>
            ) : null}
            {options}
        </select>
    );
}

/** Free JSON for object / complex properties; applies the value when it parses. */
function JsonField({ value, disabled, onChange }: { value: unknown; disabled?: boolean; onChange: (next: unknown) => void }) {
    const t = useTranslations();
    const [text, setText] = useState(() => (value === undefined ? "" : JSON.stringify(value, null, 2)));
    const [error, setError] = useState<string | null>(null);
    return (
        <>
            <textarea
                rows={3}
                disabled={disabled}
                value={text}
                spellCheck={false}
                onChange={(e) => {
                    const raw = e.target.value;
                    setText(raw);
                    if (!raw.trim()) {
                        setError(null);
                        onChange(undefined);
                        return;
                    }
                    try {
                        onChange(JSON.parse(raw));
                        setError(null);
                    } catch {
                        setError(t("cat_invalid_json"));
                    }
                }}
                className={`${textareaClass} font-mono text-[13px]`}
            />
            {error ? <span className="block text-[12px] text-red-500">{error}</span> : null}
        </>
    );
}

function PropertyInput({
    prop,
    value,
    disabled,
    onChange,
}: {
    prop: SchemaProperty;
    value: unknown;
    disabled?: boolean;
    onChange: (next: unknown) => void;
}) {
    const t = useTranslations();
    const s = prop.schema;
    const ref = listRefOf(s);
    if (ref) {
        return <ListRefSelect listCode={ref.ref} multiple={ref.multiple} value={value} disabled={disabled} onChange={onChange} />;
    }
    const type = Array.isArray(s.type) ? s.type.find((x) => x !== "null") : s.type;
    if (Array.isArray(s.enum)) {
        return (
            <select
                disabled={disabled}
                value={value == null ? "" : JSON.stringify(value)}
                onChange={(e) => onChange(e.target.value ? JSON.parse(e.target.value) : undefined)}
                className={inputClass}
            >
                <option value="">{t("cat_select_value")}</option>
                {s.enum.map((opt) => (
                    <option key={JSON.stringify(opt)} value={JSON.stringify(opt)}>
                        {String(opt)}
                    </option>
                ))}
            </select>
        );
    }
    if (type === "boolean") {
        return (
            <select
                disabled={disabled}
                value={value === true ? "true" : value === false ? "false" : ""}
                onChange={(e) => onChange(e.target.value === "" ? undefined : e.target.value === "true")}
                className={inputClass}
            >
                <option value="">—</option>
                <option value="true">{t("yes")}</option>
                <option value="false">{t("no")}</option>
            </select>
        );
    }
    if (type === "number" || type === "integer") {
        return (
            <input
                type="number"
                disabled={disabled}
                step={type === "integer" ? 1 : "any"}
                min={typeof s.minimum === "number" ? s.minimum : undefined}
                max={typeof s.maximum === "number" ? s.maximum : undefined}
                value={typeof value === "number" ? String(value) : ""}
                onChange={(e) => {
                    const raw = e.target.value;
                    if (raw === "") return onChange(undefined);
                    const n = type === "integer" ? parseInt(raw, 10) : parseFloat(raw);
                    onChange(Number.isNaN(n) ? undefined : n);
                }}
                className={inputClass}
            />
        );
    }
    if (type === "string" || type === undefined) {
        if (type === undefined && value !== undefined && typeof value !== "string") {
            return <JsonField value={value} disabled={disabled} onChange={onChange} />;
        }
        return (
            <input
                type={s.format === "date" ? "date" : "text"}
                disabled={disabled}
                value={typeof value === "string" ? value : ""}
                maxLength={typeof s.maxLength === "number" ? s.maxLength : undefined}
                onChange={(e) => onChange(e.target.value === "" ? undefined : e.target.value)}
                className={inputClass}
            />
        );
    }
    return <JsonField value={value} disabled={disabled} onChange={onChange} />;
}

/**
 * Inputs for a value's typed `attributes`, driven by the list's attribute schema: list references
 * (`x-list-ref`) as dropdowns of the referenced list's values, enums as selects, numbers, booleans,
 * text, and JSON for anything else. Without a schema, attributes are edited as raw JSON.
 * Keys not described by the schema are kept as they are.
 */
export default function TypedAttributeFields({
    schema,
    value,
    onChange,
    disabled,
}: {
    schema: JsonSchema | null | undefined;
    value: Attrs;
    onChange: (next: Attrs) => void;
    disabled?: boolean;
}) {
    const t = useTranslations();
    const props = schemaProperties(schema);

    if (props.length === 0) {
        return (
            <Field label={t("cat_attributes")} hint={t("cat_attributes_json_hint")} group>
                <JsonField
                    value={Object.keys(value).length ? value : undefined}
                    disabled={disabled}
                    onChange={(next) =>
                        onChange(next && typeof next === "object" && !Array.isArray(next) ? (next as Attrs) : {})
                    }
                />
            </Field>
        );
    }

    return (
        <div className="space-y-4">
            {props.map((p) => (
                <Field
                    key={p.name}
                    group={Boolean(listRefOf(p.schema)?.multiple)}
                    label={typeof p.schema.title === "string" ? p.schema.title : p.name}
                    required={p.required}
                    hint={typeof p.schema.description === "string" ? p.schema.description : undefined}
                >
                    <PropertyInput
                        prop={p}
                        value={value[p.name]}
                        disabled={disabled}
                        onChange={(next) => {
                            const copy = { ...value };
                            if (next === undefined) delete copy[p.name];
                            else copy[p.name] = next;
                            onChange(copy);
                        }}
                    />
                </Field>
            ))}
        </div>
    );
}
