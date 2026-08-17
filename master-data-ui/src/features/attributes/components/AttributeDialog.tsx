"use client";

import { useEffect, useId, useState } from "react";
import { X } from "lucide-react";
import { useTranslations } from "next-intl";
import { useFetch } from "@/shared/hooks/useFetch";
import type { Attribute } from "../types";

type AttributeDialogProps = {
    open: boolean;
    mode: "add" | "edit";
    attribute?: Attribute;
    onClose: () => void;
    onSuccess?: () => void;
};

export default function AttributeDialog({
    open,
    mode,
    attribute,
    onClose,
    onSuccess,
}: AttributeDialogProps) {
    const t = useTranslations();
    const titleId = useId();
    const { execute: writeAttribute } = useFetch<Attribute>();

    const [code, setCode] = useState("");
    const [isHierarchical, setIsHierarchical] = useState(false);
    const [error, setError] = useState("");

    useEffect(() => {
        if (!open) return;
        setCode(attribute?.attribute_code ?? "");
        setIsHierarchical(attribute?.is_hierarchical ?? false);
        setError("");
    }, [open, attribute]);

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
            setError(t("attr_code_required"));
            return;
        }
        setError("");

        const url =
            mode === "add"
                ? "/api/attributes/add-attribute"
                : "/api/attributes/update-attribute";

        const body =
            mode === "add"
                ? { attribute_code: code.trim(), attribute_display: code.trim(), is_hierarchical: isHierarchical }
                : {
                      attribute_id: attribute!.attribute_id,
                      attribute_code: code.trim(),
                      attribute_display: code.trim(),
                      is_hierarchical: isHierarchical,
                  };

        const result = await writeAttribute(url, {
            method: "POST",
            body: JSON.stringify(body),
        });

        if (result?.attribute_id) {
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
                        {mode === "edit" ? t("edit_reference_data") : t("add_new_attribute")}
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
                            {t("attribute_code")}
                            <span className="text-red-400 ml-1">*</span>
                        </label>
                        <input
                            type="text"
                            value={code}
                            onChange={(e) => setCode(e.target.value)}
                            className="w-full rounded-[10px] border border-[#5A5A5A] bg-white/5 py-2 px-4 text-[16px] text-white placeholder:text-white/30 outline-none focus:border-[#F4BB1B]"
                            placeholder={t("attr_code_placeholder")}
                        />
                        {error && <p className="text-[14px] text-red-400">{error}</p>}
                    </div>

                    <label className="flex cursor-pointer items-center gap-3">
                        <div className="relative">
                            <input
                                type="checkbox"
                                checked={isHierarchical}
                                onChange={(e) => setIsHierarchical(e.target.checked)}
                                className="sr-only"
                            />
                            <div
                                className={`flex h-5 w-5 items-center justify-center rounded border ${
                                    isHierarchical
                                        ? "border-[#F4BB1B] bg-[#F4BB1B]"
                                        : "border-[#5A5A5A] bg-white/5"
                                }`}
                            >
                                {isHierarchical && (
                                    <svg viewBox="0 0 12 12" className="h-3 w-3" fill="none">
                                        <path
                                            d="M2 6l3 3 5-5"
                                            stroke="black"
                                            strokeWidth="1.8"
                                            strokeLinecap="round"
                                            strokeLinejoin="round"
                                        />
                                    </svg>
                                )}
                            </div>
                        </div>
                        <span className="text-[16px] font-medium text-white/70">
                            {t("is_hierarchical")}
                        </span>
                    </label>

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
