"use client";

import { useEffect, useId, useState } from "react";
import { X } from "lucide-react";
import { useTranslations } from "next-intl";
import { useFetch } from "@/shared/hooks/useFetch";
import Button from "@/components/Button";
import { toast } from "react-toastify";
import { getErrorMessage } from "@/shared/utils/errorHandler";
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
    const [saving, setSaving] = useState(false);

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
        setSaving(true);

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

        setSaving(false);

        if (result?.attribute_id) {
            onSuccess?.();
            onClose();
        } else {
            const rawError = (result as any)?.error || (result as any)?.statusText;
            const errorCode = (result as any)?.code;
            const errorMessage = getErrorMessage(rawError, errorCode, t);
            toast.error(errorMessage);
        }
    };

    if (!open) return null;

    return (
        <div
            className="fixed inset-0 z-60 flex items-center justify-center bg-black/50 p-4"
            role="presentation"
            onMouseDown={(e) => {
                if (e.target === e.currentTarget) onClose();
            }}
        >
            <div
                role="dialog"
                aria-modal="true"
                aria-labelledby={titleId}
                className="relative w-full bg-white rounded-[10px] shadow-lg max-h-[80vh] p-8 border-4 border-[#EABB13]"
                style={{ maxWidth: "600px" }}
                onClick={(e) => e.stopPropagation()}
            >
                <div className="flex items-center justify-between mb-6">
                    <h2 id={titleId} className="text-[22px] font-bold text-[#ED7C22]">
                        {mode === "edit" ? t("edit_reference_data") : t("add_new_attribute")}
                    </h2>
                    <button
                        type="button"
                        onClick={onClose}
                        className="text-gray-500 hover:text-gray-800 transition-colors cursor-pointer"
                        aria-label={t("close")}
                    >
                        <X size={30} />
                    </button>
                </div>

                <div className="modal-scroll overflow-y-auto max-h-[calc(80vh-120px)] pr-2 space-y-5">
                    <div className="flex flex-col gap-2">
                        <label className="text-[16px] font-medium text-black">
                            {t("attribute_code")}
                            <span className="text-red-500 ml-1">*</span>
                        </label>
                        <input
                            type="text"
                            value={code}
                            onChange={(e) => setCode(e.target.value)}
                            className="w-full rounded-[10px] border border-gray-300 bg-white py-2 px-4 text-[16px] text-black placeholder:text-gray-400 outline-none focus:border-(--color-yellow)"
                            placeholder={t("attr_code_placeholder")}
                        />
                        {error && <p className="text-[14px] text-red-500">{error}</p>}
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
                                        ? "border-(--color-yellow) bg-(--color-yellow)"
                                        : "border-gray-300 bg-white"
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
                        <span className="text-[16px] font-medium text-black">
                            {t("is_hierarchical")}
                        </span>
                    </label>

                    <div className="flex gap-4 w-full justify-end pt-4">
                        <Button variant="secondary" onClick={onClose} disabled={saving}>
                            {t("cancel")}
                        </Button>
                        <Button variant="primary" onClick={handleSubmit} loading={saving}>
                            {saving ? t("saving") : t("save")}
                        </Button>
                    </div>
                </div>
            </div>
        </div>
    );
}
