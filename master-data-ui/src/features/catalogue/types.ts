/**
 * Types of the Master Data catalogue API (`/catalogue/<op>` on master-data-api).
 * Field names follow master-data-api `schemas/g2p_catalogue.py`.
 */

/** Version selector: a number, "latest" (published version in effect) or "draft". */
export type VersionRef = number | "latest" | "draft";

export type VersionStatus =
    | "DRAFT"
    | "SUBMITTED"
    | "PUBLISHED"
    | "REJECTED"
    | "DISCARDED"
    | "RETIRED"
    | string;

export type ItemStatus = "ACTIVE" | "RETIRED" | string;

export type I18nLabels = Record<string, string>;

export interface VersionInfo {
    version_no: number;
    status: VersionStatus;
    base_version_no?: number | null;
    effective_from?: string | null;
    published_at?: string | null;
    is_latest?: boolean;
    change_note?: string | null;
    /** `*_by`: stable user id (token `sub`) or a system name; `*_by_name`: display name. */
    created_by?: string | null;
    created_by_name?: string | null;
    created_at?: string | null;
    updated_by?: string | null;
    updated_by_name?: string | null;
    updated_at?: string | null;
    submitted_by?: string | null;
    submitted_by_name?: string | null;
    submitted_at?: string | null;
    decided_by?: string | null;
    decided_by_name?: string | null;
    decided_at?: string | null;
    decision_note?: string | null;
    approval_ref?: string | null;
}

export interface CatalogueConfig {
    approval_mode: "permission" | "awe";
    boundary_store_enabled: boolean;
    audit_enabled: boolean;
    websub_enabled: boolean;
    country?: string | null;
    geo_current_version_no?: number | null;
}

/* ------------------------------------------------------------------ Lists */

export interface AttributeSchemaSummary {
    properties?: string[];
    required?: string[];
    list_refs?: Record<string, string>;
    [key: string]: unknown;
}

export type JsonSchema = Record<string, unknown>;

export interface ListSummary {
    list_id: string;
    list_code?: string | null;
    display?: string | null;
    display_i18n?: I18nLabels | null;
    description?: string | null;
    owner_org?: string | null;
    /** Pack domain ("core", "agriculture", ...), shown as the dataset's Theme; null when unknown. */
    domain?: string | null;
    is_hierarchical: boolean;
    attribute_schema?: JsonSchema | null;
    attribute_schema_summary?: AttributeSchemaSummary | null;
    current_version_no?: number | null;
    latest_published_version_no?: number | null;
    open_draft_version_no?: number | null;
    open_draft_status?: VersionStatus | null;
}

export interface ListValue {
    value_id: string;
    value_code: string;
    display?: string | null;
    display_i18n?: I18nLabels | null;
    parent_code?: string | null;
    sort_order?: number | null;
    attributes?: Record<string, unknown> | null;
    roles?: string[] | null;
    status: ItemStatus;
}

export interface GetListsResponse {
    lists: ListSummary[];
}

export interface GetListResponse {
    list: ListSummary;
    version?: VersionInfo | null;
}

export interface GetListValuesResponse {
    list_code: string;
    version: VersionInfo;
    values: ListValue[];
    total: number;
}

export interface GetListVersionsResponse {
    list_code: string;
    versions: VersionInfo[];
}

export interface ValueChange {
    value_id: string;
    value_code: string;
    changes: Record<string, { before?: unknown; after?: unknown }>;
}

export interface ListDiffResponse {
    list_code: string;
    from_version?: number | null;
    to_version: number;
    metadata_changes: Record<string, { before?: unknown; after?: unknown }>;
    added: ListValue[];
    changed: ValueChange[];
    retired: ListValue[];
    reactivated: ListValue[];
}

export interface ListAndDraftResponse {
    list: ListSummary;
    draft?: VersionInfo | null;
}

export interface DraftResponse {
    list_code: string;
    draft: VersionInfo;
}

export interface DraftValueInput {
    value_code: string;
    display?: string | null;
    display_i18n?: I18nLabels | null;
    parent_code?: string | null;
    sort_order?: number | null;
    attributes?: Record<string, unknown> | null;
    value_id?: string;
    status?: "ACTIVE" | "RETIRED";
}

export interface UpsertDraftValuesResponse {
    list_code: string;
    draft: VersionInfo;
    values: ListValue[];
}

export interface RetireDraftValuesResponse {
    list_code: string;
    draft: VersionInfo;
    retired: string[];
    removed: string[];
}

/* -------------------------------------------------------------- Geography */

export interface GeoVersionInfo extends VersionInfo {
    country?: string | null;
    owner_org?: string | null;
    boundary_objects?: Record<string, string> | null;
    unit_count?: number | null;
}

export interface CatalogueGeoLevel {
    level_id: string;
    level_mnemonic: string;
    parent_level_id?: string | null;
    display?: string | null;
    display_i18n?: I18nLabels | null;
}

export interface GeoUnit {
    unit_id: string;
    level_id: string;
    name: string;
    name_i18n?: I18nLabels | null;
    parent_unit_id?: string | null;
    status: ItemStatus;
    valid_from?: string | null;
    valid_to?: string | null;
}

export const GEO_CHANGE_TYPES = [
    "CREATE",
    "RETIRE",
    "RENAME",
    "RECODE",
    "SPLIT",
    "MERGE",
    "REPARENT",
    "BOUNDARY_CHANGE",
] as const;

export type GeoChangeType = (typeof GEO_CHANGE_TYPES)[number];

export interface GeoChange {
    change_id: number;
    version_no: number;
    change_type: GeoChangeType | string;
    from_units: string[];
    to_units: string[];
    effective_date?: string | null;
    note?: string | null;
    is_auto: boolean;
    created_by?: string | null;
    created_by_name?: string | null;
    created_at?: string | null;
}

export interface GetGeoVersionsResponse {
    versions: GeoVersionInfo[];
}

export interface GetGeoLevelsResponse {
    version: GeoVersionInfo;
    levels: CatalogueGeoLevel[];
}

export interface GetGeoUnitsResponse {
    version: GeoVersionInfo;
    units: GeoUnit[];
    total: number;
}

export interface GetGeoChangesResponse {
    changes: GeoChange[];
}

export interface CrosswalkStep {
    version_no: number;
    change_id: number;
    change_type: string;
    from_units: string[];
    to_units: string[];
}

export interface GeoCrosswalkResponse {
    unit_id: string;
    from_version: number;
    to_version: number;
    direction: "forward" | "backward" | "none";
    unchanged: boolean;
    units: GeoUnit[];
    unmapped: string[];
    path: CrosswalkStep[];
}

export interface GeoDraftResponse {
    draft: GeoVersionInfo;
}

export interface UploadDraftBoundaryResponse {
    draft: GeoVersionInfo;
    level: string;
    object_key: string;
    features: number;
}

/* --------------------------------------------------------------- Releases */

export interface ReleaseInfo {
    release_code: string;
    title?: string | null;
    note?: string | null;
    status: "DRAFT" | "PUBLISHED" | string;
    geo_version_no?: number | null;
    created_by?: string | null;
    created_by_name?: string | null;
    created_at?: string | null;
    members_set_by?: string | null;
    members_set_by_name?: string | null;
    members_set_at?: string | null;
    published_by?: string | null;
    published_by_name?: string | null;
    published_at?: string | null;
    member_count: number;
}

export interface ReleaseMember {
    list_id?: string | null;
    list_code: string;
    version_no: number;
}

export interface GetReleasesResponse {
    releases: ReleaseInfo[];
}

export interface GetReleaseResponse {
    release: ReleaseInfo;
    members: ReleaseMember[];
}

/* ------------------------------------------------------------ Change feed */

export interface ChangeEvent {
    event_id: number;
    event_type: string;
    subject_type: "list" | "geo" | "release" | string;
    subject_id?: string | null;
    version_no?: number | null;
    /** Stable user id (token `sub`) or a system name; `actor_name`: a user's display name. */
    actor?: string | null;
    actor_name?: string | null;
    at: string;
    details?: Record<string, unknown> | null;
}

export interface GetChangesResponse {
    events: ChangeEvent[];
    next_cursor: number;
    has_more: boolean;
}

export interface CataloguePagination {
    current_page?: number;
    page_size?: number;
    number_of_items?: number;
    number_of_pages?: number;
}
