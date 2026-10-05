import type { useTranslations } from "next-intl";
import type { ListSummary } from "./types";

/** Theme key of a dataset: its `domain` (lower-case), or "" when unknown (shown as "Other"). */
export function themeKey(list: Pick<ListSummary, "domain">): string {
    return (list.domain ?? "").trim().toLowerCase();
}

/**
 * Label of a theme: a translated name when the locale has one (`cat_theme_<key>`), otherwise the
 * key in title case; "" (no domain) is "Other".
 */
export function themeLabel(key: string, t: ReturnType<typeof useTranslations>): string {
    if (!key) return t("cat_theme_other");
    const msg = `cat_theme_${key}`;
    if (t.has(msg)) return t(msg);
    return key
        .split(/[_\s-]+/)
        .filter(Boolean)
        .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
        .join(" ");
}

/** Themes present in the given datasets: Core first, then by label, Other ("") last. */
export function themesOf(lists: Pick<ListSummary, "domain">[], t: ReturnType<typeof useTranslations>): string[] {
    const keys = Array.from(new Set(lists.map(themeKey)));
    const rank = (k: string) => (k === "core" ? 0 : k === "" ? 2 : 1);
    return keys.sort((a, b) => rank(a) - rank(b) || themeLabel(a, t).localeCompare(themeLabel(b, t)));
}
