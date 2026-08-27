"use client";

import { useEffect, useId, useState } from "react";
import { X } from "lucide-react";
import { useTranslations } from "next-intl";
import { useFetch } from "@/shared/hooks/useFetch";
import Button from "@/components/Button";
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
  onClose,
  onSuccess,
}: GeoLevelDialogProps) {
  const t = useTranslations();
  const titleId = useId();
  const { execute: writeLevel } = useFetch<GeoLevel>();
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    setName(initialName);
    setSaving(false);
  }, [initialName, open]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  const handleSubmit = async () => {
    if (!name.trim()) return;

    setSaving(true);

    const result =
      mode === "add"
        ? await writeLevel("/api/geo/add-geo-level", {
            method: "POST",
            body: JSON.stringify({
              level_mnemonic: name.trim(),
              parent_level_id: parentLevelId ?? "",
            }),
          })
        : await writeLevel("/api/geo/update-geo-level", {
            method: "POST",
            body: JSON.stringify({
              level_id: levelId,
              level_mnemonic: name.trim(),
            }),
          });

    setSaving(false);

    if (result?.level_id) {
      toast.success(mode === "add" ? t("geo_level_added_successfully") : t("geo_level_updated_successfully"));
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
            <span className="text-[12px] font-semibold uppercase tracking-wide text-black">
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
            <span className="text-[12px] font-semibold uppercase tracking-wide text-black">
              {t("geo_level_mnemonic")}
            </span>
            <input
              type="text"
              value={name}
              onChange={(event) => setName(event.target.value)}
              autoFocus
              placeholder={t("geo_level_mnemonic_placeholder")}
              className="h-10 w-full rounded border border-gray-300 bg-white px-3 text-[14px] text-black outline-none placeholder:text-gray-400 focus:border-(--color-yellow)"
            />
          </label>

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
              disabled={saving}
            >
              {saving && (
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
              {saving ? t("saving") : t("save")}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
