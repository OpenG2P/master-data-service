"use client";

import { useEffect, useId } from "react";
import { X } from "lucide-react";
import { useTranslations } from "next-intl";
import Button from "@/components/Button";

type ConfirmDialogProps = {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  confirming?: boolean;
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
  confirming = false,
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
      className="fixed inset-0 z-70 flex items-center justify-center bg-black/50 p-4"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="relative w-full max-w-150 bg-white rounded-[10px] shadow-lg flex flex-col items-center p-8 border-4 border-[#dc3545]"
      >
        <button
          type="button"
          onClick={onClose}
          className="absolute top-4 right-4 text-gray-400 hover:text-gray-600 transition-colors cursor-pointer"
          aria-label={t("close")}
        >
          <X size={30} />
        </button>

        <div className="mb-6 mt-4">
          <div className="w-20 h-20 bg-gray-100 rounded-full flex items-center justify-center">
            <div className="w-14 h-14 bg-[#dc3545] rounded-full flex items-center justify-center">
              <span className="text-white text-[32px] font-bold">!</span>
            </div>
          </div>
        </div>

        <h2 id={titleId} className="text-[22px] font-bold text-black mb-2 text-center">{title}</h2>
        <p className="text-black/70 text-[18px] text-center mb-8 px-4">
          {message}
        </p>

        <div className="flex gap-4 w-full justify-center">
          <Button
            variant="primary"
            onClick={onClose}
            disabled={confirming}
          >
            {cancelLabel ?? t("cancel")}
          </Button>
          <Button
            variant="danger"
            onClick={onConfirm}
            disabled={confirming}
          >
            {confirming && (
              <svg
                className="animate-spin h-4 w-4 mr-2"
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
              >
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                ></circle>
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                ></path>
              </svg>
            )}
            {confirming ? t("deleting") : (confirmLabel ?? t("delete"))}
          </Button>
        </div>
      </div>
    </div>
  );
}
