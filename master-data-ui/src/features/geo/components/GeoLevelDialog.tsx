"use client";

import { useEffect, useId, useState } from "react";
import { X } from "lucide-react";
import { useTranslations } from "next-intl";
import { useFetch } from "@/shared/hooks/useFetch";
import { toast } from "react-toastify";
import { getErrorMessage } from "@/shared/utils/errorHandler";
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
    if (!(code.trim() || name.trim())) return;

    const result =
      mode === "add"
        ? await writeLevel("/api/geo/add-geo-level", {
            method: "POST",
            body: JSON.stringify({
              level_mnemonic: (code.trim() || name.trim()),
              parent_level_id: parentLevelId ?? "",
            }),
          })
        : await writeLevel("/api/geo/update-geo-level", {
            method: "POST",
            body: JSON.stringify({
              level_id: levelId,
              level_mnemonic: (code.trim() || name.trim()),
            }),
          });

    if (result?.level_id) {
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
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
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
            {mode === "edit" ? t("geo_edit_level") : t("geo_add_level")}
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
          className="modal-scroll overflow-y-auto max-h-[calc(80vh-120px)] pr-2 space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            void handleSubmit();
          }}
        >
          <label className="block space-y-1.5">
            <span className="text-[12px] font-medium uppercase tracking-wide text-gray-500">
              {t("geo_parent_level")}
            </span>
            <input
              type="text"
              value={parentLevelLabel ?? t("geo_parent_level_none")}
              readOnly
              className="h-10 w-full rounded border border-gray-300 bg-gray-50 px-3 text-[14px] text-gray-700 outline-none"
            />
          </label>

          <label className="block space-y-1.5">
            <span className="text-[12px] font-medium uppercase tracking-wide text-gray-500">
              {t("geo_level_name")}
            </span>
            <input
              type="text"
              value={name}
              onChange={(event) => setName(event.target.value)}
              autoFocus
              placeholder={t("geo_level_name_placeholder")}
              className="h-10 w-full rounded border border-gray-300 bg-white px-3 text-[14px] text-black outline-none placeholder:text-gray-400 focus:border-(--color-yellow)"
            />
          </label>

          <label className="block space-y-1.5">
            <span className="text-[12px] font-medium uppercase tracking-wide text-gray-500">
              {t("geo_level_code")}
            </span>
            <input
              type="text"
              value={code}
              onChange={(event) => setCode(event.target.value)}
              placeholder={t("geo_level_code_placeholder")}
              className="h-10 w-full rounded border border-gray-300 bg-white px-3 text-[14px] text-black outline-none placeholder:text-gray-400 focus:border-(--color-yellow)"
            />
          </label>

          <div className="flex gap-4 w-full justify-center pt-4">
            <button
              type="button"
              onClick={onClose}
              className="px-8 py-2 bg-black text-white font-semibold rounded-[10px] hover:bg-black/80 transition-colors text-[16px] cursor-pointer"
            >
              {t("cancel")}
            </button>
            <button
              type="submit"
              className="px-8 py-2 bg-(--color-yellow) text-black font-semibold rounded-[10px] hover:bg-(--color-accent-hover) transition-colors text-[16px] cursor-pointer"
            >
              {mode === "edit" ? t("save") : t("add")}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
