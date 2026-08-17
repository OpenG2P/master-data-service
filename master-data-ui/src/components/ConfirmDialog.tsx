"use client";

import { useEffect, useId } from "react";
import { X } from "lucide-react";
import { useTranslations } from "next-intl";

type ConfirmDialogProps = {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  onConfirm: () => void;
  onClose: () => void;
};

export default function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel,
  cancelLabel,
  danger = false,
  onConfirm,
  onClose,
}: ConfirmDialogProps) {
  const t = useTranslations();
  const titleId = useId();

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[70] flex items-center justify-center bg-black/55 p-4"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="w-full max-w-md rounded-[10px] border border-[#5A5A5A] bg-black text-white shadow-2xl"
      >
        <div className="flex items-center justify-between border-b border-[#5A5A5A] px-5 py-4">
          <h2 id={titleId} className="text-[16px] font-semibold text-[#F4BB1B]">
            {title}
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
          <p className="text-[14px] leading-relaxed text-white/80">{message}</p>

          <div className="flex justify-end gap-3">
            <button
              type="button"
              onClick={onClose}
              className="h-9 cursor-pointer rounded-[10px] border border-[#5A5A5A] px-4 text-[14px] font-medium text-white hover:bg-white/5"
            >
              {cancelLabel ?? t("cancel")}
            </button>
            <button
              type="button"
              onClick={onConfirm}
              className={`h-9 cursor-pointer rounded-[10px] px-4 text-[14px] font-semibold ${
                danger
                  ? "bg-red-500 text-white hover:bg-red-400"
                  : "bg-[#F4BB1B] text-black"
              }`}
            >
              {confirmLabel ?? t("delete")}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
