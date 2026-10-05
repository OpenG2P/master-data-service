"""Request/response models of the ``/catalogue`` API.

Same envelope as every other Master Data endpoint (openg2p-fastapi-common's
G2PRequest / G2PResponse): ``request_header`` + ``request_body.request_payload``
in, ``response_header`` + ``response_body.response_payload`` out. Errors come
back as HTTP 200 with ``response_status = ERROR`` and a ``G2P-CAT-*`` code, as
the existing endpoints do.

Version selection, on every read that returns versioned data
------------------------------------------------------------
- ``version``: a number, ``"latest"`` (the default — latest PUBLISHED version
  already in effect) or ``"draft"`` (the open draft, if any);
- ``as_of``: a date/time — the published version in effect at that moment;
- ``release``: a catalogue release code — the version that release pins.
At most one of them. Every such response carries a ``version`` object saying
which version the data came from.
"""

from datetime import date, datetime
from typing import Any, Dict, Generic, List, Literal, Optional, TypeVar, Union

from openg2p_fastapi_common.schemas import (
    G2PRequest,
    G2PRequestBody,
    G2PResponse,
    G2PResponseBody,
)
from pydantic import BaseModel, ConfigDict, Field

P = TypeVar("P")
R = TypeVar("R")


class CatalogueRequestBody(G2PRequestBody, Generic[P]):
    request_payload: P


class CatalogueRequest(G2PRequest, Generic[P]):
    request_body: CatalogueRequestBody[P]


class CatalogueResponseBody(G2PResponseBody, Generic[R]):
    response_payload: Optional[R] = None


class CatalogueResponse(G2PResponse, Generic[R]):
    response_body: CatalogueResponseBody[R]


# ---------------------------------------------------------------------------
# Shared pieces
# ---------------------------------------------------------------------------

VersionRef = Union[int, Literal["latest", "draft"]]


class VersionSelector(BaseModel):
    version: Optional[VersionRef] = Field(
        default=None,
        description='Version number, "latest" (default: latest published version in effect) or "draft".',
    )
    as_of: Optional[datetime] = Field(
        default=None, description="Return the published version in effect at this date/time."
    )
    release: Optional[str] = Field(
        default=None, description="Return the version pinned by this catalogue release."
    )


class VersionInfo(BaseModel):
    """Which version the data came from, and where it is in its lifecycle."""

    version_no: int
    status: str
    base_version_no: Optional[int] = None
    effective_from: Optional[datetime] = None
    published_at: Optional[datetime] = None
    is_latest: bool = False
    change_note: Optional[str] = None
    # *_by: the stable user id (token sub) or a system name; *_by_name: the
    # user's display name when they acted (None for a system actor).
    created_by: Optional[str] = None
    created_by_name: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_by: Optional[str] = None
    updated_by_name: Optional[str] = None
    updated_at: Optional[datetime] = None
    submitted_by: Optional[str] = None
    submitted_by_name: Optional[str] = None
    submitted_at: Optional[datetime] = None
    decided_by: Optional[str] = None
    decided_by_name: Optional[str] = None
    decided_at: Optional[datetime] = None
    decision_note: Optional[str] = None
    approval_ref: Optional[str] = None


class EmptyPayload(BaseModel):
    pass


# ---------------------------------------------------------------------------
# Lists
# ---------------------------------------------------------------------------


class ListSummary(BaseModel):
    list_id: str
    list_code: Optional[str] = None
    display: Optional[str] = None
    display_i18n: Optional[Dict[str, str]] = None
    description: Optional[str] = None
    owner_org: Optional[str] = None
    domain: Optional[str] = Field(
        default=None,
        description='Pack domain of the list ("core", "agriculture", ...). Set by the country-pack loader '
        "or on create/update; for a pack list loaded before the column existed it is derived from its "
        "first version's change note. NULL when unknown.",
    )
    is_hierarchical: bool = False
    attribute_schema: Optional[Dict[str, Any]] = None
    attribute_schema_summary: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Property names, required ones and list references of attribute_schema.",
    )
    current_version_no: Optional[int] = Field(
        default=None, description="Published version currently in effect."
    )
    latest_published_version_no: Optional[int] = Field(
        default=None, description="Highest published version (may be future-effective)."
    )
    open_draft_version_no: Optional[int] = None
    open_draft_status: Optional[str] = None


class ListValue(BaseModel):
    value_id: str
    value_code: str
    display: Optional[str] = None
    display_i18n: Optional[Dict[str, str]] = None
    parent_code: Optional[str] = None
    sort_order: Optional[int] = None
    attributes: Optional[Dict[str, Any]] = None
    roles: Optional[List[str]] = None
    status: str = "ACTIVE"


class ListRef(BaseModel):
    list_code: str = Field(..., description="List code (or list id).")


class GetListsPayload(BaseModel):
    include_unpublished: bool = Field(
        default=True, description="Include lists that have never been published."
    )


class GetListsResponsePayload(BaseModel):
    lists: List[ListSummary] = []


class GetListPayload(ListRef, VersionSelector):
    pass


class GetListResponsePayload(BaseModel):
    list: ListSummary
    version: Optional[VersionInfo] = None


class GetListValuesPayload(ListRef, VersionSelector):
    include_retired: bool = False
    parent_code: Optional[str] = Field(
        default=None, description="Only children of this value (hierarchical lists)."
    )
    attribute_filters: Optional[Dict[str, Any]] = Field(
        default=None,
        description='Match values whose attributes contain these key/values, e.g. {"crop": "CROP_TEFF"}.',
    )
    search: Optional[str] = Field(default=None, description="Case-insensitive match on code or label.")

    model_config = ConfigDict(json_schema_extra={"example": {"list_code": "GENDER", "version": "latest"}})


class GetListValuesResponsePayload(BaseModel):
    list_code: str
    version: VersionInfo
    values: List[ListValue] = []
    total: int = 0


class GetListValuePayload(ListRef, VersionSelector):
    value_code: str


class GetListValueResponsePayload(BaseModel):
    list_code: str
    version: VersionInfo
    value: ListValue


class GetListVersionsResponsePayload(BaseModel):
    list_code: str
    versions: List[VersionInfo] = []


class GetListDiffPayload(ListRef):
    from_version: Optional[int] = Field(default=None, description="Defaults to the base of to_version.")
    to_version: Optional[VersionRef] = Field(default=None, description='Defaults to "latest".')


class ValueChange(BaseModel):
    value_id: str
    value_code: str
    changes: Dict[str, Dict[str, Any]] = Field(default_factory=dict, description="{field: {before, after}}")


class GetListDiffResponsePayload(BaseModel):
    list_code: str
    from_version: Optional[int] = None
    to_version: int
    metadata_changes: Dict[str, Dict[str, Any]] = {}
    added: List[ListValue] = []
    changed: List[ValueChange] = []
    retired: List[ListValue] = []
    reactivated: List[ListValue] = []


class CreateListPayload(BaseModel):
    list_code: str
    display: str
    display_i18n: Optional[Dict[str, str]] = None
    description: Optional[str] = None
    owner_org: Optional[str] = None
    domain: Optional[str] = Field(
        default=None, description='Pack domain ("core", "agriculture", ...); stored lower-case.'
    )
    is_hierarchical: bool = False
    attribute_schema: Optional[Dict[str, Any]] = None
    list_id: Optional[str] = Field(default=None, description="Defaults to list_code.")
    change_note: Optional[str] = None


class ListAndDraftResponsePayload(BaseModel):
    list: ListSummary
    draft: Optional[VersionInfo] = None


class UpdateListPayload(ListRef):
    description: Optional[str] = Field(default=None, description="Applied directly (not versioned).")
    owner_org: Optional[str] = Field(default=None, description="Applied directly (not versioned).")
    domain: Optional[str] = Field(
        default=None, description="Applied directly (not versioned); lower-case, empty clears it."
    )
    new_list_code: Optional[str] = Field(default=None, description="Goes into the open draft.")
    display: Optional[str] = Field(default=None, description="Goes into the open draft.")
    display_i18n: Optional[Dict[str, str]] = Field(default=None, description="Goes into the open draft.")
    is_hierarchical: Optional[bool] = Field(default=None, description="Goes into the open draft.")
    attribute_schema: Optional[Dict[str, Any]] = Field(
        default=None, description="Goes into the open draft; validated on submit."
    )


class CreateListDraftPayload(ListRef):
    base_version: Optional[int] = Field(
        default=None,
        description="Published version to start from; defaults to the highest published version.",
    )
    copy_from_version: Optional[int] = Field(
        default=None,
        description="Copy content from this version instead (e.g. a REJECTED draft to rework). Base stays as above.",
    )
    change_note: Optional[str] = None
    effective_from: Optional[datetime] = None


class UpdateListDraftPayload(ListRef):
    change_note: Optional[str] = None
    effective_from: Optional[datetime] = None


class DraftResponsePayload(BaseModel):
    list_code: str
    draft: VersionInfo


class DraftValueInput(BaseModel):
    value_code: str
    display: Optional[str] = None
    display_i18n: Optional[Dict[str, str]] = None
    parent_code: Optional[str] = None
    sort_order: Optional[int] = None
    attributes: Optional[Dict[str, Any]] = None
    roles: Optional[List[str]] = None
    value_id: Optional[str] = Field(
        default=None,
        description="Stable id. Give it to change a value's code (RECODE); omit to match on value_code.",
    )
    status: Optional[Literal["ACTIVE", "RETIRED"]] = Field(default=None, description="ACTIVE re-activates.")


class UpsertDraftValuesPayload(ListRef):
    values: List[DraftValueInput]


class UpsertDraftValuesResponsePayload(BaseModel):
    list_code: str
    draft: VersionInfo
    values: List[ListValue] = []


class RetireDraftValuesPayload(ListRef):
    value_codes: List[str]
    cascade: bool = Field(default=False, description="Also retire descendants (hierarchical lists).")


class RetireDraftValuesResponsePayload(BaseModel):
    list_code: str
    draft: VersionInfo
    retired: List[str] = []
    removed: List[str] = Field(
        default_factory=list, description="Values new in this draft, removed outright."
    )


class SubmitDraftPayload(ListRef):
    change_note: Optional[str] = None
    effective_from: Optional[datetime] = None


class DecideDraftPayload(ListRef):
    version_no: Optional[int] = Field(default=None, description="Guard: the submitted version being decided.")
    decision_note: Optional[str] = None
    effective_from: Optional[datetime] = Field(
        default=None, description="Approve only: override effective_from."
    )


class DiscardDraftResponsePayload(BaseModel):
    list_code: str
    discarded_version_no: int


# ---------------------------------------------------------------------------
# Geography
# ---------------------------------------------------------------------------


class GeoVersionInfo(VersionInfo):
    country: Optional[str] = None
    owner_org: Optional[str] = None
    boundary_objects: Optional[Dict[str, str]] = None
    unit_count: Optional[int] = None


class GeoLevel(BaseModel):
    level_id: str
    level_mnemonic: str
    parent_level_id: Optional[str] = None
    display: Optional[str] = None
    display_i18n: Optional[Dict[str, str]] = None


class GeoUnit(BaseModel):
    unit_id: str
    level_id: str
    name: str
    name_i18n: Optional[Dict[str, str]] = None
    parent_unit_id: Optional[str] = None
    status: str = "ACTIVE"
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None


class GeoChange(BaseModel):
    change_id: int
    version_no: int
    change_type: str
    from_units: List[str] = []
    to_units: List[str] = []
    effective_date: Optional[date] = None
    note: Optional[str] = None
    is_auto: bool = False
    created_by: Optional[str] = None
    created_by_name: Optional[str] = None
    created_at: Optional[datetime] = None


class GetGeoVersionsResponsePayload(BaseModel):
    versions: List[GeoVersionInfo] = []


class GetGeoLevelsPayload(VersionSelector):
    pass


class GetGeoLevelsResponsePayload(BaseModel):
    version: GeoVersionInfo
    levels: List[GeoLevel] = []


class GetGeoUnitsPayload(VersionSelector):
    level: Optional[str] = Field(default=None, description="Level id or mnemonic.")
    parent_unit_id: Optional[str] = None
    include_retired: bool = False
    search: Optional[str] = Field(default=None, description="Case-insensitive match on unit id or name.")


class GetGeoUnitsResponsePayload(BaseModel):
    version: GeoVersionInfo
    units: List[GeoUnit] = []
    total: int = 0


class GetGeoUnitPayload(VersionSelector):
    unit_id: str


class GetGeoUnitResponsePayload(BaseModel):
    version: GeoVersionInfo
    unit: GeoUnit
    ancestors: List[GeoUnit] = Field(default_factory=list, description="Parent first, up to the root.")


class GetGeoChangesPayload(BaseModel):
    from_version: Optional[int] = Field(default=None, description="Exclusive. Defaults to 0.")
    to_version: Optional[VersionRef] = Field(default=None, description='Inclusive. Defaults to "latest".')
    unit_id: Optional[str] = Field(default=None, description="Only events naming this unit.")
    include_draft: bool = Field(default=False, description="Also return events of the open draft.")


class GetGeoChangesResponsePayload(BaseModel):
    changes: List[GeoChange] = []


class GetGeoCrosswalkPayload(BaseModel):
    unit_id: str
    from_version: int
    to_version: Optional[VersionRef] = Field(default=None, description='Defaults to "latest".')


class CrosswalkStep(BaseModel):
    version_no: int
    change_id: int
    change_type: str
    from_units: List[str]
    to_units: List[str]


class GetGeoCrosswalkResponsePayload(BaseModel):
    unit_id: str
    from_version: int
    to_version: int
    direction: Literal["forward", "backward", "none"]
    unchanged: bool
    units: List[GeoUnit] = Field(
        default_factory=list,
        description="The unit's successors in to_version (predecessors when going backward).",
    )
    unmapped: List[str] = Field(
        default_factory=list,
        description="Units that end without a successor (forward: retired) or start without a predecessor "
        "(backward: created).",
    )
    path: List[CrosswalkStep] = []


class GetGeoBoundaryPayload(VersionSelector):
    level: str = Field(..., description="Level mnemonic (or id).")
    stream: bool = Field(default=False, description="Return the GeoJSON itself (application/geo+json).")


class GetGeoBoundaryResponsePayload(BaseModel):
    version_no: int
    level: str
    object_key: Optional[str] = None
    url: Optional[str] = None
    presigned_url: Optional[str] = None


class CreateGeoDraftPayload(BaseModel):
    base_version: Optional[int] = None
    copy_from_version: Optional[int] = None
    change_note: Optional[str] = None
    effective_from: Optional[datetime] = None
    owner_org: Optional[str] = None


class UpdateGeoDraftPayload(BaseModel):
    change_note: Optional[str] = None
    effective_from: Optional[datetime] = None
    owner_org: Optional[str] = None


class GeoDraftResponsePayload(BaseModel):
    draft: GeoVersionInfo


class DraftLevelInput(BaseModel):
    level_id: str
    level_mnemonic: str
    parent_level_id: Optional[str] = None
    display: Optional[str] = None
    display_i18n: Optional[Dict[str, str]] = None


class UpsertDraftLevelsPayload(BaseModel):
    levels: List[DraftLevelInput]


class UpsertDraftLevelsResponsePayload(BaseModel):
    draft: GeoVersionInfo
    levels: List[GeoLevel] = []


class DraftUnitInput(BaseModel):
    unit_id: str
    level_id: str
    name: str
    name_i18n: Optional[Dict[str, str]] = None
    parent_unit_id: Optional[str] = None
    status: Optional[Literal["ACTIVE", "RETIRED"]] = None


class UpsertDraftUnitsPayload(BaseModel):
    units: List[DraftUnitInput]


class UpsertDraftUnitsResponsePayload(BaseModel):
    draft: GeoVersionInfo
    units: List[GeoUnit] = []


class RetireDraftUnitsPayload(BaseModel):
    unit_ids: List[str]
    cascade: bool = Field(default=False, description="Also retire active descendants.")


class RetireDraftUnitsResponsePayload(BaseModel):
    draft: GeoVersionInfo
    retired: List[str] = []
    removed: List[str] = []


class RecordGeoChangePayload(BaseModel):
    change_type: Literal[
        "CREATE", "RETIRE", "RENAME", "RECODE", "SPLIT", "MERGE", "REPARENT", "BOUNDARY_CHANGE"
    ]
    from_units: List[str] = []
    to_units: List[str] = []
    effective_date: Optional[date] = Field(
        default=None, description="Defaults to the version's effective date."
    )
    note: Optional[str] = None


class RecordGeoChangeResponsePayload(BaseModel):
    draft: GeoVersionInfo
    change: GeoChange


class DeleteGeoChangePayload(BaseModel):
    change_id: int


class DeleteGeoChangeResponsePayload(BaseModel):
    change_id: int


class UploadDraftBoundaryPayload(BaseModel):
    level: str = Field(..., description="Level mnemonic (or id) of the open draft.")
    geojson: Dict[str, Any] = Field(..., description="A GeoJSON FeatureCollection for that level.")


class UploadDraftBoundaryResponsePayload(BaseModel):
    draft: GeoVersionInfo
    level: str
    object_key: str
    features: int


class SubmitGeoDraftPayload(BaseModel):
    change_note: Optional[str] = None
    effective_from: Optional[datetime] = None


class DecideGeoDraftPayload(BaseModel):
    version_no: Optional[int] = None
    decision_note: Optional[str] = None
    effective_from: Optional[datetime] = None


class DiscardGeoDraftResponsePayload(BaseModel):
    discarded_version_no: int


# ---------------------------------------------------------------------------
# Releases
# ---------------------------------------------------------------------------


class ReleaseMember(BaseModel):
    list_id: Optional[str] = None
    list_code: str
    version_no: int


class ReleaseInfo(BaseModel):
    release_code: str
    title: Optional[str] = None
    note: Optional[str] = None
    status: str
    geo_version_no: Optional[int] = None
    # *_by: stable user id (token sub); *_by_name: display name (None for a system actor).
    created_by: Optional[str] = None
    created_by_name: Optional[str] = None
    created_at: Optional[datetime] = None
    members_set_by: Optional[str] = None
    members_set_by_name: Optional[str] = None
    members_set_at: Optional[datetime] = None
    published_by: Optional[str] = None
    published_by_name: Optional[str] = None
    published_at: Optional[datetime] = None
    member_count: int = 0


class GetReleasesResponsePayload(BaseModel):
    releases: List[ReleaseInfo] = []


class ReleaseRef(BaseModel):
    release_code: str


class GetReleaseResponsePayload(BaseModel):
    release: ReleaseInfo
    members: List[ReleaseMember] = []


class CreateReleasePayload(BaseModel):
    release_code: str
    title: Optional[str] = None
    note: Optional[str] = None


class ReleaseMemberInput(BaseModel):
    list_code: str
    version_no: int


class SetReleaseMembersPayload(BaseModel):
    release_code: str
    members: List[ReleaseMemberInput] = []
    geo_version_no: Optional[int] = None
    replace: bool = Field(
        default=True, description="Replace all members (true) or add/overwrite these (false)."
    )


class DeleteReleaseResponsePayload(BaseModel):
    release_code: str


# ---------------------------------------------------------------------------
# Change feed and config
# ---------------------------------------------------------------------------


class GetChangesPayload(BaseModel):
    cursor: int = Field(default=0, ge=0, description="Return events with event_id greater than this.")
    limit: int = Field(default=100, ge=1, le=1000)
    subject_type: Optional[Literal["list", "geo", "release"]] = None
    subject_id: Optional[str] = Field(default=None, description="List id, 'geography' or a release code.")
    event_types: Optional[List[str]] = None
    newest: bool = Field(
        default=False,
        description="Return the newest `limit` matching events (after `cursor`), still oldest first, "
        "instead of the first `limit`; `next_cursor` is the last event's id. For a recent-activity view.",
    )


class ChangeEvent(BaseModel):
    event_id: int
    event_type: str
    subject_type: str
    subject_id: Optional[str] = None
    version_no: Optional[int] = None
    # Stable user id (token sub) or a system name; actor_name is a user's display name.
    actor: Optional[str] = None
    actor_name: Optional[str] = None
    at: datetime
    details: Optional[Dict[str, Any]] = None


class GetChangesResponsePayload(BaseModel):
    events: List[ChangeEvent] = []
    next_cursor: int
    has_more: bool = False


class CatalogueConfigResponsePayload(BaseModel):
    approval_mode: Literal["permission", "awe"]
    boundary_store_enabled: bool
    audit_enabled: bool
    websub_enabled: bool
    country: Optional[str] = None
    geo_current_version_no: Optional[int] = None


class AweWebhookEvent(BaseModel):
    """Body AWE POSTs to the callback (awe.schemas.callback.WebhookEvent)."""

    event_id: str
    event_type: str
    request_id: str
    artifact_type: str
    artifact_id: str
    status: str
    stage_order: Optional[int] = None
    actor: Optional[str] = None
    occurred_at: datetime


class AweWebhookResponse(BaseModel):
    event_id: str
    applied: bool
    message: str = "ok"
