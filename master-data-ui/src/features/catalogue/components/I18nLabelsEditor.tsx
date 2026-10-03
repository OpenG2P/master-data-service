"use client";

import { useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { inputClass } from "./ui";

type Row = { locale: string; label: string };

function toRows(value: Record<string, string> | null | undefined): Row[] {
    return Object.entries(value ?? {}).map(([locale, label]) => ({ locale, label }));
}

function toObject(rows: Row[]): Record<string, string> {
    const out: Record<string, string> = {};
    for (const r of rows) {
        const locale = r.locale.trim();
        if (locale && r.label.trim()) out[locale] = r.label.trim();
    }
    return out;
}

/**
 * Edits `{locale: label}` (display_i18n / name_i18n). Initialised from `value`; remount with a
 * new `key` to reset. Emits the cleaned object (empty rows dropped).
 */
export default function I18nLabelsEditor({
    value,
    onChange,
    disabled,
}: {
    value: Record<string, string> | null | undefined;
    onChange: (next: Record<string, string>) => void;
    disabled?: boolean;
}) {
    const t = useTranslations();
    const [rows, setRows] = useState<Row[]>(() => toRows(value));

    const update = (next: Row[]) => {
        setRows(next);
        onChange(toObject(next));
    };

    return (
        <div className="space-y-2">
            {rows.length === 0 ? (
                <p className="text-[13px] text-gray-500">{t("cat_i18n_none")}</p>
            ) : null}
            {rows.map((row, idx) => (
                <div key={idx} className="flex items-center gap-2">
                    <input
                        type="text"
                        value={row.locale}
                        disabled={disabled}
                        onChange={(e) =>
                            update(rows.map((r, i) => (i === idx ? { ...r, locale: e.target.value } : r)))
                        }
                        placeholder={t("cat_i18n_locale_placeholder")}
                        aria-label={t("cat_i18n_locale")}
                        className={`${inputClass} max-w-24`}
                    />
                    <input
                        type="text"
                        value={row.label}
                        disabled={disabled}
                        onChange={(e) =>
                            update(rows.map((r, i) => (i === idx ? { ...r, label: e.target.value } : r)))
                        }
                        placeholder={t("cat_i18n_label_placeholder")}
                        aria-label={t("cat_i18n_label")}
                        className={inputClass}
                    />
                    {!disabled ? (
                        <button
                            type="button"
                            onClick={() => update(rows.filter((_, i) => i !== idx))}
                            className="cursor-pointer rounded p-2 text-gray-500 hover:bg-gray-100 hover:text-red-600"
                            aria-label={t("delete")}
                            title={t("delete")}
                        >
                            <Trash2 size={16} />
                        </button>
                    ) : null}
                </div>
            ))}
            {!disabled ? (
                <button
                    type="button"
                    onClick={() => setRows([...rows, { locale: "", label: "" }])}
                    className="inline-flex cursor-pointer items-center gap-1 text-[14px] font-medium text-gray-700 hover:text-black hover:underline"
                >
                    <Plus size={14} /> {t("cat_i18n_add")}
                </button>
            ) : null}
        </div>
    );
}
