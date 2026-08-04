"use client";

import { useLocale, useTranslations } from "next-intl";
import { usePathname, useRouter } from "@/i18n/navigation";
import { routing } from "@/i18n/routing";

const LOCALE_LABELS: Record<string, string> = {
  en: "English"
};

export default function Footer() {
  const t = useTranslations();
  const locale = useLocale();
  const pathname = usePathname();
  const router = useRouter();

  const year = new Date().getFullYear();
  const localeLabel = LOCALE_LABELS[locale] ?? LOCALE_LABELS.en;

  const cycleLocale = () => {
    const locales = routing.locales;
    const currentIndex = locales.indexOf(locale as (typeof locales)[number]);
    const next = locales[(currentIndex + 1) % locales.length];
    router.replace(pathname, { locale: next });
  };

  return (
    <footer className="w-full shrink-0 bg-[#2B2B2B] text-white">
      <div className="mx-auto flex h-[60px] w-full max-w-[1440px] items-center justify-between px-[60px] md:px-[120px]">
        <p className="text-[14px] font-normal leading-none whitespace-nowrap">
          {t("footer_copyright", { year })}
        </p>

        <nav className="flex items-center text-[14px] font-normal leading-none whitespace-nowrap">
          <button
            type="button"
            onClick={cycleLocale}
            className="cursor-pointer hover:opacity-80"
          >
            {localeLabel}
          </button>
          <span aria-hidden className="mx-[15px]">
            |
          </span>
          <a href="#" className="hover:opacity-80">
            {t("privacy_policy")}
          </a>
          <span aria-hidden className="mx-[15px]">
            |
          </span>
          <a href="#" className="hover:opacity-80">
            {t("contact_us")}
          </a>
        </nav>
      </div>
    </footer>
  );
}
