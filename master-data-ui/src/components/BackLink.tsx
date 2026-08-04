"use client";

import { ArrowLeft } from "lucide-react";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";

type BackLinkProps = {
  href: string;
  label?: string;
};

export default function BackLink({ href, label }: BackLinkProps) {
  const t = useTranslations();

  return (
    <Link
      href={href}
      className="inline-flex items-center gap-2.5 mb-5 text-(--color-text-muted) text-[16px] font-medium hover:text-black"
      aria-label={label ?? t("back")}
    >
      <span className="inline-flex items-center justify-center w-9 h-9 rounded-xl bg-(--color-surface) border border-(--color-border) text-black transition-colors duration-150">
        <ArrowLeft size={20} strokeWidth={2} />
      </span>
      <span>{label ?? t("back")}</span>
    </Link>
  );
}
