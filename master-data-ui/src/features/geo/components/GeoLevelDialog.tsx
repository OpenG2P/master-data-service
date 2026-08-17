"use client";

import { useEffect, useId, useState } from "react";
import { X } from "lucide-react";
import { useTranslations } from "next-intl";
import { useFetch } from "@/shared/hooks/useFetch";
import type { GeoLevel } from "../types";

type GeoLevelDialogProps = {
  open: boolean;
  mode?: "add" | "edit";
  levelId?: string;
  parentLevelId?: string | null;
  parentLevelLabel: string | null;
  initialName?: string;
  initialCode?: string;
  onClose: () => void;
  onSuccess?: () => void;
};

export default function GeoLevelDialog({
  open,
  mode = "add",
  levelId,
  parentLevelId = null,
  parentLevelLabel,
  initialName = "",
  initialCode = "",
  onClose,
  onSuccess,
}: GeoLevelDialogProps) {
  const t = useTranslations();
  const titleId = useId();
  const { execute: writeLevel } = useFetch<GeoLevel>();
  const [name, setName] = useState("");
  const [code, setCode] = useState("");

  useEffect(() => {
    if (!open) return;
    setName(initialName);
    setCode(initialCode);
  }, [initialCode, initialName, open]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  const handleSubmit = async () => {
    if (!name.trim() || !code.trim()) return;

    const result =
      mode === "add"
        ? await writeLevel("/api/geo/add-geo-level", {
            method: "POST",
            body: JSON.stringify({
              level_mnemonic: code.trim(),
              display_name: name.trim(),
              parent_level_id: parentLevelId ?? "",
            }),
          })
        : await writeLevel("/api/geo/update-geo-level", {
            method: "POST",
            body: JSON.stringify({
              level_id: levelId,
              level_mnemonic: code.trim(),
              display_name: name.trim(),
            }),
          });

    if (result?.level_id) {
      onSuccess?.();
      onClose();
    }
  };

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/55 p-4"
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
            {mode === "edit" ? t("geo_edit_level") : t("geo_add_level")}
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
            void handleSubmit();
          }}
        >
          <label className="block space-y-1.5">
            <span className="text-[12px] font-medium uppercase tracking-wide text-white/55">
              {t("geo_parent_level")}
            </span>
            <input
              type="text"
              value={parentLevelLabel ?? t("geo_parent_level_none")}
              readOnly
              className="h-10 w-full rounded border border-[#5A5A5A] bg-[#1A1A1A] px-3 text-[14px] text-white/80 outline-none"
            />
          </label>

          <label className="block space-y-1.5">
            <span className="text-[12px] font-medium uppercase tracking-wide text-white/55">
              {t("geo_level_name")}
            </span>
            <input
              type="text"
              value={name}
              onChange={(event) => setName(event.target.value)}
              autoFocus
              placeholder={t("geo_level_name_placeholder")}
              className="h-10 w-full rounded border border-[#5A5A5A] bg-black px-3 text-[14px] text-white outline-none placeholder:text-[#8A8A8A] focus:border-[#F4BB1B]"
            />
          </label>

          <label className="block space-y-1.5">
            <span className="text-[12px] font-medium uppercase tracking-wide text-white/55">
              {t("geo_level_code")}
            </span>
            <input
              type="text"
              value={code}
              onChange={(event) => setCode(event.target.value)}
              placeholder={t("geo_level_code_placeholder")}
              className="h-10 w-full rounded border border-[#5A5A5A] bg-black px-3 text-[14px] text-white outline-none placeholder:text-[#8A8A8A] focus:border-[#F4BB1B]"
            />
          </label>

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
              {mode === "edit" ? t("save") : t("add")}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
