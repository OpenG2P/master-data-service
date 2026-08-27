"use client";

import { useEffect, useId, useState } from "react";
import { X } from "lucide-react";
import { useTranslations } from "next-intl";
import { useFetch } from "@/shared/hooks/useFetch";
import Button from "@/components/Button";
import { toast } from "react-toastify";
import { getErrorMessage } from "@/shared/utils/errorHandler";
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
    const [saving, setSaving] = useState(false);

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
        setSaving(true);

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

        setSaving(false);

        if (result?.value_id) {
            toast.success(mode === "add" ? t("attr_value_added_successfully") : t("attr_value_updated_successfully"));
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
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
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
                        {mode === "edit" ? t("edit_reference_data_value") : t("add_attribute_value")}
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

                <form
                    className="modal-scroll overflow-y-auto max-h-[calc(80vh-120px)] pr-2"
                    onSubmit={(event) => {
                        event.preventDefault();
                        void handleSubmit();
                    }}
                >
                    <div className="space-y-4">
                        <label className="block space-y-1.5">
                            <span className="text-[12px] font-semibold uppercase tracking-wide text-black">
                                {t("value_code")}
                                <span className="text-red-500 ml-1">*</span>
                            </span>
                            <input
                                type="text"
                                value={code}
                                onChange={(e) => setCode(e.target.value)}
                                autoFocus
                                className="h-10 w-full rounded border border-gray-300 bg-white px-3 text-[14px] text-black outline-none focus:border-[#EABB13]"
                                placeholder={t("value_code_placeholder")}
                            />
                            {error && <p className="text-[14px] text-red-500">{error}</p>}
                        </label>

                        <label className="block space-y-1.5">
                            <span className="text-[12px] font-semibold uppercase tracking-wide text-black">
                                {t("sort_order")}
                            </span>
                            <input
                                type="number"
                                value={sortOrder}
                                onChange={(e) => setSortOrder(e.target.value)}
                                className="h-10 w-full rounded border border-gray-300 bg-white px-3 text-[14px] text-black outline-none focus:border-[#EABB13]"
                            />
                        </label>
                    </div>

                    <div className="flex gap-4 w-full justify-end pt-4">
                        <Button
                            variant="secondary"
                            onClick={onClose}
                            disabled={saving}
                        >
                            {t("cancel")}
                        </Button>
                        <Button
                            variant="primary"
                            type="submit"
                            loading={saving}
                        >
                            {saving ? t("saving") : t("save")}
                        </Button>
                    </div>
                </form>
            </div>
        </div>
    );
}
