"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useRbac } from "@/context/RbacContext";
import { useCatalogueQuery } from "@/features/catalogue/api";
import { useCatalogueConfig } from "@/features/catalogue/hooks";
import VersionBar, { GEO_DRAFT_OPS, findOpenDraft } from "@/features/catalogue/components/VersionBar";
import VersionHistoryActivity from "@/features/catalogue/components/VersionHistoryActivity";
import { ErrorBox, Panel, Tabs } from "@/features/catalogue/components/ui";
import { LicenceText, VisibilityBadge } from "@/features/catalogue/components/Publication";
import EditButton from "@/components/EditButton";
import type {
    GeoSettingsResponse,
    GetGeoLevelsResponse,
    GetGeoVersionsResponse,
    VersionRef,
} from "@/features/catalogue/types";
import GeoSettingsDialog from "./GeoSettingsDialog";
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

/** Top-level groups; Data has sub-tabs, Lineage shows two panels side by side, History merges versions and activity. */
type GroupKey = "data" | "lineage" | "history";
type DataTabKey = "hierarchy" | "units" | "boundaries";

const EMPTY = {};

/**
 * Geo Locations page: geography version selector and badge, draft lifecycle, and three groups:
 * Data (per version the hierarchy tree, a flat unit search and boundaries), Lineage (change events
 * and the crosswalk lookup side by side) and History (version history, each version expanding to
 * its activity, plus the geography's full change feed).
 */
export default function GeoCatalogueView() {
    const t = useTranslations();
    const { can } = useRbac();
    const { config } = useCatalogueConfig();
    const [group, setGroup] = useState<GroupKey>("data");
    const [dataTab, setDataTab] = useState<DataTabKey>("hierarchy");
    const [chosen, setChosen] = useState<VersionRef | null>(null);
    const [includeRetired, setIncludeRetired] = useState(false);
    const [treeNonce, setTreeNonce] = useState(0);
    const [settingsOpen, setSettingsOpen] = useState(false);
    const settingsQuery = useCatalogueQuery<GeoSettingsResponse>("get_geo_settings", EMPTY);
    const geoSettings = settingsQuery.data?.settings ?? null;

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

    const groups = [
        { key: "data" as const, label: t("cat_group_data") },
        { key: "lineage" as const, label: t("cat_group_lineage") },
        { key: "history" as const, label: t("cat_group_history") },
    ];
    const boundariesEnabled = Boolean(config?.boundary_store_enabled);
    const dataTabs = [
        { key: "hierarchy" as const, label: t("cat_tab_hierarchy") },
        { key: "units" as const, label: t("cat_tab_units") },
        { key: "boundaries" as const, label: t("cat_tab_boundaries"), hidden: !boundariesEnabled },
    ];
    // Boundaries can be hidden (boundary store disabled): fall back to the hierarchy.
    const activeDataTab: DataTabKey = dataTab === "boundaries" && !boundariesEnabled ? "hierarchy" : dataTab;

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

            <div className="flex flex-wrap items-center gap-3 text-[14px] text-gray-600">
                <VisibilityBadge visibility={geoSettings?.visibility} />
                <LicenceText uri={geoSettings?.licence_uri} label={geoSettings?.licence_label} />
                {can(GEO_ACTIONS.edit) ? (
                    <EditButton onClick={() => setSettingsOpen(true)}>{t("cat_geo_settings")}</EditButton>
                ) : null}
            </div>
            {settingsOpen ? (
                <GeoSettingsDialog
                    settings={geoSettings}
                    publicCatalogueEnabled={config?.public_catalogue_enabled}
                    onClose={() => setSettingsOpen(false)}
                    onSaved={() => settingsQuery.reload()}
                />
            ) : null}

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

            <Tabs<GroupKey> tabs={groups} active={group} onChange={setGroup} />

            {group === "data" ? (
                <div className="space-y-3">
                    <Tabs<DataTabKey> tabs={dataTabs} active={activeDataTab} onChange={setDataTab} />
                    {shown ? (
                        <>
                            {activeDataTab === "hierarchy" ? (
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

                            {activeDataTab === "units" ? (
                                <Panel>
                                    <GeoUnitsBrowser version={effective} levels={levels} editable={editable} onChanged={refreshMeta} />
                                </Panel>
                            ) : null}

                            {activeDataTab === "boundaries" ? (
                                <Panel>
                                    <GeoBoundaries shown={shown} levels={levels} editable={editable} onChanged={refreshMeta} />
                                </Panel>
                            ) : null}
                        </>
                    ) : null}
                </div>
            ) : null}

            {group === "lineage" ? (
                <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
                    {shown ? (
                        <Panel className="min-w-0 space-y-3">
                            <h2 className="text-[17px] font-semibold text-black">{t("cat_tab_changes")}</h2>
                            <GeoChangeEvents shown={shown} versions={versions} editable={editable} onChanged={refreshMeta} />
                        </Panel>
                    ) : null}
                    <Panel className="min-w-0 space-y-3">
                        <h2 className="text-[17px] font-semibold text-black">{t("cat_tab_crosswalk")}</h2>
                        <GeoCrosswalk versions={versions} />
                    </Panel>
                </div>
            ) : null}

            {group === "history" ? (
                <VersionHistoryActivity
                    subjectType="geo"
                    versions={versions}
                    extraHeader={t("cat_units")}
                    extraCell={(v) => (v.unit_count != null ? String(v.unit_count) : "—")}
                    onView={(ref) => {
                        setChosen(ref);
                        setGroup("data");
                        setDataTab("hierarchy");
                    }}
                />
            ) : null}
        </div>
    );
}
