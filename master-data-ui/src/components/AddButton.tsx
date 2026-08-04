"use client";

import { Plus } from "lucide-react";
import { useTranslations } from "next-intl";

type AddButtonProps = {
  onClick: () => void;
  label?: string;
  disabled?: boolean;
};

export default function AddButton({
  onClick,
  label,
  disabled = false,
}: AddButtonProps) {
  const t = useTranslations();

  return (
    <button
      type="button"
      className="inline-flex items-center gap-2 bg-(--color-accent) text-black text-[16px] font-medium px-4 py-2 rounded-[10px] cursor-pointer border-none transition-colors duration-150 hover:bg-(--color-accent-hover) disabled:opacity-50 disabled:not-allowed"
      onClick={onClick}
      disabled={disabled}
    >
      <Plus size={18} strokeWidth={3} aria-hidden />
      <span>{label ?? t("add")}</span>
    </button>
  );
}
