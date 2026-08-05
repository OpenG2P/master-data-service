"use client";

import { useEffect, useId, useMemo, useState } from "react";
import { X } from "lucide-react";
import { useTranslations } from "next-intl";
import ConfirmDialog from "@/components/ConfirmDialog";
import GeoLevelDialog from "@/components/geo/GeoLevelDialog";
import type { GeoLevel } from "@/types/geo";
import {
  getChildLevel,
  getLevelById,
  getLevelLabel,
} from "@/shared/utils/geoHierarchy";

type GeoManageLevelsDialogProps = {
  open: boolean;
  levels: GeoLevel[];
  onClose: () => void;
};

export default function GeoManageLevelsDialog({
  open,
  levels,
  onClose,
}: GeoManageLevelsDialogProps) {
  const t = useTranslations();
  const titleId = useId();
  const [levelForm, setLevelForm] = useState<
    | { open: false }
    | {
        open: true;
        mode: "add" | "edit";
        parentLevelLabel: string | null;
        initialName?: string;
        initialCode?: string;
      }
  >({ open: false });
  const [deleteTarget, setDeleteTarget] = useState<GeoLevel | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (!open) {
      setLevelForm({ open: false });
      setDeleteTarget(null);
      setNotice(null);
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

          {notice ? (
            <div className="shrink-0 border-b border-[#F4BB1B]/35 bg-[#F4BB1B]/10 px-5 py-2 text-[13px] text-[#F4BB1B]">
              {notice}
            </div>
          ) : null}

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
                            parentLevelLabel: parentLabel,
                            initialName:
                              level.display_name || level.level_mnemonic || "",
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
        parentLevelLabel={
          levelForm.open ? levelForm.parentLevelLabel : null
        }
        initialName={levelForm.open ? levelForm.initialName : undefined}
        initialCode={levelForm.open ? levelForm.initialCode : undefined}
        onClose={() => setLevelForm({ open: false })}
        onSubmit={() => {
          /* Write APIs not available yet — dialog shows notice. */
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
          setDeleteTarget(null);
          setNotice(t("geo_write_unavailable"));
        }}
        onClose={() => setDeleteTarget(null)}
      />
    </>
  );
}
