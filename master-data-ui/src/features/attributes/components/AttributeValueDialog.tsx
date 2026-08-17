"use client";

import { useEffect, useId, useState } from "react";
import { X } from "lucide-react";
import { useTranslations } from "next-intl";
import { useFetch } from "@/shared/hooks/useFetch";
import type { AttributeValue } from "../types";

type AttributeValueDialogProps = {
    open: boolean;
    mode: "add" | "edit";
    attributeId: string;
    parentValueId?: string | null;
    value?: AttributeValue;
    onClose: () => void;
    onSuccess?: () => void;
};

export default function AttributeValueDialog({
    open,
    mode,
    attributeId,
    parentValueId,
    value,
    onClose,
    onSuccess,
}: AttributeValueDialogProps) {
    const t = useTranslations();
    const titleId = useId();
    const { execute: writeValue } = useFetch<AttributeValue>();

    const [code, setCode] = useState("");
    const [sortOrder, setSortOrder] = useState("0");
    const [error, setError] = useState("");

    useEffect(() => {
        if (!open) return;
        setCode(value?.value_code ?? "");
        setSortOrder(String(value?.sort_order ?? 0));
        setError("");
    }, [open, value]);

    useEffect(() => {
        if (!open) return;
        const onKeyDown = (e: KeyboardEvent) => {
            if (e.key === "Escape") onClose();
        };
        window.addEventListener("keydown", onKeyDown);
        return () => window.removeEventListener("keydown", onKeyDown);
    }, [open, onClose]);

    const handleSubmit = async () => {
        if (!code.trim()) {
            setError(t("value_code_required"));
            return;
        }
        setError("");

        const url =
            mode === "add"
                ? "/api/attributes/add-attribute-value"
                : "/api/attributes/update-attribute-value";

        const body =
            mode === "add"
                ? {
                      attribute_id: attributeId,
                      value_code: code.trim(),
                      value_display: code.trim(),
                      parent_value_id: parentValueId ?? null,
                      sort_order: Number(sortOrder) || 0,
                  }
                : {
                      value_id: value!.value_id,
                      attribute_id: value!.attribute_id,
                      value_code: code.trim(),
                      value_display: code.trim(),
                      parent_value_id: value!.parent_value_id ?? null,
                      sort_order: Number(sortOrder) || 0,
                  };

        const result = await writeValue(url, {
            method: "POST",
            body: JSON.stringify(body),
        });

        if (result?.value_id) {
            onSuccess?.();
            onClose();
        }
    };

    if (!open) return null;

    return (
        <div
            className="fixed inset-0 z-[60] flex items-center justify-center bg-black/55 p-4"
            role="presentation"
            onMouseDown={(e) => {
                if (e.target === e.currentTarget) onClose();
            }}
        >
            <div
                role="dialog"
                aria-modal="true"
                aria-labelledby={titleId}
                className="w-full max-w-md rounded-[10px] border border-[#5A5A5A] bg-black text-white shadow-2xl"
            >
                <div className="flex items-center justify-between border-b border-[#5A5A5A] px-5 py-4">
                    <h2 id={titleId} className="text-[24px] font-medium text-[#F4BB1B]">
                        {mode === "edit" ? t("edit_reference_data_value") : t("add_attribute_value")}
                    </h2>
                    <button
                        type="button"
                        onClick={onClose}
                        className="flex h-8 w-8 cursor-pointer items-center justify-center rounded text-white/70 hover:bg-white/10 hover:text-white"
                        aria-label={t("close")}
                    >
                        <X size={16} />
                    </button>
                </div>

                <div className="space-y-5 px-5 py-5">
                    <div className="flex flex-col gap-2">
                        <label className="text-[16px] font-medium text-white/70">
                            {t("value_code")}
                            <span className="text-red-400 ml-1">*</span>
                        </label>
                        <input
                            type="text"
                            value={code}
                            onChange={(e) => setCode(e.target.value)}
                            className="w-full rounded-[10px] border border-[#5A5A5A] bg-white/5 py-2 px-4 text-[16px] text-white placeholder:text-white/30 outline-none focus:border-[#F4BB1B]"
                            placeholder={t("value_code_placeholder")}
                        />
                        {error && <p className="text-[14px] text-red-400">{error}</p>}
                    </div>

                    <div className="flex flex-col gap-2">
                        <label className="text-[16px] font-medium text-white/70">
                            {t("sort_order")}
                        </label>
                        <input
                            type="number"
                            value={sortOrder}
                            onChange={(e) => setSortOrder(e.target.value)}
                            className="w-full rounded-[10px] border border-[#5A5A5A] bg-white/5 py-2 px-4 text-[16px] text-white placeholder:text-white/30 outline-none focus:border-[#F4BB1B]"
                        />
                    </div>

                    <div className="flex justify-end gap-3 pt-2">
                        <button
                            type="button"
                            onClick={onClose}
                            className="cursor-pointer rounded-[10px] border border-[#5A5A5A] px-6 py-2 text-[16px] font-bold text-white hover:bg-white/5"
                        >
                            {t("cancel")}
                        </button>
                        <button
                            type="button"
                            onClick={handleSubmit}
                            className="cursor-pointer rounded-[10px] bg-[#F4BB1B] px-6 py-2 text-[16px] font-bold text-black"
                        >
                            {t("save")}
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}
