"use client";

import { useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import Button from "@/components/Button";
import Pagination from "@/components/Pagination";
import { errorMessage, useCatalogueApi } from "../api";
import type { ChangeEvent, GetChangesResponse } from "../types";
import { ErrorBox, formatDateTime, personLabel, tdClass, thClass } from "./ui";

const PAGE_LIMIT = 1000;
const MAX_PAGES = 20;
const PAGE_SIZE = 20;

interface FeedState {
    key: string;
    nonce: number;
    events?: ChangeEvent[];
    truncated?: boolean;
    error?: string;
}

/**
 * The catalogue change feed (`get_changes`), newest first. Reads the cursor-based feed from the
 * start (up to MAX_PAGES × PAGE_LIMIT events) and filters by subject.
 */
export default function ChangeFeed({
    subjectType,
    subjectId,
    showSubjectFilter = false,
}: {
    subjectType?: "list" | "geo" | "release";
    subjectId?: string;
    showSubjectFilter?: boolean;
}) {
    const t = useTranslations();
    const call = useCatalogueApi();
    const [filterType, setFilterType] = useState<string>(subjectType ?? "");
    const [query, setQuery] = useState("");
    const [page, setPage] = useState(1);
    const [nonce, setNonce] = useState(0);
    const [state, setState] = useState<FeedState>({ key: "", nonce: -1 });

    const key = JSON.stringify([filterType || null, subjectId ?? null]);

    useEffect(() => {
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
                        ...(filterType ? { subject_type: filterType } : {}),
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
    }, [key, nonce, call, filterType, subjectId]);

    const loading = state.key !== key || state.nonce !== nonce;
    const events = useMemo(() => {
        const list = state.key === key ? state.events ?? [] : [];
        const q = query.trim().toLowerCase();
        if (!q) return list;
        return list.filter(
            (e) =>
                e.event_type.toLowerCase().includes(q) ||
                (e.subject_id ?? "").toLowerCase().includes(q) ||
                (e.actor ?? "").toLowerCase().includes(q) ||
                (e.actor_name ?? "").toLowerCase().includes(q),
        );
    }, [state, key, query]);

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
                <Button variant="secondary" onClick={() => setNonce((n) => n + 1)} loading={loading}>
                    {t("refresh")}
                </Button>
            </div>

            <ErrorBox message={state.key === key ? state.error : undefined} />
            {state.truncated ? <p className="text-[13px] text-gray-500">{t("cat_feed_truncated")}</p> : null}

            {loading && !state.events ? (
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
                                        {e.subject_type}
                                        {e.subject_id ? `: ${e.subject_id}` : ""}
                                    </td>
                                    <td className={`${tdClass} text-[13px]`}>{e.version_no != null ? `v${e.version_no}` : "—"}</td>
                                    <td className={`${tdClass} text-[13px]`}>{personLabel(e.actor, e.actor_name)}</td>
                                    <td
                                        className={`${tdClass} max-w-md truncate font-mono text-[12px] text-gray-600`}
                                        title={e.details ? JSON.stringify(e.details) : ""}
                                    >
                                        {e.details && Object.keys(e.details).length ? JSON.stringify(e.details) : "—"}
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
