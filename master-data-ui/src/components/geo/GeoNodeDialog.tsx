"use client";

import { useEffect, useId, useState } from "react";
import { X } from "lucide-react";
import { useTranslations } from "next-intl";

export type GeoNodeDialogMode = "add" | "edit";

export type GeoNodeDialogField = {
  label: string;
  value: string;
  readOnly?: boolean;
};

type GeoNodeDialogProps = {
  open: boolean;
  mode: GeoNodeDialogMode;
  title: string;
  contextFields: GeoNodeDialogField[];
  nameLabel: string;
  codeLabel: string;
  initialName?: string;
  initialCode?: string;
  onClose: () => void;
  onSubmit: (values: { name: string; code: string }) => void;
};

export default function GeoNodeDialog({
  open,
  mode,
  title,
  contextFields,
  nameLabel,
  codeLabel,
  initialName = "",
  initialCode = "",
  onClose,
  onSubmit,
}: GeoNodeDialogProps) {
  const t = useTranslations();
  const titleId = useId();
  const [name, setName] = useState(initialName);
  const [code, setCode] = useState(initialCode);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setName(initialName);
    setCode(initialCode);
    setNotice(null);
  }, [open, initialName, initialCode]);

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
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/55 p-4"
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

        <form
          className="space-y-4 px-5 py-5"
          onSubmit={(event) => {
            event.preventDefault();
            const trimmedName = name.trim();
            const trimmedCode = code.trim();
            if (!trimmedName || !trimmedCode) {
              setNotice(t("geo_form_required"));
              return;
            }
            onSubmit({ name: trimmedName, code: trimmedCode });
            setNotice(t("geo_write_unavailable"));
          }}
        >
          {contextFields.map((field) => (
            <label key={field.label} className="block space-y-1.5">
              <span className="text-[12px] font-medium uppercase tracking-wide text-white/55">
                {field.label}
              </span>
              <input
                type="text"
                value={field.value}
                readOnly={field.readOnly !== false}
                className="h-10 w-full rounded border border-[#5A5A5A] bg-[#1A1A1A] px-3 text-[14px] text-white/80 outline-none"
              />
            </label>
          ))}

          <label className="block space-y-1.5">
            <span className="text-[12px] font-medium uppercase tracking-wide text-white/55">
              {nameLabel}
            </span>
            <input
              type="text"
              value={name}
              onChange={(event) => setName(event.target.value)}
              autoFocus
              className="h-10 w-full rounded border border-[#5A5A5A] bg-black px-3 text-[14px] text-white outline-none focus:border-[#F4BB1B]"
            />
          </label>

          <label className="block space-y-1.5">
            <span className="text-[12px] font-medium uppercase tracking-wide text-white/55">
              {codeLabel}
            </span>
            <input
              type="text"
              value={code}
              onChange={(event) => setCode(event.target.value)}
              className="h-10 w-full rounded border border-[#5A5A5A] bg-black px-3 text-[14px] text-white outline-none focus:border-[#F4BB1B]"
            />
          </label>

          {notice ? (
            <p className="rounded border border-[#F4BB1B]/35 bg-[#F4BB1B]/10 px-3 py-2 text-[13px] text-[#F4BB1B]">
              {notice}
            </p>
          ) : null}

          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="h-9 cursor-pointer rounded-[10px] border border-[#5A5A5A] px-4 text-[14px] font-medium text-white hover:bg-white/5"
            >
              {t("cancel")}
            </button>
            <button
              type="submit"
              className="h-9 cursor-pointer rounded-[10px] bg-[#F4BB1B] px-4 text-[14px] font-semibold text-black"
            >
              {mode === "add" ? t("add") : t("save")}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
