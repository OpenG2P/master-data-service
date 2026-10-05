"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import Button from "@/components/Button";
import Pagination from "@/components/Pagination";
import { errorMessage, useCatalogueApi } from "../api";
import type { ChangeEvent, GetChangesResponse } from "../types";
import { ErrorBox, formatDateTime, personLabel, tdClass, thClass } from "./ui";

const PAGE_LIMIT = 1000;
const MAX_PAGES = 20;
const PAGE_SIZE = 20;
const NO_EVENTS: ChangeEvent[] = [];

interface FeedState {
    key: string;
    nonce: number;
    events?: ChangeEvent[];
    truncated?: boolean;
    error?: string;
}

export interface ChangeFeedData {
    events: ChangeEvent[];
    truncated: boolean;
    error?: string;
    loading: boolean;
    reload: () => void;
}

/**
 * Loads the catalogue change feed (`get_changes`) from the start (up to MAX_PAGES × PAGE_LIMIT
 * events), filtered by subject, newest first. `enabled = false` skips loading (the caller passes
 * an already loaded feed).
 */
export function useChangeFeed(subjectType?: string, subjectId?: string, enabled = true): ChangeFeedData {
    const call = useCatalogueApi();
    const [nonce, setNonce] = useState(0);
    const [state, setState] = useState<FeedState>({ key: "", nonce: -1 });

    const key = JSON.stringify([subjectType || null, subjectId ?? null]);

    useEffect(() => {
        if (!enabled) return;
        const controller = new AbortController();
        const load = async () => {
            const all: ChangeEvent[] = [];
            let cursor = 0;
            let truncated = false;
            for (let i = 0; i < MAX_PAGES; i += 1) {
                const { payload } = await call<GetChangesResponse>(
                    "get_changes",
                    {
                        cursor,
                        limit: PAGE_LIMIT,
                        ...(subjectType ? { subject_type: subjectType } : {}),
                        ...(subjectId ? { subject_id: subjectId } : {}),
                    },
                    undefined,
                    controller.signal,
                );
                all.push(...payload.events);
                cursor = payload.next_cursor;
                if (!payload.has_more) break;
                if (i === MAX_PAGES - 1) truncated = true;
            }
            return { events: all.reverse(), truncated };
        };
        load().then(
            (r) => {
                if (!controller.signal.aborted) setState({ key, nonce, ...r });
            },
            (e: unknown) => {
                if (!controller.signal.aborted) setState({ key, nonce, error: errorMessage(e) });
            },
        );
        return () => controller.abort();
    }, [key, nonce, call, subjectType, subjectId, enabled]);

    const reload = useCallback(() => setNonce((n) => n + 1), []);
    const current = state.key === key;
    return {
        events: (current ? state.events : undefined) ?? NO_EVENTS,
        truncated: current ? Boolean(state.truncated) : false,
        error: current ? state.error : undefined,
        loading: !current || state.nonce !== nonce,
        reload,
    };
}

const unitList = (v: unknown): string => (Array.isArray(v) ? v.map(String).join(", ") : v == null ? "" : String(v));

function formatValue(v: unknown): string {
    if (v == null) return "—";
    if (Array.isArray(v)) return v.every((x) => typeof x !== "object" || x === null) ? v.join(", ") : JSON.stringify(v);
    if (typeof v === "object") return JSON.stringify(v);
    return String(v);
}

/**
 * A readable one-line summary of an event's details: a sentence for known events (a recorded
 * geography change event: "SPLIT recorded: D1 → D1A, D1B"), otherwise `key: value` pairs.
 */
export function describeChange(e: ChangeEvent, t: ReturnType<typeof useTranslations>): string {
    const d = e.details ?? {};
    if (e.event_type === "geo.change.recorded") {
        const from = unitList(d.from);
        const to = unitList(d.to);
        const units = from && to ? `${from} → ${to}` : from || to;
        return t("cat_feed_change_recorded", { type: String(d.change_type ?? ""), units: units || "—" });
    }
    if (e.event_type === "geo.change.deleted") {
        return t("cat_feed_change_deleted", { id: String(d.change_id ?? "") });
    }
    const entries = Object.entries(d);
    if (!entries.length) return "—";
    return entries.map(([k, v]) => `${k}: ${formatValue(v)}`).join(" · ");
}

/** Display name of an event's subject type ("list" → "Dataset"); the raw type when unknown. */
export function subjectTypeLabel(type: string, t: ReturnType<typeof useTranslations>): string {
    const key = `cat_subject_type_${type}`;
    return t.has(key) ? t(key) : type;
}

/** A compact, newest-first timeline of events (used inside an expanded version row). */
export function ChangeTimeline({ events }: { events: ChangeEvent[] }) {
    const t = useTranslations();
    if (!events.length) return <p className="py-2 text-[13px] text-gray-500">{t("cat_feed_empty")}</p>;
    return (
        <ol className="space-y-2 border-l-2 border-[#f4bb1b]/60 pl-4">
            {events.map((e) => (
                <li key={e.event_id} className="text-[13px]">
                    <div className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5">
                        <span className="whitespace-nowrap text-gray-500">{formatDateTime(e.at)}</span>
                        <span className="font-mono text-gray-800">{e.event_type}</span>
                        <span className="text-gray-600">{personLabel(e.actor, e.actor_name)}</span>
                    </div>
                    <div
                        className="break-words text-gray-700"
                        title={e.details ? JSON.stringify(e.details) : ""}
                    >
                        {describeChange(e, t)}
                    </div>
                </li>
            ))}
        </ol>
    );
}

/**
 * The catalogue change feed, newest first, with a text filter and paging. Loads the feed itself
 * unless `feed` (from `useChangeFeed`) is passed.
 */
export default function ChangeFeed({
    subjectType,
    subjectId,
    showSubjectFilter = false,
    feed: given,
}: {
    subjectType?: "list" | "geo" | "release";
    subjectId?: string;
    showSubjectFilter?: boolean;
    feed?: ChangeFeedData;
}) {
    const t = useTranslations();
    const [filterType, setFilterType] = useState<string>(subjectType ?? "");
    const [query, setQuery] = useState("");
    const [page, setPage] = useState(1);
    const own = useChangeFeed(filterType, subjectId, !given);
    const feed = given ?? own;

    const loading = feed.loading;
    const events = useMemo(() => {
        const list = feed.events;
        const q = query.trim().toLowerCase();
        if (!q) return list;
        return list.filter(
            (e) =>
                e.event_type.toLowerCase().includes(q) ||
                (e.subject_id ?? "").toLowerCase().includes(q) ||
                (e.actor ?? "").toLowerCase().includes(q) ||
                (e.actor_name ?? "").toLowerCase().includes(q),
        );
    }, [feed.events, query]);

    const totalPages = Math.max(1, Math.ceil(events.length / PAGE_SIZE));
    const currentPage = Math.min(page, totalPages);
    const rows = events.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);

    return (
        <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-3">
                {showSubjectFilter ? (
                    <select
                        value={filterType}
                        onChange={(e) => {
                            setFilterType(e.target.value);
                            setPage(1);
                        }}
                        className="h-9 rounded border border-gray-300 bg-white px-2 text-[14px] outline-none focus:border-[#EABB13]"
                        aria-label={t("cat_subject")}
                    >
                        <option value="">{t("cat_subject_all")}</option>
                        <option value="list">{t("cat_subject_list")}</option>
                        <option value="geo">{t("cat_subject_geo")}</option>
                        <option value="release">{t("cat_subject_release")}</option>
                    </select>
                ) : null}
                <input
                    type="search"
                    value={query}
                    onChange={(e) => {
                        setQuery(e.target.value);
                        setPage(1);
                    }}
                    placeholder={t("cat_feed_search")}
                    className="h-9 w-64 rounded border border-gray-300 bg-white px-3 text-[14px] outline-none focus:border-[#EABB13]"
                />
                <Button variant="secondary" onClick={feed.reload} loading={loading}>
                    {t("refresh")}
                </Button>
            </div>

            <ErrorBox message={feed.error} />
            {feed.truncated ? <p className="text-[13px] text-gray-500">{t("cat_feed_truncated")}</p> : null}

            {loading && !feed.events.length ? (
                <p className="text-[14px] text-gray-500">{t("loading")}</p>
            ) : rows.length === 0 ? (
                <p className="py-6 text-center text-[14px] text-gray-500">{t("cat_feed_empty")}</p>
            ) : (
                <div className="overflow-auto">
                    <table className="w-full min-w-[800px] border-collapse">
                        <thead>
                            <tr>
                                <th className={thClass}>{t("cat_when")}</th>
                                <th className={thClass}>{t("cat_event")}</th>
                                <th className={thClass}>{t("cat_subject")}</th>
                                <th className={thClass}>{t("cat_version")}</th>
                                <th className={thClass}>{t("cat_actor")}</th>
                                <th className={thClass}>{t("cat_details")}</th>
                            </tr>
                        </thead>
                        <tbody>
                            {rows.map((e, i) => (
                                <tr key={e.event_id} className={i % 2 ? "bg-white" : "bg-gray-50"}>
                                    <td className={`${tdClass} whitespace-nowrap text-[13px]`}>{formatDateTime(e.at)}</td>
                                    <td className={`${tdClass} font-mono text-[13px]`}>{e.event_type}</td>
                                    <td className={`${tdClass} text-[13px]`}>
                                        {subjectTypeLabel(e.subject_type, t)}
                                        {e.subject_id ? `: ${e.subject_id}` : ""}
                                    </td>
                                    <td className={`${tdClass} text-[13px]`}>{e.version_no != null ? `v${e.version_no}` : "—"}</td>
                                    <td className={`${tdClass} text-[13px]`}>{personLabel(e.actor, e.actor_name)}</td>
                                    <td
                                        className={`${tdClass} max-w-md truncate text-[13px] text-gray-700`}
                                        title={e.details ? JSON.stringify(e.details) : ""}
                                    >
                                        {describeChange(e, t)}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}

            {events.length > PAGE_SIZE ? (
                <div className="flex justify-end">
                    <Pagination page={currentPage} pageSize={PAGE_SIZE} total={events.length} onPageChange={setPage} />
                </div>
            ) : null}
        </div>
    );
}
