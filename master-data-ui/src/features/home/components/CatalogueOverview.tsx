"use client";

import { useCallback, useMemo, useState, type ReactNode } from "react";
import { useLocale, useTranslations } from "next-intl";
import { ArrowRight } from "lucide-react";
import { Link, useRouter } from "@/i18n/navigation";
import SearchInput from "@/components/SearchInput";
import Button from "@/components/Button";
import { useRbac } from "@/context/RbacContext";
import { useCatalogueQuery } from "@/features/catalogue/api";
import { useCatalogueConfig } from "@/features/catalogue/hooks";
import { describeChange, subjectTypeLabel } from "@/features/catalogue/components/ChangeFeed";
import { findOpenDraft } from "@/features/catalogue/components/VersionBar";
import {
    ErrorBox,
    Panel,
    StatusBadge,
    formatDate,
    formatDateTime,
    localizedLabel,
    personLabel,
} from "@/features/catalogue/components/ui";
import { themeKey, themeLabel, themesOf } from "@/features/catalogue/theme";
import type {
    CatalogueGeoLevel,
    ChangeEvent,
    GetChangesResponse,
    GetGeoLevelsResponse,
    GetGeoUnitsResponse,
    GetGeoVersionsResponse,
    GetListsResponse,
    GetReleasesResponse,
    ListSummary,
} from "@/features/catalogue/types";

const EMPTY = {};
const LISTS_PAYLOAD = { include_unpublished: true };
const RECENT_PAYLOAD = { newest: true, limit: 10 };
const ONE_ROW = { current_page: 1, page_size: 1 };

const ACTIONS = {
    listEdit: "referenceData:edit",
    listPublish: "referenceData:publish",
    geoEdit: "geo:edit",
    geoPublish: "geo:publish",
};

const datasetHref = (listId: string) => `/datasets/${encodeURIComponent(listId)}`;

function SectionTitle({ title, href, linkLabel }: { title: string; href?: string; linkLabel?: string }) {
    return (
        <div className="mb-3 flex items-center justify-between gap-3">
            <h2 className="text-[18px] font-semibold text-black">{title}</h2>
            {href && linkLabel ? (
                <Link
                    href={href}
                    className="flex items-center gap-1 text-[14px] font-medium text-[#ED7C22] hover:underline"
                >
                    {linkLabel}
                    <ArrowRight size={14} />
                </Link>
            ) : null}
        </div>
    );
}

function StatTile({ label, value, sub, href }: { label: string; value: ReactNode; sub?: ReactNode; href: string }) {
    const className = "block rounded-[10px] bg-white p-4 shadow-sm transition-colors hover:bg-[#f4bb1b]/10";
    const body = (
        <>
            <div className="text-[13px] font-semibold uppercase tracking-wide text-gray-500">{label}</div>
            <div className="mt-1 text-[28px] font-semibold leading-tight text-black">{value}</div>
            {sub ? <div className="mt-0.5 truncate text-[13px] text-gray-600">{sub}</div> : null}
        </>
    );
    // An in-page anchor (#pending) is a plain link; pages go through the locale-aware Link.
    return href.startsWith("#") ? (
        <a href={href} className={className}>
            {body}
        </a>
    ) : (
        <Link href={href} className={className}>
            {body}
        </Link>
    );
}

/** Levels root first, each followed by its children (the geography's level chain). */
function orderLevels(levels: CatalogueGeoLevel[]): CatalogueGeoLevel[] {
    const ids = new Set(levels.map((l) => l.level_id));
    const out: CatalogueGeoLevel[] = [];
    const visit = (parent: string | null) => {
        for (const l of levels) {
            const p = l.parent_level_id && ids.has(l.parent_level_id) ? l.parent_level_id : null;
            if (p === parent && !out.includes(l)) {
                out.push(l);
                visit(l.level_id);
            }
        }
    };
    visit(null);
    return [...out, ...levels.filter((l) => !out.includes(l))];
}

/** Number of active administrative units of one level in a version (one `get_geo_units` row + total). */
function LevelUnitCount({ version, level }: { version: number; level: string }) {
    const { data } = useCatalogueQuery<GetGeoUnitsResponse>("get_geo_units", { version, level }, ONE_ROW);
    return <span className="font-semibold text-black">{data ? data.total.toLocaleString() : "…"}</span>;
}

interface PendingItem {
    key: string;
    label: string;
    sub: string;
    href: string;
    status: string;
    canAct: boolean;
}

/**
 * Home page: an overview of the catalogue — datasets by theme, the geography in effect, work
 * waiting for a maker or checker, and recent activity. All reads run in parallel; the only
 * per-item calls are one unit count per geography level.
 */
export default function CatalogueOverview() {
    const t = useTranslations();
    const locale = useLocale();
    const router = useRouter();
    const { can } = useRbac();
    const [search, setSearch] = useState("");

    const { config } = useCatalogueConfig();
    const listsQuery = useCatalogueQuery<GetListsResponse>("get_lists", LISTS_PAYLOAD);
    const geoVersionsQuery = useCatalogueQuery<GetGeoVersionsResponse>("get_geo_versions", EMPTY);
    const releasesQuery = useCatalogueQuery<GetReleasesResponse>("get_releases", EMPTY);
    const recentQuery = useCatalogueQuery<GetChangesResponse>("get_changes", RECENT_PAYLOAD);

    const lists = useMemo(() => listsQuery.data?.lists ?? [], [listsQuery.data]);
    const geoVersions = useMemo(() => geoVersionsQuery.data?.versions ?? [], [geoVersionsQuery.data]);
    const releases = useMemo(() => releasesQuery.data?.releases ?? [], [releasesQuery.data]);
    const recent: ChangeEvent[] = useMemo(
        () => [...(recentQuery.data?.events ?? [])].reverse(),
        [recentQuery.data],
    );

    // Geography in effect: the config's current version, else the highest published one.
    const currentGeoNo =
        config?.geo_current_version_no ??
        geoVersions.filter((v) => v.status === "PUBLISHED").reduce<number | null>(
            (max, v) => (max == null || v.version_no > max ? v.version_no : max),
            null,
        );
    const currentGeo = geoVersions.find((v) => v.version_no === currentGeoNo) ?? null;
    const geoDraft = findOpenDraft(geoVersions);
    const levelsQuery = useCatalogueQuery<GetGeoLevelsResponse>(
        "get_geo_levels",
        currentGeoNo != null ? { version: currentGeoNo } : null,
    );
    const levels = useMemo(() => orderLevels(levelsQuery.data?.levels ?? []), [levelsQuery.data]);
    const geoShown = levelsQuery.data?.version ?? currentGeo;

    const label = useCallback(
        (l: ListSummary) => localizedLabel(l.display, l.display_i18n, locale) || l.list_code || l.list_id,
        [locale],
    );

    const byTheme = useMemo(() => {
        const themes = themesOf(lists, t);
        return themes.map((k) => ({
            key: k,
            lists: lists
                .filter((l) => themeKey(l) === k)
                .sort((a, b) => label(a).localeCompare(label(b))),
        }));
    }, [lists, t, label]);

    const pending = useMemo(() => {
        const submitted: PendingItem[] = [];
        const drafts: PendingItem[] = [];
        for (const l of lists) {
            if (!l.open_draft_status) continue;
            const item: PendingItem = {
                key: `list:${l.list_id}`,
                label: label(l),
                sub: `${t("cat_dataset")} · v${l.open_draft_version_no}`,
                href: datasetHref(l.list_id),
                status: l.open_draft_status,
                canAct:
                    l.open_draft_status === "SUBMITTED" ? can(ACTIONS.listPublish) : can(ACTIONS.listEdit),
            };
            (l.open_draft_status === "SUBMITTED" ? submitted : drafts).push(item);
        }
        if (geoDraft) {
            const item: PendingItem = {
                key: "geo",
                label: t("geo_locations"),
                sub: `${t("cat_subject_geo")} · v${geoDraft.version_no}`,
                href: "/geo-locations",
                status: geoDraft.status,
                canAct: geoDraft.status === "SUBMITTED" ? can(ACTIONS.geoPublish) : can(ACTIONS.geoEdit),
            };
            (geoDraft.status === "SUBMITTED" ? submitted : drafts).push(item);
        }
        for (const r of releases) {
            if (r.status !== "DRAFT") continue;
            drafts.push({
                key: `release:${r.release_code}`,
                label: r.title || r.release_code,
                sub: `${t("cat_subject_type_release")} · ${r.release_code}`,
                href: "/releases",
                status: "DRAFT",
                canAct: can(ACTIONS.listEdit) || can(ACTIONS.listPublish),
            });
        }
        return { submitted, drafts };
    }, [lists, geoDraft, releases, can, t, label]);

    const publishedReleases = releases.filter((r) => r.status === "PUBLISHED");
    const latestRelease = publishedReleases
        .slice()
        .sort((a, b) => String(b.published_at ?? "").localeCompare(String(a.published_at ?? "")))[0];

    const goSearch = () => {
        const q = search.trim();
        router.push(q ? `/datasets?q=${encodeURIComponent(q)}` : "/datasets");
    };

    const subjectHref = (e: ChangeEvent): string | null => {
        if (e.subject_type === "list" && e.subject_id) return datasetHref(e.subject_id);
        if (e.subject_type === "geo") return "/geo-locations";
        if (e.subject_type === "release") return "/releases";
        return null;
    };

    const pendingList = (items: PendingItem[], empty: string) =>
        items.length === 0 ? (
            <p className="py-2 text-[14px] text-gray-500">{empty}</p>
        ) : (
            <ul className="divide-y divide-gray-100">
                {items.map((i) => (
                    <li key={i.key}>
                        <Link
                            href={i.href}
                            className="flex items-center justify-between gap-3 py-2 hover:bg-gray-50"
                        >
                            <div className="min-w-0">
                                <div className="truncate text-[15px] text-black">{i.label}</div>
                                <div className="truncate text-[12px] text-gray-500">{i.sub}</div>
                            </div>
                            <div className="flex shrink-0 items-center gap-2">
                                <StatusBadge status={i.status} label={t(`cat_status_${i.status}`)} />
                                {i.canAct ? (
                                    <span className="text-[13px] font-medium text-[#ED7C22]">
                                        {i.status === "SUBMITTED" ? t("home_review") : t("home_continue")}
                                    </span>
                                ) : null}
                            </div>
                        </Link>
                    </li>
                ))}
            </ul>
        );

    return (
        <div className="space-y-6">
            <div className="flex flex-wrap items-end justify-between gap-4">
                <div>
                    <h1 className="text-[24px] font-semibold text-black">{t("home_title")}</h1>
                    <p className="text-[14px] text-gray-600">{t("home_hint")}</p>
                </div>
                <form
                    className="flex items-center gap-2"
                    onSubmit={(e) => {
                        e.preventDefault();
                        goSearch();
                    }}
                >
                    <SearchInput value={search} onChange={setSearch} placeholder={t("search_attributes")} width="w-72" />
                    <Button type="submit" variant="warning">
                        {t("search")}
                    </Button>
                </form>
            </div>

            <ErrorBox message={listsQuery.error} />

            <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
                <StatTile
                    label={t("reference_data")}
                    href="/datasets"
                    value={listsQuery.data ? lists.length : "…"}
                    sub={listsQuery.data ? t("home_themes_count", { count: byTheme.length }) : undefined}
                />
                <StatTile
                    label={t("geo_locations")}
                    href="/geo-locations"
                    value={currentGeoNo != null ? `v${currentGeoNo}` : "—"}
                    sub={
                        geoShown?.unit_count != null
                            ? t("cat_units_total", { total: geoShown.unit_count.toLocaleString() })
                            : geoVersionsQuery.data && currentGeoNo == null
                              ? t("cat_not_published")
                              : undefined
                    }
                />
                <StatTile
                    label={t("home_pending")}
                    href="#pending"
                    value={pending.submitted.length + pending.drafts.length}
                    sub={t("home_pending_sub", { submitted: pending.submitted.length, drafts: pending.drafts.length })}
                />
                <StatTile
                    label={t("releases")}
                    href="/releases"
                    value={releasesQuery.data ? releases.length : "…"}
                    sub={
                        latestRelease
                            ? t("home_latest_release", { code: latestRelease.release_code })
                            : releasesQuery.data
                              ? t("cat_no_releases")
                              : undefined
                    }
                />
            </div>

            <div className="grid gap-6 xl:grid-cols-3">
                <Panel className="xl:col-span-2">
                    <SectionTitle
                        title={t("home_datasets_by_theme")}
                        href="/datasets"
                        linkLabel={t("home_all_datasets", { count: lists.length })}
                    />
                    {listsQuery.loading && !listsQuery.data ? (
                        <p className="text-[14px] text-gray-500">{t("loading")}</p>
                    ) : byTheme.length === 0 ? (
                        <p className="text-[14px] text-gray-500">{t("no_attributes")}</p>
                    ) : (
                        <div className="space-y-5">
                            {byTheme.map((g) => (
                                <section key={g.key || "other"}>
                                    <div className="mb-2 flex items-center gap-2">
                                        <Link
                                            href={`/datasets?theme=${encodeURIComponent(g.key || "other")}`}
                                            className="text-[15px] font-semibold text-black hover:underline"
                                        >
                                            {themeLabel(g.key, t)}
                                        </Link>
                                        <span className="rounded-full bg-[#f4bb1b]/20 px-2 py-0.5 text-[12px] font-semibold text-black">
                                            {g.lists.length}
                                        </span>
                                    </div>
                                    <div className="flex flex-wrap gap-2">
                                        {g.lists.map((l) => (
                                            <Link
                                                key={l.list_id}
                                                href={datasetHref(l.list_id)}
                                                title={l.list_code ?? l.list_id}
                                                className="rounded-full border border-gray-200 bg-gray-50 px-3 py-1 text-[13px] text-gray-800 hover:border-[#ED7C22] hover:text-black"
                                            >
                                                {label(l)}
                                                {l.open_draft_status ? (
                                                    <span className="ml-1 text-[#ED7C22]" title={t(`cat_status_${l.open_draft_status}`)}>
                                                        •
                                                    </span>
                                                ) : null}
                                            </Link>
                                        ))}
                                    </div>
                                </section>
                            ))}
                        </div>
                    )}
                </Panel>

                <div className="space-y-6">
                    <Panel>
                        <SectionTitle title={t("geo_locations")} href="/geo-locations" linkLabel={t("home_open")} />
                        <ErrorBox message={geoVersionsQuery.error || levelsQuery.error} />
                        {currentGeoNo == null ? (
                            <p className="text-[14px] text-gray-500">
                                {geoVersionsQuery.data ? t("cat_geo_empty") : t("loading")}
                            </p>
                        ) : (
                            <div className="space-y-3 text-[14px]">
                                <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
                                    <dt className="text-gray-500">{t("cat_country")}</dt>
                                    <dd className="text-black">{geoShown?.country || config?.country || "—"}</dd>
                                    <dt className="text-gray-500">{t("cat_version")}</dt>
                                    <dd className="text-black">
                                        v{currentGeoNo}{" "}
                                        <StatusBadge status="LATEST" label={t("cat_in_effect")} />
                                    </dd>
                                    <dt className="text-gray-500">{t("cat_effective_from")}</dt>
                                    <dd className="text-black">{formatDate(geoShown?.effective_from)}</dd>
                                </dl>
                                {levels.length ? (
                                    <table className="w-full text-[14px]">
                                        <thead>
                                            <tr className="text-left text-[13px] text-[#ED7C22]">
                                                <th className="pb-1 font-semibold">{t("geo_level")}</th>
                                                <th className="pb-1 text-right font-semibold">{t("cat_units")}</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {levels.map((l) => (
                                                <tr key={l.level_id} className="border-t border-gray-100">
                                                    <td className="py-1 text-gray-800">
                                                        {localizedLabel(l.display || l.level_mnemonic, l.display_i18n, locale)}
                                                    </td>
                                                    <td className="py-1 text-right">
                                                        <LevelUnitCount version={currentGeoNo} level={l.level_id} />
                                                    </td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                ) : null}
                            </div>
                        )}
                    </Panel>

                    <Panel>
                        <div id="pending" className="scroll-mt-4" />
                        <SectionTitle title={t("home_pending")} />
                        <h3 className="text-[13px] font-semibold uppercase tracking-wide text-gray-500">
                            {t("home_awaiting_approval")}
                        </h3>
                        {pendingList(pending.submitted, t("home_nothing_awaiting"))}
                        <h3 className="mt-3 text-[13px] font-semibold uppercase tracking-wide text-gray-500">
                            {t("home_drafts_in_progress")}
                        </h3>
                        {pendingList(pending.drafts, t("home_no_drafts"))}
                    </Panel>
                </div>
            </div>

            <Panel>
                <SectionTitle title={t("home_recent_activity")} href="/changes" linkLabel={t("home_all_activity")} />
                <ErrorBox message={recentQuery.error} />
                {recentQuery.loading && !recentQuery.data ? (
                    <p className="text-[14px] text-gray-500">{t("loading")}</p>
                ) : recent.length === 0 ? (
                    <p className="text-[14px] text-gray-500">{t("cat_feed_empty")}</p>
                ) : (
                    <ol className="divide-y divide-gray-100">
                        {recent.map((e) => {
                            const href = subjectHref(e);
                            const subject = `${subjectTypeLabel(e.subject_type, t)}${e.subject_id ? `: ${e.subject_id}` : ""}${
                                e.version_no != null ? ` · v${e.version_no}` : ""
                            }`;
                            return (
                                <li key={e.event_id} className="grid gap-x-4 gap-y-0.5 py-2 text-[13px] md:grid-cols-[170px_1fr]">
                                    <span className="whitespace-nowrap text-gray-500">{formatDateTime(e.at)}</span>
                                    <div className="min-w-0">
                                        <div className="flex flex-wrap items-baseline gap-x-3">
                                            {href ? (
                                                <Link href={href} className="font-medium text-black hover:underline">
                                                    {subject}
                                                </Link>
                                            ) : (
                                                <span className="font-medium text-black">{subject}</span>
                                            )}
                                            <span className="font-mono text-gray-600">{e.event_type}</span>
                                            <span className="text-gray-600">{personLabel(e.actor, e.actor_name)}</span>
                                        </div>
                                        <div
                                            className="truncate text-gray-700"
                                            title={e.details ? JSON.stringify(e.details) : ""}
                                        >
                                            {describeChange(e, t)}
                                        </div>
                                    </div>
                                </li>
                            );
                        })}
                    </ol>
                )}
            </Panel>
        </div>
    );
}
