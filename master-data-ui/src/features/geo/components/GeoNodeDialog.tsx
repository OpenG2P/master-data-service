"use client";

import { useEffect, useId, useState } from "react";
import { X } from "lucide-react";
import { useTranslations } from "next-intl";
import { useFetch } from "@/shared/hooks/useFetch";
import Button from "@/components/Button";
import { toast } from "react-toastify";
import { getErrorMessage } from "@/shared/utils/errorHandler";
import type { GeoLevelValue } from "../types";

export type GeoNodeDialogMode = "add" | "edit";

export type GeoNodeDialogField = {
  label: string;
  value: string;
  readOnly?: boolean;
};

interface GeoNodeDialogProps {
  open: boolean;
  mode: GeoNodeDialogMode;
  title?: string;
  contextFields?: GeoNodeDialogField[];
  nameLabel?: string;
  levelId: string;
  parentLevelValueId?: string | null;
  levelValueId?: string;
  initialName?: string;
  levelChoices?: { levelId: string; label: string }[];
  onClose: () => void;
  onSuccess?: () => void;
};

export default function GeoNodeDialog({
  open,
  mode,
  title,
  contextFields,
  nameLabel,
  levelId,
  parentLevelValueId = null,
  levelValueId,
  initialName = "",
  levelChoices = [],
  onClose,
  onSuccess,
}: GeoNodeDialogProps) {
  const t = useTranslations();
  const titleId = useId();
  const { execute: writeLevelValue } = useFetch<GeoLevelValue>();
  const [name, setName] = useState(initialName);
  const [selectedLevelId, setSelectedLevelId] = useState(
    levelChoices[0]?.levelId || levelId
  );
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    setName(initialName);
    setSelectedLevelId(levelChoices[0]?.levelId || levelId);
    setSaving(false);
  }, [open, initialName, levelChoices, levelId]);

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
        ? await writeLevelValue("/api/geo/add-geo-level-value", {
            method: "POST",
            body: JSON.stringify({
              level_id: selectedLevelId,
              level_value_mnemonic: name.trim(),
              parent_level_value_id: parentLevelValueId ?? "",
            }),
          })
        : await writeLevelValue("/api/geo/update-geo-level-value", {
            method: "POST",
            body: JSON.stringify({
              level_value_id: levelValueId,
              level_value_mnemonic: name.trim(),
            }),
          });

    setSaving(false);

    if (result?.level_value_id) {
      toast.success(mode === "add" ? t("geo_value_added_successfully") : t("geo_value_updated_successfully"));
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

  const chosenChoice = levelChoices.find(
    (choice) => choice.levelId === selectedLevelId
  );
  const dialogTitle =
    mode === "add" && chosenChoice
      ? t("geo_add_named", { name: chosenChoice.label })
      : mode === "add"
      ? t("geo_add_level_value")
      : title || t("geo_edit_level_value");
  const dialogNameLabel = chosenChoice
    ? t("geo_name_field", { name: chosenChoice.label })
    : nameLabel;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
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
          <h2 id={titleId} className="text-[22px] font-bold text-[#ED7C22]">{dialogTitle}</h2>
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
            {levelChoices.length >= 1 ? (
              <div className="space-y-1.5">
                <span className="text-[12px] font-semibold uppercase tracking-wide text-black">
                  {t("geo_child_level")}
                </span>
                <div className="flex flex-wrap gap-2">
                  {levelChoices.map((choice) => {
                    const isActive = choice.levelId === selectedLevelId;
                    return (
                      <button
                        key={choice.levelId}
                        type="button"
                        onClick={() => setSelectedLevelId(choice.levelId)}
                        className={`h-9 cursor-pointer rounded-[10px] border px-3 text-[14px] font-medium ${
                          isActive
                            ? "border-(--color-yellow) bg-(--color-yellow) text-black"
                            : "border-gray-300 bg-white text-gray-600 hover:border-(--color-yellow)/60 hover:text-black"
                        }`}
                      >
                        {choice.label}
                      </button>
                    );
                  })}
                </div>
              </div>
            ) : null}

            {contextFields && contextFields.length > 0 ? (
              <div className="space-y-1.5">
                <span className="text-[12px] font-semibold uppercase tracking-wide text-black">
                  {t("geo_hierarchy_path")}
                </span>
                <div className="rounded border border-gray-200 bg-gray-50 px-3 py-2.5">
                  <p className="wrap-break-word text-[13px] leading-relaxed text-gray-700">
                    {contextFields.map((field, index) => (
                      <span key={`${field.label}-${index}`}>
                        {index > 0 ? (
                          <span className="mx-1.5 text-gray-400" aria-hidden>
                            /
                          </span>
                        ) : null}
                        <span className="text-gray-500">{field.label}:</span>{" "}
                        <span>{field.value}</span>
                      </span>
                    ))}
                  </p>
                </div>
              </div>
            ) : null}

            <label className="block space-y-1.5">
              <span className="text-[12px] font-semibold uppercase tracking-wide text-black">
                {dialogNameLabel}
              </span>
              <input
                type="text"
                value={name}
                onChange={(event) => setName(event.target.value)}
                autoFocus
                placeholder={t("geo_level_value_mnemonic_placeholder")}
                className="h-10 w-full rounded border border-gray-300 bg-white px-3 text-[14px] text-black outline-none focus:border-(--color-yellow)"
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
