"use client";

import { useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useRouter } from "@/i18n/navigation";
import { ArrowLeft } from "lucide-react";
import { toast } from "react-toastify";
import TableSkeleton from "@/components/TableSkeleton";
import Can from "@/components/Can";
import EditButton from "@/components/EditButton";
import { useRbac } from "@/context/RbacContext";
import { useCatalogueApi, useCatalogueQuery } from "@/features/catalogue/api";
import { useCatalogueConfig } from "@/features/catalogue/hooks";
import AttributeSchemaEditor from "@/features/catalogue/components/AttributeSchemaEditor";
import ListDiffView from "@/features/catalogue/components/ListDiffView";
import VersionBar, { LIST_DRAFT_OPS, findOpenDraft } from "@/features/catalogue/components/VersionBar";
import VersionHistoryActivity from "@/features/catalogue/components/VersionHistoryActivity";
import { ErrorBox, Panel, Tabs, localizedLabel } from "@/features/catalogue/components/ui";
import { LicenceText, VisibilityBadge } from "@/features/catalogue/components/Publication";
import { themeKey, themeLabel } from "@/features/catalogue/theme";
import type { GetListResponse, GetListVersionsResponse, JsonSchema, VersionRef } from "@/features/catalogue/types";
import { useCatalogueLists } from "../hooks";
import AttributeDialog from "./AttributeDialog";
import AttributeValuesView from "./AttributeValuesView";
import { REFERENCE_DATA_ACTIONS } from "./AttributeListExplorer";

interface AttributeDetailProps {
    attributeId: string;
}

type TabKey = "values" | "schema" | "history" | "diff";

/**
 * One code list: version selector and badge, draft lifecycle, values (edited in the draft),
 * attribute schema, history (version history, each version expanding to its activity, plus the
 * list's full change feed) and diff between versions.
 */
export default function AttributeDetail({ attributeId }: AttributeDetailProps) {
    const t = useTranslations();
    const locale = useLocale();
    const router = useRouter();
    const call = useCatalogueApi();
    const { can } = useRbac();
    const { config } = useCatalogueConfig();
    const { allLists } = useCatalogueLists();

    const [tab, setTab] = useState<TabKey>("values");
    const [chosen, setChosen] = useState<VersionRef | null>(null);
    const [editOpen, setEditOpen] = useState(false);
    const [valuesNonce, setValuesNonce] = useState(0);

    const versionsQuery = useCatalogueQuery<GetListVersionsResponse>("get_list_versions", { list_code: attributeId });
    const versions = versionsQuery.data?.versions ?? [];
    const draft = findOpenDraft(versions);
    const hasPublished = versions.some((v) => v.status === "PUBLISHED" && v.is_latest);

    // Default: the version in effect, or the open draft for a list that was never published.
    const selected: VersionRef = chosen ?? (hasPublished || !draft ? "latest" : "draft");
    const effectiveSelected: VersionRef = selected === "draft" && !draft && versionsQuery.data ? "latest" : selected;

    const listQuery = useCatalogueQuery<GetListResponse>(
        "get_list",
        versionsQuery.data
            ? effectiveSelected === "latest" && !hasPublished
                ? { list_code: attributeId } // never published: metadata only
                : { list_code: attributeId, version: effectiveSelected }
            : null,
    );
    const list = listQuery.data?.list;
    const shown = listQuery.data?.version ?? null;

    const canEdit = can(REFERENCE_DATA_ACTIONS.edit);
    const editable = effectiveSelected === "draft" && draft?.status === "DRAFT" && canEdit;

    const reloadAll = (select?: VersionRef) => {
        if (select !== undefined) setChosen(select);
        versionsQuery.reload();
        listQuery.reload();
        setValuesNonce((n) => n + 1);
    };

    const backBar = (title?: string) => (
        <div className="flex items-center gap-2 mb-4">
            <button
                type="button"
                onClick={() => router.push("/datasets")}
                className="flex items-center gap-2 text-[18px] font-semibold text-black/80 hover:text-black transition-colors cursor-pointer"
            >
                <ArrowLeft size={18} />
                {t("reference_data")}
            </button>
            <span className="text-[22px] text-black">&gt;</span>
            {title ? (
                <h1 className="font-semibold text-[18px] text-black">{title}</h1>
            ) : (
                <div className="h-6 bg-gray-200 rounded animate-pulse w-1/4"></div>
            )}
        </div>
    );

    if (versionsQuery.error && !versionsQuery.data) {
        return (
            <div>
                {backBar(attributeId)}
                <ErrorBox message={versionsQuery.error} />
            </div>
        );
    }

    if (!list) {
        return (
            <div>
                {backBar()}
                {listQuery.error ? <ErrorBox message={listQuery.error} /> : <TableSkeleton rows={10} columns={4} />}
            </div>
        );
    }

    const title = localizedLabel(list.display, list.display_i18n, locale) || list.list_code || list.list_id;
    const listCode = list.list_code || list.list_id;

    return (
        <div className="space-y-4">
            {backBar(title)}

            <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="space-y-1 text-[14px] text-gray-600">
                    <div>
                        <span className="font-mono text-gray-800">{listCode}</span>
                        {list.owner_org ? (
                            <span>
                                {" · "}
                                {t("cat_owner_org")}: <span className="text-gray-800">{list.owner_org}</span>
                            </span>
                        ) : null}
                        <span>
                            {" · "}
                            {t("cat_theme")}: <span className="text-gray-800">{themeLabel(themeKey(list), t)}</span>
                        </span>
                        {list.is_hierarchical ? <span>{` · ${t("is_hierarchical")}`}</span> : null}
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                        <VisibilityBadge visibility={list.visibility} />
                        <LicenceText uri={list.licence_uri} label={list.licence_label} />
                    </div>
                    {list.description ? <p className="max-w-3xl">{list.description}</p> : null}
                    {list.display_i18n && Object.keys(list.display_i18n).length ? (
                        <p className="text-[13px]">
                            {Object.entries(list.display_i18n)
                                .map(([l, v]) => `${l}: ${v}`)
                                .join(" · ")}
                        </p>
                    ) : null}
                </div>
                <Can action={REFERENCE_DATA_ACTIONS.edit}>
                    <EditButton onClick={() => setEditOpen(true)}>{t("cat_edit_list")}</EditButton>
                </Can>
            </div>

            <VersionBar
                versions={versions}
                selected={effectiveSelected}
                onSelect={setChosen}
                shown={shown}
                subject={{ list_code: list.list_id }}
                ops={LIST_DRAFT_OPS}
                editPermission={REFERENCE_DATA_ACTIONS.edit}
                publishPermission={REFERENCE_DATA_ACTIONS.publish}
                approvalMode={config?.approval_mode}
                onChanged={reloadAll}
            />

            <ErrorBox message={listQuery.error} />

            <Tabs<TabKey>
                tabs={[
                    { key: "values", label: t("cat_tab_values") },
                    { key: "schema", label: t("cat_tab_schema") },
                    { key: "history", label: t("cat_group_history") },
                    { key: "diff", label: t("cat_tab_diff") },
                ]}
                active={tab}
                onChange={setTab}
            />

            {tab === "values" ? (
                <AttributeValuesView
                    key={`${list.list_id}-${String(effectiveSelected)}-${list.is_hierarchical}`}
                    list={list}
                    version={effectiveSelected}
                    editable={editable}
                    hasDraft={Boolean(draft)}
                    reloadNonce={valuesNonce}
                    onChanged={() => versionsQuery.reload()}
                />
            ) : null}

            {tab === "schema" ? (
                <Panel>
                    <AttributeSchemaEditor
                        key={`${String(effectiveSelected)}-${JSON.stringify(list.attribute_schema ?? null)}`}
                        value={list.attribute_schema}
                        knownLists={allLists.map((l) => l.list_code || l.list_id)}
                        readOnly={!editable}
                        onSave={async (schema: JsonSchema | null) => {
                            await call("update_list", { list_code: list.list_id, attribute_schema: schema });
                            toast.success(t("cat_schema_saved"));
                            reloadAll();
                        }}
                    />
                </Panel>
            ) : null}

            {tab === "history" ? (
                <VersionHistoryActivity
                    subjectType="list"
                    subjectId={list.list_id}
                    versions={versions}
                    onView={(ref) => {
                        setChosen(ref);
                        setTab("values");
                    }}
                />
            ) : null}

            {tab === "diff" ? (
                <Panel>
                    <ListDiffView listCode={list.list_id} versions={versions} />
                </Panel>
            ) : null}

            {editOpen ? (
                <AttributeDialog
                    open
                    mode="edit"
                    attribute={list}
                    onClose={() => setEditOpen(false)}
                    onSuccess={(result) => reloadAll(result.draft && !draft ? "draft" : undefined)}
                />
            ) : null}
        </div>
    );
}
