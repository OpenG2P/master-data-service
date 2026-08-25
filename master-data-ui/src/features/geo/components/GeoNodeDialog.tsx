"use client";

import { useEffect, useId, useState } from "react";
import { X } from "lucide-react";
import { useTranslations } from "next-intl";
import { useFetch } from "@/shared/hooks/useFetch";
import type { GeoLevelValue } from "../types";

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
  levelId: string;
  parentLevelValueId?: string | null;
  levelValueId?: string;
  initialName?: string;
  initialCode?: string;
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
  codeLabel,
  levelId,
  parentLevelValueId = null,
  levelValueId,
  initialName = "",
  initialCode = "",
  levelChoices = [],
  onClose,
  onSuccess,
}: GeoNodeDialogProps) {
  const t = useTranslations();
  const titleId = useId();
  const { execute: writeLevelValue } = useFetch<GeoLevelValue>();
  const [name, setName] = useState(initialName);
  const [code, setCode] = useState(initialCode);
  const [selectedLevelId, setSelectedLevelId] = useState(
    levelChoices[0]?.levelId || levelId
  );

  useEffect(() => {
    if (!open) return;
    setName(initialName);
    setCode(initialCode);
    setSelectedLevelId(levelChoices[0]?.levelId || levelId);
  }, [open, initialName, initialCode, levelChoices, levelId]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  const handleSubmit = async () => {
    if (!name.trim() && !code.trim()) return;

    const result =
      mode === "add"
        ? await writeLevelValue("/api/geo/add-geo-level-value", {
            method: "POST",
            body: JSON.stringify({
              level_id: selectedLevelId,
              level_value_mnemonic: name.trim() || code.trim(),
              parent_level_value_id: parentLevelValueId ?? "",
            }),
          })
        : await writeLevelValue("/api/geo/update-geo-level-value", {
            method: "POST",
            body: JSON.stringify({
              level_value_id: levelValueId,
              level_value_mnemonic: name.trim() || code.trim(),
            }),
          });

    if (result?.level_value_id) {
      onSuccess?.();
      onClose();
    }
  };

  if (!open) return null;

  const chosenChoice = levelChoices.find(
    (choice) => choice.levelId === selectedLevelId
  );
  const dialogTitle =
    mode === "add" && chosenChoice
      ? t("geo_add_named", { name: chosenChoice.label })
      : title;
  const dialogNameLabel = chosenChoice
    ? t("geo_name_field", { name: chosenChoice.label })
    : nameLabel;

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
        className="flex max-h-[min(90vh,720px)] w-full max-w-md flex-col overflow-hidden rounded-[10px] border border-[#5A5A5A] bg-black text-white shadow-2xl"
      >
        <div className="flex shrink-0 items-center justify-between border-b border-[#5A5A5A] px-5 py-4">
          <h2 id={titleId} className="text-[16px] font-semibold text-[#F4BB1B]">
            {dialogTitle}
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
          className="flex min-h-0 flex-1 flex-col"
          onSubmit={(event) => {
            event.preventDefault();
            void handleSubmit();
          }}
        >
          <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-5 py-5">
            {levelChoices.length > 1 ? (
              <div className="space-y-1.5">
                <span className="text-[12px] font-medium uppercase tracking-wide text-white/55">
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
                            ? "border-[#F4BB1B] bg-[#F4BB1B] text-black"
                            : "border-[#5A5A5A] bg-black text-white/80 hover:border-[#F4BB1B]/60 hover:text-white"
                        }`}
                      >
                        {choice.label}
                      </button>
                    );
                  })}
                </div>
              </div>
            ) : null}

            {contextFields.length > 0 ? (
              <div className="space-y-1.5">
                <span className="text-[12px] font-medium uppercase tracking-wide text-white/55">
                  {t("geo_hierarchy_path")}
                </span>
                <div className="rounded border border-[#5A5A5A] bg-[#1A1A1A] px-3 py-2.5">
                  <p className="break-words text-[13px] leading-relaxed text-white/80">
                    {contextFields.map((field, index) => (
                      <span key={`${field.label}-${index}`}>
                        {index > 0 ? (
                          <span className="mx-1.5 text-white/35" aria-hidden>
                            /
                          </span>
                        ) : null}
                        <span className="text-white/45">{field.label}:</span>{" "}
                        <span>{field.value}</span>
                      </span>
                    ))}
                  </p>
                </div>
              </div>
            ) : null}

            <label className="block space-y-1.5">
              <span className="text-[12px] font-medium uppercase tracking-wide text-white/55">
                {dialogNameLabel}
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
          </div>

          <div className="flex shrink-0 justify-end gap-3 border-t border-[#5A5A5A] px-5 py-4">
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
