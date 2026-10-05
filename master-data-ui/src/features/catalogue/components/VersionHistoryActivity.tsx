"use client";

import { useMemo, useState, type ReactNode } from "react";
import { useTranslations } from "next-intl";
import type { ChangeEvent, VersionInfo, VersionRef } from "../types";
import ChangeFeed, { ChangeTimeline, useChangeFeed } from "./ChangeFeed";
import VersionHistoryTable from "./VersionHistoryTable";
import { ErrorBox, Panel, Tabs } from "./ui";

type HistoryView = "versions" | "activity";

/**
 * The History group of a catalogue subject (a code list or the geography): the version history,
 * where each version row expands to that version's activity timeline (the change feed filtered by
 * subject and version), and "All activity", the subject's full change feed. Both read one feed.
 */
export default function VersionHistoryActivity<V extends VersionInfo>({
    subjectType,
    subjectId,
    versions,
    onView,
    extraHeader,
    extraCell,
}: {
    subjectType: "list" | "geo";
    subjectId?: string;
    versions: V[];
    onView: (ref: VersionRef) => void;
    extraHeader?: string;
    extraCell?: (v: V) => ReactNode;
}) {
    const t = useTranslations();
    const [view, setView] = useState<HistoryView>("versions");
    const feed = useChangeFeed(subjectType, subjectId);

    const byVersion = useMemo(() => {
        const map = new Map<number, ChangeEvent[]>();
        for (const e of feed.events) {
            if (e.version_no == null) continue;
            const list = map.get(e.version_no);
            if (list) list.push(e);
            else map.set(e.version_no, [e]);
        }
        return map;
    }, [feed.events]);

    return (
        <div className="space-y-3">
            <Tabs<HistoryView>
                tabs={[
                    { key: "versions", label: t("cat_subtab_versions") },
                    { key: "activity", label: t("cat_subtab_all_activity") },
                ]}
                active={view}
                onChange={setView}
            />
            <Panel>
                {view === "versions" ? (
                    <VersionHistoryTable
                        versions={versions}
                        onView={onView}
                        extraHeader={extraHeader}
                        extraCell={extraCell}
                        renderExpanded={(v) =>
                            feed.loading && !feed.events.length ? (
                                <p className="text-[13px] text-gray-500">{t("loading")}</p>
                            ) : feed.error ? (
                                <ErrorBox message={feed.error} />
                            ) : (
                                <ChangeTimeline events={byVersion.get(v.version_no) ?? []} />
                            )
                        }
                    />
                ) : (
                    <ChangeFeed subjectType={subjectType} subjectId={subjectId} feed={feed} />
                )}
            </Panel>
        </div>
    );
}
