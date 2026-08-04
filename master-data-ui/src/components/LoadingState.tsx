"use client";

import Image from "next/image";
import { useTranslations } from "next-intl";

type LoadingStateProps = {
  label?: string;
  fullScreen?: boolean;
  compact?: boolean;
  loaderOnly?: boolean;
};

export default function LoadingState({
  label,
  fullScreen = false,
  compact = false,
  loaderOnly = false,
}: LoadingStateProps) {
  const t = useTranslations();
  const text = label ?? t("loading");

  if (loaderOnly) {
    return (
      <div className="flex items-center justify-center py-12 px-4 min-h-[200px]">
        <Image
          src="/loading.gif"
          alt={text}
          width={48}
          height={48}
          priority
          unoptimized
        />
      </div>
    );
  }

  return (
    <div
      className={
        fullScreen
          ? "w-full min-h-screen flex items-center justify-center bg-[var(--color-surface)]"
          : compact
            ? "flex items-center justify-center p-6 min-h-[120px]"
            : "flex items-center justify-center py-12 px-4 min-h-[200px]"
      }
    >
      <div className="flex flex-col items-center gap-4">
        <Image
          src="/loading.gif"
          alt={text}
          width={48}
          height={48}
          priority
          unoptimized
        />
        <p className="text-[rgba(6,19,39,0.55)] text-[16px] m-0">
          {text}
        </p>
      </div>
    </div>
  );
}
