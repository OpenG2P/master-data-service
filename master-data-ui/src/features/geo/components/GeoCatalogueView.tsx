"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useRbac } from "@/context/RbacContext";
import { useCatalogueQuery } from "@/features/catalogue/api";
import { useCatalogueConfig } from "@/features/catalogue/hooks";
import ChangeFeed from "@/features/catalogue/components/ChangeFeed";
import VersionBar, { GEO_DRAFT_OPS, findOpenDraft } from "@/features/catalogue/components/VersionBar";
import VersionHistoryTable from "@/features/catalogue/components/VersionHistoryTable";
import { ErrorBox, Panel, Tabs } from "@/features/catalogue/components/ui";
import type { GetGeoLevelsResponse, GetGeoVersionsResponse, VersionRef } from "@/features/catalogue/types";
import GeoBoundaries from "./GeoBoundaries";
import GeoChangeEvents from "./GeoChangeEvents";
import GeoCrosswalk from "./GeoCrosswalk";
import GeoHierarchyExplorer from "./GeoHierarchyExplorer";
import GeoUnitsBrowser from "./GeoUnitsBrowser";

export const GEO_ACTIONS = {
    edit: "geo:edit",
    delete: "geo:delete",
    publish: "geo:publish",
};

type TabKey = "hierarchy" | "units" | "changes" | "boundaries" | "crosswalk" | "history" | "activity";

const EMPTY = {};

/**
 * Geo Locations page: geography version selector and badge, draft lifecycle, and per version the
 * hierarchy (tree), a flat unit search, change events (lineage), boundaries, crosswalk lookup,
 * version history and the geography change feed.
 */
export default function GeoCatalogueView() {
    const t = useTranslations();
    const { can } = useRbac();
    const { config } = useCatalogueConfig();
    const [tab, setTab] = useState<TabKey>("hierarchy");
    const [chosen, setChosen] = useState<VersionRef | null>(null);
    const [includeRetired, setIncludeRetired] = useState(false);
    const [treeNonce, setTreeNonce] = useState(0);

    const versionsQuery = useCatalogueQuery<GetGeoVersionsResponse>("get_geo_versions", EMPTY);
    const versions = versionsQuery.data?.versions ?? [];
    const draft = findOpenDraft(versions);
    const hasPublished = versions.some((v) => v.status === "PUBLISHED");

    const selected: VersionRef = chosen ?? (hasPublished || !draft ? "latest" : "draft");
    const effective: VersionRef = selected === "draft" && !draft && versionsQuery.data ? "latest" : selected;

    const levelsQuery = useCatalogueQuery<GetGeoLevelsResponse>(
        "get_geo_levels",
        versionsQuery.data && (hasPublished || draft) ? { version: effective } : null,
    );
    const shown = levelsQuery.data?.version ?? null;
    const levels = levelsQuery.data?.levels ?? [];

    const editable = effective === "draft" && draft?.status === "DRAFT" && can(GEO_ACTIONS.edit);

    // After an edit inside a tab: refresh version metadata (who edited, unit count) only.
    const refreshMeta = () => {
        versionsQuery.reload();
        levelsQuery.reload();
    };
    // After a lifecycle action: also rebuild the tree.
    const reloadAll = (select?: VersionRef) => {
        if (select !== undefined) setChosen(select);
        refreshMeta();
        setTreeNonce((n) => n + 1);
    };

    const tabs = [
        { key: "hierarchy" as const, label: t("cat_tab_hierarchy") },
        { key: "units" as const, label: t("cat_tab_units") },
        { key: "changes" as const, label: t("cat_tab_changes") },
        { key: "boundaries" as const, label: t("cat_tab_boundaries"), hidden: !config?.boundary_store_enabled },
        { key: "crosswalk" as const, label: t("cat_tab_crosswalk") },
        { key: "history" as const, label: t("cat_tab_history") },
        { key: "activity" as const, label: t("cat_tab_activity") },
    ];

    return (
        <div className="space-y-4">
            <div className="flex flex-wrap items-baseline justify-between gap-4">
                <h1 className="font-semibold text-[24px] text-black">{t("geo_locations")}</h1>
                {shown ? (
                    <span className="text-[14px] text-gray-600">
                        {[
                            shown.country ? `${t("cat_country")}: ${shown.country}` : null,
                            shown.owner_org ? `${t("cat_owner_org")}: ${shown.owner_org}` : null,
                            shown.unit_count != null ? t("cat_units_total", { total: shown.unit_count }) : null,
                        ]
                            .filter(Boolean)
                            .join(" · ")}
                    </span>
                ) : null}
            </div>

            <ErrorBox message={versionsQuery.error} />

            {versionsQuery.data ? (
                <VersionBar
                    versions={versions}
                    selected={effective}
                    onSelect={setChosen}
                    shown={shown}
                    subject={{}}
                    ops={GEO_DRAFT_OPS}
                    editPermission={GEO_ACTIONS.edit}
                    publishPermission={GEO_ACTIONS.publish}
                    approvalMode={config?.approval_mode}
                    onChanged={reloadAll}
                />
            ) : null}

            <ErrorBox message={levelsQuery.error} />
            {versionsQuery.data && !hasPublished && !draft ? (
                <p className="rounded bg-gray-100 px-3 py-2 text-[13px] text-gray-700">{t("cat_geo_empty")}</p>
            ) : null}

            <Tabs<TabKey> tabs={tabs} active={tab} onChange={setTab} />

            {shown ? (
                <>
                    {tab === "hierarchy" ? (
                        <div className="space-y-2">
                            <div className="flex flex-wrap items-center gap-4">
                                <label className="flex cursor-pointer items-center gap-2 text-[14px] text-gray-700">
                                    <input
                                        type="checkbox"
                                        checked={includeRetired}
                                        onChange={(e) => setIncludeRetired(e.target.checked)}
                                        className="h-4 w-4 accent-[#f4bb1b]"
                                    />
                                    {t("cat_include_retired")}
                                </label>
                                {!editable && can(GEO_ACTIONS.edit) ? (
                                    <span className="text-[13px] text-gray-500">
                                        {draft ? t("cat_readonly_view_draft_hint") : t("cat_readonly_open_draft_hint")}
                                    </span>
                                ) : null}
                            </div>
                            <GeoHierarchyExplorer
                                key={`${String(effective)}-${includeRetired}-${treeNonce}`}
                                version={effective}
                                editable={editable}
                                includeRetired={includeRetired}
                                embedded
                                onChanged={refreshMeta}
                            />
                        </div>
                    ) : null}

                    {tab === "units" ? (
                        <Panel>
                            <GeoUnitsBrowser version={effective} levels={levels} editable={editable} onChanged={refreshMeta} />
                        </Panel>
                    ) : null}

                    {tab === "changes" ? (
                        <Panel>
                            <GeoChangeEvents shown={shown} versions={versions} editable={editable} onChanged={refreshMeta} />
                        </Panel>
                    ) : null}

                    {tab === "boundaries" && config?.boundary_store_enabled ? (
                        <Panel>
                            <GeoBoundaries shown={shown} levels={levels} editable={editable} onChanged={refreshMeta} />
                        </Panel>
                    ) : null}
                </>
            ) : null}

            {tab === "crosswalk" ? (
                <Panel>
                    <GeoCrosswalk versions={versions} />
                </Panel>
            ) : null}

            {tab === "history" ? (
                <Panel>
                    <VersionHistoryTable
                        versions={versions}
                        extraHeader={t("cat_units")}
                        extraCell={(v) => (v.unit_count != null ? String(v.unit_count) : "—")}
                        onView={(ref) => {
                            setChosen(ref);
                            setTab("hierarchy");
                        }}
                    />
                </Panel>
            ) : null}

            {tab === "activity" ? (
                <Panel>
                    <ChangeFeed subjectType="geo" />
                </Panel>
            ) : null}
        </div>
    );
}
