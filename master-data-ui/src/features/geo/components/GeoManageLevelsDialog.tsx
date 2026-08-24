"use client";

import { useEffect, useId, useMemo, useState } from "react";
import { X } from "lucide-react";
import { useTranslations } from "next-intl";
import ConfirmDialog from "@/components/ConfirmDialog";
import { useFetch } from "@/shared/hooks/useFetch";
import GeoLevelDialog from "./GeoLevelDialog";
import type { GeoLevel } from "../types";
import {
  getChildLevel,
  getLevelById,
  getLevelLabel,
} from "../utils";

type GeoManageLevelsDialogProps = {
  open: boolean;
  levels: GeoLevel[];
  onClose: () => void;
  onChanged?: () => void | Promise<void>;
};

export default function GeoManageLevelsDialog({
  open,
  levels,
  onClose,
  onChanged,
}: GeoManageLevelsDialogProps) {
  const t = useTranslations();
  const titleId = useId();
  const { execute: deleteLevel } = useFetch<{ level_id: string }>();
  const [levelForm, setLevelForm] = useState<
    | { open: false }
    | {
        open: true;
        mode: "add" | "edit";
        levelId?: string;
        parentLevelId?: string | null;
        parentLevelLabel: string | null;
        initialName?: string;
        initialCode?: string;
      }
  >({ open: false });
  const [deleteTarget, setDeleteTarget] = useState<GeoLevel | null>(null);

  useEffect(() => {
    if (!open) {
      setLevelForm({ open: false });
      setDeleteTarget(null);
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !levelForm.open && !deleteTarget) {
        onClose();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [deleteTarget, levelForm.open, onClose, open]);

  const deepestLevel = levels[levels.length - 1];
  const canAddLevel =
    levels.length === 0 ||
    (deepestLevel != null && !getChildLevel(levels, deepestLevel.level_id));

  const rows = useMemo(
    () =>
      levels.map((level) => {
        const parent = level.parent_level_id
          ? getLevelById(levels, level.parent_level_id)
          : undefined;
        return {
          level,
          parentLabel: parent ? getLevelLabel(parent) : null,
        };
      }),
    [levels]
  );

  const proceedDelete = async (level: GeoLevel) => {
    const result = await deleteLevel("/api/geo/delete-geo-level", {
      method: "POST",
      body: JSON.stringify({ level_id: level.level_id }),
    });

    if (result?.level_id) {
      setDeleteTarget(null);
      await onChanged?.();
    }
  };

  if (!open) return null;

  return (
    <>
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
          className="flex max-h-[min(80vh,640px)] w-full max-w-lg flex-col overflow-hidden rounded-[10px] border border-[#5A5A5A] bg-black text-white shadow-2xl"
        >
          <div className="flex shrink-0 items-center justify-between border-b border-[#5A5A5A] px-5 py-4">
            <h2
              id={titleId}
              className="font-normal text-[16px] leading-none tracking-normal text-[#F4BB1B]"
            >
              {t("geo_manage_levels_title")}
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

          <div className="min-h-0 flex-1 overflow-y-auto">
            {rows.length === 0 ? (
              <p className="px-5 py-8 text-center text-[14px] text-white/45">
                {t("geo_no_levels")}
              </p>
            ) : (
              <ul className="divide-y divide-[#5A5A5A]">
                {rows.map(({ level, parentLabel }) => (
                  <li key={level.level_id} className="px-5 py-4">
                    <p className="font-normal text-[16px] leading-none tracking-normal text-white">
                      {getLevelLabel(level)}
                    </p>
                    <p className="mt-2 text-[13px] text-white/55">
                      {t("geo_parent")}: {parentLabel ?? "—"}
                    </p>
                    <div className="mt-3 flex flex-wrap justify-end gap-4 text-[14px]">
                      <button
                        type="button"
                        onClick={() =>
                          setLevelForm({
                            open: true,
                            mode: "edit",
                            levelId: level.level_id,
                            parentLevelId: level.parent_level_id,
                            parentLevelLabel: parentLabel,
                            initialName: level.level_mnemonic || "",
                            initialCode: level.level_mnemonic || "",
                          })
                        }
                        className="cursor-pointer text-white/80 hover:text-[#F4BB1B] hover:underline"
                      >
                        {t("edit")}
                      </button>
                      <button
                        type="button"
                        onClick={() => setDeleteTarget(level)}
                        className="cursor-pointer text-red-300 hover:underline"
                      >
                        {t("delete")}
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="shrink-0 border-t border-[#5A5A5A] px-5 py-4">
            <button
              type="button"
              disabled={!canAddLevel}
              onClick={() =>
                setLevelForm({
                  open: true,
                  mode: "add",
                  parentLevelId: deepestLevel?.level_id ?? null,
                  parentLevelLabel: deepestLevel
                    ? getLevelLabel(deepestLevel)
                    : null,
                })
              }
              className="inline-flex h-9 cursor-pointer items-center gap-2 rounded-[10px] bg-[#F4BB1B] px-4 text-[14px] font-semibold text-black disabled:cursor-not-allowed disabled:bg-white/15 disabled:text-white/40"
            >
              {t("geo_add_level")}
              <span className="flex h-[18px] w-[18px] items-center justify-center rounded-[10px] bg-white text-[14px] font-bold leading-none text-black">
                +
              </span>
            </button>
          </div>
        </div>
      </div>

      <GeoLevelDialog
        open={levelForm.open}
        mode={levelForm.open ? levelForm.mode : "add"}
        levelId={levelForm.open ? levelForm.levelId : undefined}
        parentLevelId={levelForm.open ? levelForm.parentLevelId : null}
        parentLevelLabel={
          levelForm.open ? levelForm.parentLevelLabel : null
        }
        initialName={levelForm.open ? levelForm.initialName : undefined}
        initialCode={levelForm.open ? levelForm.initialCode : undefined}
        onClose={() => setLevelForm({ open: false })}
        onSuccess={() => {
          void onChanged?.();
        }}
      />

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title={t("geo_delete_level")}
        message={t("geo_delete_level_confirm", {
          name: deleteTarget ? getLevelLabel(deleteTarget) : "",
        })}
        confirmLabel={t("delete")}
        danger
        onConfirm={() => {
          if (!deleteTarget) return;
          void proceedDelete(deleteTarget);
        }}
        onClose={() => setDeleteTarget(null)}
      />
    </>
  );
}
