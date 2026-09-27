"use client";

import { useEffect, useId, useMemo, useState } from "react";
import { X } from "lucide-react";
import { useTranslations } from "next-intl";
import ConfirmDialog from "@/components/ConfirmDialog";
import { useFetch } from "@/shared/hooks/useFetch";
import GeoLevelDialog from "./GeoLevelDialog";
import AddButton from "@/components/AddButton";
import DeleteButton from "@/components/DeleteButton";
import EditButton from "@/components/EditButton";
import Button from "@/components/Button";
import { toast } from "react-toastify";
import { getErrorMessage } from "@/shared/utils/errorHandler";
import type { GeoLevel } from "../types";
import {
  getLevelById,
  getLevelDepth,
  getLevelLabel,
  getRootLevels,
  orderGeoLevelsByHierarchy,
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
  const [isSaving, setIsSaving] = useState(false);
  const [levelForm, setLevelForm] = useState<
    | { open: false }
    | {
        open: true;
        mode: "add" | "edit";
        levelId?: string;
        parentLevelId?: string | null;
        parentLevelLabel: string | null;
        initialName?: string;
      }
  >({ open: false });
  const [deleteTarget, setDeleteTarget] = useState<GeoLevel | null>(null);
  const [showMainDialog, setShowMainDialog] = useState(true);

  useEffect(() => {
    if (!open) {
      setLevelForm({ open: false });
      setDeleteTarget(null);
      setShowMainDialog(true);
    }
  }, [open]);

  useEffect(() => {
    // Hide main dialog when sub-dialogs are open
    if (levelForm.open || deleteTarget) {
      setShowMainDialog(false);
    } else if (open) {
      setShowMainDialog(true);
    }
  }, [levelForm.open, deleteTarget, open]);

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

  const ordered = useMemo(() => orderGeoLevelsByHierarchy(levels), [levels]);
  const roots = useMemo(() => getRootLevels(ordered), [ordered]);

  const rows = useMemo(
    () =>
      ordered.map((level) => {
        const parent = level.parent_level_id
          ? getLevelById(ordered, level.parent_level_id)
          : undefined;
        return {
          level,
          parentLabel: parent ? getLevelLabel(parent) : null,
          depth: getLevelDepth(ordered, level.level_id),
        };
      }),
    [ordered]
  );

  const proceedDelete = async (level: GeoLevel) => {
    const result = await deleteLevel("/api/geo/delete-geo-level", {
      method: "POST",
      body: JSON.stringify({ level_id: level.level_id }),
    });

    if (result?.level_id) {
      toast.success(t("geo_level_deleted_successfully"));
      setDeleteTarget(null);
      setIsSaving(false);
      await onChanged?.();
    } else {
      setIsSaving(false);
      const rawError = (result as any)?.error || (result as any)?.statusText;
      const errorCode = (result as any)?.code;
      const errorMessage = getErrorMessage(rawError, errorCode, t);
      toast.error(errorMessage);
    }
  };

  if (!open) return null;

  return (
    <>
      {showMainDialog && (
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
            style={{ maxWidth: "900px" }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-6">
            <h2
              id={titleId}
              className="text-[22px] font-bold text-[#ED7C22]"
            >
              {t("geo_manage_levels_title")}
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

          <div className="modal-scroll overflow-y-auto max-h-[calc(80vh-120px)] pr-2">
            {rows.length === 0 ? (
              <p className="px-5 py-8 text-center text-[14px] text-gray-400">
                {t("geo_no_levels")}
              </p>
            ) : (
              <ul className="divide-y divide-gray-200">
                {rows.map(({ level, parentLabel, depth }) => (
                  <li key={level.level_id} className="px-5 py-4">
                    <p
                      className="font-semibold text-[16px] leading-none tracking-normal text-black"
                      style={{ paddingLeft: `${depth * 16}px` }}
                    >
                      {getLevelLabel(level)}
                    </p>
                    <p
                      className="mt-2 text-[13px] text-gray-500"
                      style={{ paddingLeft: `${depth * 16}px` }}
                    >
                      {t("geo_parent")}: {parentLabel ?? "—"}
                    </p>
                    <div className="mt-3 flex flex-wrap justify-end gap-4 text-[14px]">
                      <button
                        type="button"
                        onClick={() =>
                          setLevelForm({
                            open: true,
                            mode: "add",
                            parentLevelId: level.level_id,
                            parentLevelLabel: getLevelLabel(level),
                          })
                        }
                        className="cursor-pointer text-gray-600 hover:text-black hover:underline"
                      >
                        {t("geo_add_child_level")}
                      </button>
                      <EditButton onClick={() =>
                        setLevelForm({
                          open: true,
                          mode: "edit",
                          levelId: level.level_id,
                          parentLevelId: level.parent_level_id,
                          parentLevelLabel: parentLabel,
                          initialName: level.level_mnemonic || "",
                        })
                      }>
                        {t("edit")}
                      </EditButton>
                      <DeleteButton onClick={() => setDeleteTarget(level)}>
                        {t("delete")}
                      </DeleteButton>
                    </div>
                  </li>
                ))}
              </ul>
            )}
            <div className="shrink-0 pt-4 px-5">
              <AddButton
                onClick={() =>
                  setLevelForm({
                    open: true,
                    mode: "add",
                    parentLevelId: null,
                    parentLevelLabel: null,
                  })
                }
                label={roots.length === 0 ? t("geo_add_level") : t("geo_add_root_level")}
              />
            </div>
          </div>
        </div>
      </div>
      )}

      <GeoLevelDialog
        open={levelForm.open}
        mode={levelForm.open ? levelForm.mode : "add"}
        levelId={levelForm.open ? levelForm.levelId : undefined}
        parentLevelId={levelForm.open ? levelForm.parentLevelId : null}
        parentLevelLabel={
          levelForm.open ? levelForm.parentLevelLabel : null
        }
        initialName={levelForm.open ? levelForm.initialName : undefined}
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
        confirming={isSaving}
        onConfirm={() => {
          if (!deleteTarget) return;
          setIsSaving(true);
          void proceedDelete(deleteTarget);
        }}
        onClose={() => setDeleteTarget(null)}
      />
    </>
  );
}
