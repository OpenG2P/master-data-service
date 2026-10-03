# NOTE: no `from __future__ import annotations` here — endpoint signatures are
# built at runtime from the request models and must stay real types for FastAPI.
import logging
from datetime import datetime
from typing import Any, Awaitable, Callable, Iterable, Optional, Type

from fastapi import Request
from fastapi.responses import Response
from iam_core.user_auth.decorators import data_policy as data_policy_marker
from iam_core.user_auth.decorators import require_permissions
from openg2p_fastapi_common.controller import BaseController
from openg2p_fastapi_common.schemas import (
    G2PPaginationResponse,
    G2PResponseHeader,
    G2PResponseStatus,
)
from pydantic import BaseModel

from ..config import Settings
from ..helpers.catalogue_integrations import AweWebhookSignatureError, BoundaryStore, approval_mode
from ..helpers.data_policy_request_helper import get_data_policies
from ..schemas.g2p_catalogue import (
    AweWebhookResponse,
    CatalogueConfigResponsePayload,
    CatalogueRequest,
    CatalogueResponse,
    CatalogueResponseBody,
    CreateGeoDraftPayload,
    CreateListDraftPayload,
    CreateListPayload,
    CreateReleasePayload,
    DecideDraftPayload,
    DecideGeoDraftPayload,
    DeleteGeoChangePayload,
    DeleteGeoChangeResponsePayload,
    DeleteReleaseResponsePayload,
    DiscardDraftResponsePayload,
    DiscardGeoDraftResponsePayload,
    DraftResponsePayload,
    EmptyPayload,
    GeoDraftResponsePayload,
    GetChangesPayload,
    GetChangesResponsePayload,
    GetGeoBoundaryPayload,
    GetGeoBoundaryResponsePayload,
    GetGeoChangesPayload,
    GetGeoChangesResponsePayload,
    GetGeoCrosswalkPayload,
    GetGeoCrosswalkResponsePayload,
    GetGeoLevelsPayload,
    GetGeoLevelsResponsePayload,
    GetGeoUnitPayload,
    GetGeoUnitResponsePayload,
    GetGeoUnitsPayload,
    GetGeoUnitsResponsePayload,
    GetGeoVersionsResponsePayload,
    GetListDiffPayload,
    GetListDiffResponsePayload,
    GetListPayload,
    GetListResponsePayload,
    GetListsPayload,
    GetListsResponsePayload,
    GetListValuePayload,
    GetListValueResponsePayload,
    GetListValuesPayload,
    GetListValuesResponsePayload,
    GetListVersionsResponsePayload,
    GetReleaseResponsePayload,
    GetReleasesResponsePayload,
    ListAndDraftResponsePayload,
    ListRef,
    RecordGeoChangePayload,
    RecordGeoChangeResponsePayload,
    ReleaseRef,
    RetireDraftUnitsPayload,
    RetireDraftUnitsResponsePayload,
    RetireDraftValuesPayload,
    RetireDraftValuesResponsePayload,
    SetReleaseMembersPayload,
    SubmitDraftPayload,
    SubmitGeoDraftPayload,
    UpdateGeoDraftPayload,
    UpdateListDraftPayload,
    UpdateListPayload,
    UploadDraftBoundaryPayload,
    UploadDraftBoundaryResponsePayload,
    UpsertDraftLevelsPayload,
    UpsertDraftLevelsResponsePayload,
    UpsertDraftUnitsPayload,
    UpsertDraftUnitsResponsePayload,
    UpsertDraftValuesPayload,
    UpsertDraftValuesResponsePayload,
    VersionSelector,
)
from ..services import (
    G2PCatalogueAweCallbackService,
    G2PCatalogueFeedService,
    G2PCatalogueGeoService,
    G2PCatalogueListService,
    G2PCatalogueReleaseService,
)
from ..services.catalogue_common import CatalogueError, actor_from_request

_config = Settings.get_config()
_logger = logging.getLogger(_config.logging_default_logger_name)

READ = frozenset()
TAG_LISTS = "/catalogue — lists"
TAG_GEO = "/catalogue — geography"
TAG_RELEASES = "/catalogue — releases"
TAG_FEED = "/catalogue — change feed"

_VERSIONING = (
    '\n\nVersion selection: `version` (number, `"latest"` — the default, the latest published version '
    'already in effect — or `"draft"`), `as_of` (date-time: the published version in effect then) or '
    "`release` (a catalogue release code). The response's `version` object says which version answered."
)
_DRAFT = (
    "\n\nEdits only ever touch the open DRAFT (one per list / for geography); a draft is created from the "
    "highest published version when none is open. Published versions are immutable (enforced in Postgres)."
)


def _sel(payload: BaseModel) -> VersionSelector:
    return VersionSelector(
        version=getattr(payload, "version", None),
        as_of=getattr(payload, "as_of", None),
        release=getattr(payload, "release", None),
    )


def _page(body) -> tuple[int, int]:
    p = body.request_body.pagination_request
    return (p.page_size, p.current_page) if p else (1000, 1)


class G2PCatalogueController(BaseController):
    """Master Data as a catalogue: versioned, approved, pinnable reference data.

    Reads need an authenticated caller (like the existing reads). Writes need
    referenceData:create|edit|delete (lists, releases) or geo:create|edit|delete
    (geography); approving needs referenceData:publish / geo:publish and a
    different person from the draft's maker (permission mode), or runs through
    AWE (awe mode). People are identified by the token's ``sub`` (stable user
    id), never by display name — see catalogue_common.Actor.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.router.prefix = "/catalogue"
        self.router.tags += ["/catalogue"]
        self.lists = G2PCatalogueListService.get_component()
        self.geo = G2PCatalogueGeoService.get_component()
        self.releases = G2PCatalogueReleaseService.get_component()
        self.feed = G2PCatalogueFeedService.get_component()
        self.awe = G2PCatalogueAweCallbackService.get_component()
        self._register_lists()
        self._register_geo()
        self._register_releases()
        self._register_feed()
        self.router.add_api_route(
            "/awe/callback",
            self.awe_callback,
            methods=["POST"],
            response_model=AweWebhookResponse,
            tags=[TAG_LISTS, TAG_GEO],
            summary="AWE decision callback",
            description=(
                "Called by the Approval Workflow Engine (awe mode). Authenticated by HMAC, not JWT: "
                '`X-Approval-Signature: sha256=HMAC_SHA256(secret, "<X-Approval-Timestamp>." + body)`, '
                "with `X-Approval-Timestamp` (unix seconds) and `X-Approval-Event-Id`. Body: AWE WebhookEvent "
                "(`event_id, event_type, request_id, artifact_type, artifact_id, status, stage_order, actor, "
                "occurred_at`). `request_approved` publishes the submitted version "
                "(artifact `master_data.list_version` `<list_id>:<version_no>`, or `master_data.geo_version` "
                "`geography:<version_no>`); `request_rejected` / `request_cancelled` reject it. Idempotent on "
                "event_id. 401 on a bad signature, 422 when the event cannot be applied."
            ),
        )

    # ------------------------------------------------------------------
    # Envelope plumbing
    # ------------------------------------------------------------------

    @staticmethod
    def _header(req, status: G2PResponseStatus, code: str = "", message: str = "") -> G2PResponseHeader:
        request_id = req.request_header.request_id if req is not None and req.request_header else ""
        return G2PResponseHeader(
            request_id=request_id,
            response_status=status,
            response_error_code=code,
            response_error_message=message,
            response_timestamp=datetime.now(),
        )

    def _route(
        self,
        path: str,
        payload_model: Type[BaseModel],
        result_model: Type[BaseModel],
        handler: Callable[[Request, Any, Any], Awaitable[Any]],
        *,
        permissions: Iterable[str],
        tag: str,
        summary: str,
        description: str,
        data_policy: bool = False,
        extra_responses: Optional[dict] = None,
    ) -> None:
        request_model = CatalogueRequest[payload_model]
        response_model = CatalogueResponse[result_model]
        body_model = CatalogueResponseBody[result_model]
        header = self._header

        async def endpoint(http_request: Request, catalogue_request: request_model):
            try:
                payload = catalogue_request.request_body.request_payload
                result = await handler(http_request, catalogue_request, payload)
                if isinstance(result, Response):
                    return result
                pagination = None
                if isinstance(result, tuple):
                    result, pagination = result
                return response_model(
                    response_header=header(catalogue_request, G2PResponseStatus.SUCCESS),
                    response_body=body_model(response_payload=result, pagination_response=pagination),
                )
            except Exception as exc:  # noqa: BLE001 — every error goes back in the envelope
                if isinstance(exc, CatalogueError):
                    _logger.info("%s: %s %s", path, exc.code, exc.message)
                    code, message = exc.code, exc.message
                elif hasattr(exc, "code") and hasattr(exc, "message"):
                    code, message = str(exc.code), exc.message
                else:
                    _logger.error("%s failed: %s", path, exc, exc_info=True)
                    code, message = "G2P-CAT-500", str(exc)
                return response_model(
                    response_header=header(catalogue_request, G2PResponseStatus.ERROR, code, message),
                    response_body=body_model(response_payload=None),
                )

        endpoint.__name__ = path.strip("/").replace("/", "_")
        endpoint.__qualname__ = f"G2PCatalogueController.{endpoint.__name__}"
        require_permissions(set(permissions))(endpoint)
        if data_policy:
            data_policy_marker(endpoint)
        responses = {200: {"model": response_model}}
        if extra_responses:
            responses.update(extra_responses)
        self.router.add_api_route(
            path,
            endpoint,
            methods=["POST"],
            responses=responses,
            tags=[tag],
            summary=summary,
            description=description,
        )

    # ------------------------------------------------------------------
    # Lists
    # ------------------------------------------------------------------

    def _register_lists(self) -> None:
        L = self.lists
        r = self._route

        async def get_lists(req, body, p):
            return GetListsResponsePayload(lists=await L.get_lists(p.include_unpublished))

        r(
            "/get_lists",
            GetListsPayload,
            GetListsResponsePayload,
            get_lists,
            permissions=READ,
            tag=TAG_LISTS,
            summary="All code lists",
            description=(
                "Every code list with its owner, current published version (in effect now), highest published "
                "version (may be future-effective), open draft (number and status) and a summary of its "
                "attribute schema (properties, required, list references)."
            ),
        )

        async def get_list(req, body, p):
            summary, version = await L.get_list(p.list_code, _sel(p))
            return GetListResponsePayload(list=summary, version=version)

        r(
            "/get_list",
            GetListPayload,
            GetListResponsePayload,
            get_list,
            permissions=READ,
            tag=TAG_LISTS,
            summary="One code list at a version",
            description="A list's metadata as it is in the selected version (code, labels, attribute schema), "
            "plus that version's metadata." + _VERSIONING,
        )

        async def get_list_values(req, body, p):
            size, page = _page(body)
            code, version, values, total = await L.get_list_values(
                p.list_code,
                _sel(p),
                include_retired=p.include_retired,
                parent_code=p.parent_code,
                attribute_filters=p.attribute_filters,
                search=p.search,
                page_size=size,
                page_number=page,
                data_policies=get_data_policies(req),
            )
            pages = (total + size - 1) // size if total else 0
            return (
                GetListValuesResponsePayload(list_code=code, version=version, values=values, total=total),
                G2PPaginationResponse(number_of_items=total, number_of_pages=pages),
            )

        r(
            "/get_list_values",
            GetListValuesPayload,
            GetListValuesResponsePayload,
            get_list_values,
            permissions=READ,
            tag=TAG_LISTS,
            data_policy=True,
            summary="Values of a list at a version",
            description=(
                "Values of the selected version, ordered by sort_order. Active values only unless "
                '`include_retired`. Filters: `parent_code` ("" = top level), `attribute_filters` (JSON '
                "containment on the typed attributes), `search` (code or label). Paged with "
                "`pagination_request`. ATTRIBUTE data policies apply as on /attributes/get_attribute_values. "
                "Response: `{list_code, version: {version_no, status, effective_from, published_at, is_latest, "
                "...}, values: [{value_id, value_code, display, display_i18n, parent_code, sort_order, "
                "attributes, roles, status}], total}`." + _VERSIONING
            ),
        )

        async def get_list_value(req, body, p):
            code, version, value = await L.get_list_value(p.list_code, p.value_code, _sel(p))
            return GetListValueResponsePayload(list_code=code, version=version, value=value)

        r(
            "/get_list_value",
            GetListValuePayload,
            GetListValueResponsePayload,
            get_list_value,
            permissions=READ,
            tag=TAG_LISTS,
            summary="One value by code at a version",
            description="Resolves a code in the selected version — including a RETIRED value, so an old "
            "reference still resolves against the version it was taken from." + _VERSIONING,
        )

        async def get_list_versions(req, body, p):
            code, versions = await L.get_list_versions(p.list_code)
            return GetListVersionsResponsePayload(list_code=code, versions=versions)

        r(
            "/get_list_versions",
            ListRef,
            GetListVersionsResponsePayload,
            get_list_versions,
            permissions=READ,
            tag=TAG_LISTS,
            summary="Version history of a list",
            description="All versions, newest first: DRAFT, SUBMITTED, PUBLISHED (with effective_from, "
            "published_at, decided_by), REJECTED (with decision_note) and DISCARDED. Numbers are never reused. "
            "`is_latest` marks the version in "
            "effect now. `*_by` fields hold stable user ids (token `sub`) or a system name; `*_by_name` the "
            "user's display name (null for a system actor).",
        )

        async def get_list_diff(req, body, p):
            return GetListDiffResponsePayload(
                **await L.get_list_diff(p.list_code, p.from_version, p.to_version)
            )

        r(
            "/get_list_diff",
            GetListDiffPayload,
            GetListDiffResponsePayload,
            get_list_diff,
            permissions=READ,
            tag=TAG_LISTS,
            summary="Differences between two versions",
            description=(
                "`added`, `changed` (per field before/after), `retired` and `reactivated` values, and "
                "`metadata_changes` (code, label, labels, hierarchy flag, attribute schema) from "
                '`from_version` (default: the base of `to_version`) to `to_version` (number, "latest" or '
                '"draft"; default "latest"). Use `to_version: "draft"` to review a draft.'
            ),
        )

        async def create_list(req, body, p):
            summary, draft = await L.create_list(p, actor_from_request(req))
            return ListAndDraftResponsePayload(list=summary, draft=draft)

        r(
            "/create_list",
            CreateListPayload,
            ListAndDraftResponsePayload,
            create_list,
            permissions={"referenceData:create"},
            tag=TAG_LISTS,
            summary="Create a code list",
            description="Registers a new list (code, label, labels per locale, description, owner_org, "
            "hierarchy flag, attribute_schema) and opens its first draft (version 1). Nothing is published "
            "until that draft is submitted and approved. `attribute_schema` is a JSON Schema (2020-12) for "
            'each value\'s `attributes`; a property may carry `"x-list-ref": "<LIST_CODE>"`.',
        )

        async def update_list(req, body, p):
            summary, draft = await L.update_list(p, actor_from_request(req))
            return ListAndDraftResponsePayload(list=summary, draft=draft)

        r(
            "/update_list",
            UpdateListPayload,
            ListAndDraftResponsePayload,
            update_list,
            permissions={"referenceData:edit"},
            tag=TAG_LISTS,
            summary="Update a list's metadata",
            description="`description` and `owner_org` are administrative and apply at once. `new_list_code`, "
            "`display`, `display_i18n`, `is_hierarchical` and `attribute_schema` are part of what consumers "
            "see, so they go into the open draft." + _DRAFT,
        )

        async def create_list_draft(req, body, p):
            code, draft = await L.create_list_draft(p, actor_from_request(req))
            return DraftResponsePayload(list_code=code, draft=draft)

        r(
            "/create_list_draft",
            CreateListDraftPayload,
            DraftResponsePayload,
            create_list_draft,
            permissions={"referenceData:edit"},
            tag=TAG_LISTS,
            summary="Open a draft",
            description="Opens the list's draft as a copy of the highest published version (its base). "
            "`copy_from_version` copies another version's content instead (e.g. a REJECTED draft to rework). "
            "Optional `change_note` and `effective_from` (may be in the future). 409 if a draft is open.",
        )

        async def update_list_draft(req, body, p):
            code, draft = await L.update_list_draft(p, actor_from_request(req))
            return DraftResponsePayload(list_code=code, draft=draft)

        r(
            "/update_list_draft",
            UpdateListDraftPayload,
            DraftResponsePayload,
            update_list_draft,
            permissions={"referenceData:edit"},
            tag=TAG_LISTS,
            summary="Set a draft's change note / effective date",
            description="`effective_from` may not be earlier than the latest published version's.",
        )

        async def upsert_draft_values(req, body, p):
            code, draft, values = await L.upsert_draft_values(p.list_code, p.values, actor_from_request(req))
            return UpsertDraftValuesResponsePayload(list_code=code, draft=draft, values=values)

        r(
            "/upsert_draft_values",
            UpsertDraftValuesPayload,
            UpsertDraftValuesResponsePayload,
            upsert_draft_values,
            permissions={"referenceData:edit"},
            tag=TAG_LISTS,
            summary="Add or change values in the draft (batch)",
            description="Each item is matched on `value_id` when given (which lets a value change its code), "
            "else on `value_code`; unmatched items are added. Only fields present are changed. Upserting a "
            "retired code re-activates it. `attributes` are validated against the draft's attribute_schema, "
            "and `x-list-ref` codes must be ACTIVE values of the referenced list's version in effect (now, or "
            "at the draft's future effective_from) — never its draft: publish a referenced list first."
            + _DRAFT,
        )

        async def retire_draft_values(req, body, p):
            code, draft, retired, removed = await L.retire_draft_values(
                p.list_code, p.value_codes, p.cascade, actor_from_request(req)
            )
            return RetireDraftValuesResponsePayload(
                list_code=code, draft=draft, retired=retired, removed=removed
            )

        r(
            "/retire_draft_values",
            RetireDraftValuesPayload,
            RetireDraftValuesResponsePayload,
            retire_draft_values,
            permissions={"referenceData:delete"},
            tag=TAG_LISTS,
            summary="Retire values in the draft",
            description="A value that exists in the base version becomes RETIRED (kept, so old references "
            "still resolve); a value added in this draft is removed. Active children block unless "
            "`cascade`." + _DRAFT,
        )

        async def discard_draft(req, body, p):
            code, no = await L.discard_draft(p.list_code, actor_from_request(req))
            return DiscardDraftResponsePayload(list_code=code, discarded_version_no=no)

        r(
            "/discard_draft",
            ListRef,
            DiscardDraftResponsePayload,
            discard_draft,
            permissions={"referenceData:edit"},
            tag=TAG_LISTS,
            summary="Discard the open draft",
            description="Closes the open draft (DRAFT, or SUBMITTED in permission mode) as DISCARDED. The "
            "version row is kept so its number is never reused; the next draft gets the next number. "
            "Published versions are untouched.",
        )

        async def submit_draft(req, body, p):
            code, draft = await L.submit_draft(p, actor_from_request(req))
            return DraftResponsePayload(list_code=code, draft=draft)

        r(
            "/submit_draft",
            SubmitDraftPayload,
            DraftResponsePayload,
            submit_draft,
            permissions={"referenceData:edit"},
            tag=TAG_LISTS,
            summary="Submit the draft for approval",
            description="Validates the draft (labels, hierarchy, attribute schema and every value's typed "
            "attributes incl. list references; must differ from its base) and moves it to SUBMITTED. In awe "
            "mode this also opens an AWE approval request (policy `awe_policy_key_list`, artifact "
            "`master_data.list_version`, context incl. owner_org) and records its id in `approval_ref`.",
        )

        async def approve_draft(req, body, p):
            code, version = await L.approve_draft(p, actor_from_request(req))
            return DraftResponsePayload(list_code=code, draft=version)

        r(
            "/approve_draft",
            DecideDraftPayload,
            DraftResponsePayload,
            approve_draft,
            permissions={"referenceData:publish"},
            tag=TAG_LISTS,
            summary="Approve and publish (permission mode)",
            description="Publishes the SUBMITTED version: it becomes immutable, `effective_from` defaults to "
            "now (or the draft's / this call's date, possibly future), and — if in effect — the legacy "
            "/attributes tables are refreshed in the same transaction. Maker ≠ checker: the approver must "
            "not have created, edited or submitted the draft (G2P-CAT-403). Disabled in awe mode.",
        )

        async def reject_draft(req, body, p):
            code, version = await L.reject_draft(p, actor_from_request(req))
            return DraftResponsePayload(list_code=code, draft=version)

        r(
            "/reject_draft",
            DecideDraftPayload,
            DraftResponsePayload,
            reject_draft,
            permissions={"referenceData:publish"},
            tag=TAG_LISTS,
            summary="Reject the submitted draft (permission mode)",
            description="Marks the SUBMITTED version REJECTED with a required `decision_note`. Maker ≠ checker. "
            "Rework it with create_list_draft + copy_from_version.",
        )

    # ------------------------------------------------------------------
    # Geography
    # ------------------------------------------------------------------

    def _register_geo(self) -> None:
        G = self.geo
        r = self._route

        async def get_geo_versions(req, body, p):
            return GetGeoVersionsResponsePayload(versions=await G.get_geo_versions())

        r(
            "/get_geo_versions",
            EmptyPayload,
            GetGeoVersionsResponsePayload,
            get_geo_versions,
            permissions=READ,
            tag=TAG_GEO,
            summary="Geography version history",
            description="All geography versions, newest first, with status, effective_from, owner_org, "
            "country, active unit count and the boundary object key per level.",
        )

        async def get_geo_levels(req, body, p):
            version, levels = await G.get_geo_levels(_sel(p))
            return GetGeoLevelsResponsePayload(version=version, levels=levels)

        r(
            "/get_geo_levels",
            GetGeoLevelsPayload,
            GetGeoLevelsResponsePayload,
            get_geo_levels,
            permissions=READ,
            tag=TAG_GEO,
            summary="Levels of a geography version",
            description="Levels top-down (level_id, level_mnemonic, parent_level_id, display, display_i18n)."
            + _VERSIONING,
        )

        async def get_geo_units(req, body, p):
            size, page = _page(body)
            version, units, total = await G.get_geo_units(
                _sel(p),
                level=p.level,
                parent_unit_id=p.parent_unit_id,
                include_retired=p.include_retired,
                search=p.search,
                page_size=size,
                page_number=page,
                data_policies=get_data_policies(req),
            )
            pages = (total + size - 1) // size if total else 0
            return (
                GetGeoUnitsResponsePayload(version=version, units=units, total=total),
                G2PPaginationResponse(number_of_items=total, number_of_pages=pages),
            )

        r(
            "/get_geo_units",
            GetGeoUnitsPayload,
            GetGeoUnitsResponsePayload,
            get_geo_units,
            permissions=READ,
            tag=TAG_GEO,
            data_policy=True,
            summary="Units of a geography version",
            description="Units (unit_id = P-code, level_id, name, name_i18n, parent_unit_id, status, "
            'valid_from, valid_to), filtered by `level` (id or mnemonic), `parent_unit_id` ("" = roots), '
            "`search`; active only unless `include_retired`. Paged. GEO data policies apply." + _VERSIONING,
        )

        async def get_geo_unit(req, body, p):
            version, unit, ancestors = await G.get_geo_unit(p.unit_id, _sel(p))
            return GetGeoUnitResponsePayload(version=version, unit=unit, ancestors=ancestors)

        r(
            "/get_geo_unit",
            GetGeoUnitPayload,
            GetGeoUnitResponsePayload,
            get_geo_unit,
            permissions=READ,
            tag=TAG_GEO,
            summary="One unit, with its ancestors",
            description="A unit of the selected version (retired ones too) and its ancestor chain."
            + _VERSIONING,
        )

        async def get_geo_changes(req, body, p):
            changes = await G.get_geo_changes(p.from_version, p.to_version, p.unit_id, p.include_draft)
            return GetGeoChangesResponsePayload(changes=changes)

        r(
            "/get_geo_changes",
            GetGeoChangesPayload,
            GetGeoChangesResponsePayload,
            get_geo_changes,
            permissions=READ,
            tag=TAG_GEO,
            summary="Change events (lineage) between versions",
            description="Events of the published versions in (`from_version`, `to_version`] — CREATE, RETIRE, "
            "RENAME, RECODE, SPLIT, MERGE, REPARENT, BOUNDARY_CHANGE with from_units (base version) and "
            "to_units (new version), effective_date, note, is_auto. `unit_id` filters to events naming it; "
            "`include_draft` adds the open draft's events.",
        )

        async def get_geo_crosswalk(req, body, p):
            return GetGeoCrosswalkResponsePayload(
                **await G.get_geo_crosswalk(p.unit_id, p.from_version, p.to_version)
            )

        r(
            "/get_geo_crosswalk",
            GetGeoCrosswalkPayload,
            GetGeoCrosswalkResponsePayload,
            get_geo_crosswalk,
            permissions=READ,
            tag=TAG_GEO,
            summary="Map a unit across versions",
            description="Follows the change events from `from_version` to `to_version` (default latest; may be "
            "earlier, to find predecessors) across any number of versions. Returns the unit's successors "
            "(SPLIT gives several, MERGE one, RECODE the new code; RENAME/REPARENT/BOUNDARY_CHANGE keep the "
            "unit) as they are in `to_version`, `unmapped` units (retired without successor / created without "
            "predecessor) and the `path` of events taken.",
        )

        async def get_geo_boundary(req, body, p):
            if p.stream:
                data = await G.read_boundary(_sel(p), p.level)
                return Response(content=data, media_type="application/geo+json")
            return GetGeoBoundaryResponsePayload(**await G.get_geo_boundary(_sel(p), p.level))

        r(
            "/get_geo_boundary",
            GetGeoBoundaryPayload,
            GetGeoBoundaryResponsePayload,
            get_geo_boundary,
            permissions=READ,
            tag=TAG_GEO,
            summary="Boundary GeoJSON of a level",
            description="The object key of the level's boundary in the selected version "
            "(`geo/<country>/v<version>/<level>.geojson`, immutable once published; an unchanged level points "
            "at an earlier version's object), with `url` (when a public base URL is configured) and a "
            "`presigned_url`. With `stream: true` the GeoJSON itself is returned as application/geo+json."
            + _VERSIONING,
            extra_responses={200: {"content": {"application/geo+json": {}}}},
        )

        async def create_geo_draft(req, body, p):
            return GeoDraftResponsePayload(draft=await G.create_geo_draft(p, actor_from_request(req)))

        r(
            "/create_geo_draft",
            CreateGeoDraftPayload,
            GeoDraftResponsePayload,
            create_geo_draft,
            permissions={"geo:edit"},
            tag=TAG_GEO,
            summary="Open a geography draft",
            description="Copies levels, units and boundary keys of the highest published version (or "
            "`copy_from_version`). Optional `change_note`, `effective_from` (e.g. new woredas from 2027-01-01), "
            "`owner_org`.",
        )

        async def update_geo_draft(req, body, p):
            return GeoDraftResponsePayload(draft=await G.update_geo_draft(p, actor_from_request(req)))

        r(
            "/update_geo_draft",
            UpdateGeoDraftPayload,
            GeoDraftResponsePayload,
            update_geo_draft,
            permissions={"geo:edit"},
            tag=TAG_GEO,
            summary="Set the geography draft's note / effective date / owner",
            description="Only fields present are changed.",
        )

        async def upsert_draft_levels(req, body, p):
            draft, levels = await G.upsert_draft_levels(p.levels, actor_from_request(req))
            return UpsertDraftLevelsResponsePayload(draft=draft, levels=levels)

        r(
            "/upsert_draft_levels",
            UpsertDraftLevelsPayload,
            UpsertDraftLevelsResponsePayload,
            upsert_draft_levels,
            permissions={"geo:edit"},
            tag=TAG_GEO,
            summary="Add or change levels in the geography draft",
            description="Matched on level_id. Mnemonics must be unique under the same parent level." + _DRAFT,
        )

        async def upsert_draft_units(req, body, p):
            draft, units = await G.upsert_draft_units(p.units, actor_from_request(req))
            return UpsertDraftUnitsResponsePayload(draft=draft, units=units)

        r(
            "/upsert_draft_units",
            UpsertDraftUnitsPayload,
            UpsertDraftUnitsResponsePayload,
            upsert_draft_units,
            permissions={"geo:edit"},
            tag=TAG_GEO,
            summary="Add or change units in the geography draft (batch)",
            description="Matched on unit_id (P-code). A unit's parent must be an active unit of the parent level; "
            "names are unique among siblings. Upserting a retired unit re-activates it. Renames, re-parenting "
            "and new units get change events automatically at submit unless you record them." + _DRAFT,
        )

        async def retire_draft_units(req, body, p):
            draft, retired, removed = await G.retire_draft_units(
                p.unit_ids, p.cascade, actor_from_request(req)
            )
            return RetireDraftUnitsResponsePayload(draft=draft, retired=retired, removed=removed)

        r(
            "/retire_draft_units",
            RetireDraftUnitsPayload,
            RetireDraftUnitsResponsePayload,
            retire_draft_units,
            permissions={"geo:delete"},
            tag=TAG_GEO,
            summary="Retire units in the geography draft",
            description="Units of the base version become RETIRED (never deleted); units added in this draft are "
            "removed. Active descendants block unless `cascade`." + _DRAFT,
        )

        async def record_geo_change(req, body, p):
            draft, change = await G.record_geo_change(p, actor_from_request(req))
            return RecordGeoChangeResponsePayload(draft=draft, change=change)

        r(
            "/record_geo_change",
            RecordGeoChangePayload,
            RecordGeoChangeResponsePayload,
            record_geo_change,
            permissions={"geo:edit"},
            tag=TAG_GEO,
            summary="Record a change event in the geography draft",
            description=(
                "Lineage against the draft's base version. Rules: CREATE — to-units active in the draft and new; "
                "RETIRE — from-units active in base, retired in the draft; RENAME / REPARENT — one unit, same id, "
                "name / parent differs; RECODE — one old code (retired) to one new code (new), same level; SPLIT "
                "— one from-unit (retired, or kept as one of the parts) to ≥2 active to-units; MERGE — ≥2 "
                "from-units (retired, or the survivor) to one active unit; BOUNDARY_CHANGE — units active in both. "
                "A unit can end in only one RETIRE/SPLIT/MERGE/RECODE per version. Edit the units first, then "
                "record the event."
            ),
        )

        async def delete_geo_change(req, body, p):
            return DeleteGeoChangeResponsePayload(
                change_id=await G.delete_geo_change(p.change_id, actor_from_request(req))
            )

        r(
            "/delete_geo_change",
            DeleteGeoChangePayload,
            DeleteGeoChangeResponsePayload,
            delete_geo_change,
            permissions={"geo:edit"},
            tag=TAG_GEO,
            summary="Remove a change event from the geography draft",
            description="Only events of the open DRAFT.",
        )

        async def upload_draft_boundary(req, body, p):
            return UploadDraftBoundaryResponsePayload(
                **await G.upload_draft_boundary(p.level, p.geojson, actor_from_request(req))
            )

        r(
            "/upload_draft_boundary",
            UploadDraftBoundaryPayload,
            UploadDraftBoundaryResponsePayload,
            upload_draft_boundary,
            permissions={"geo:edit"},
            tag=TAG_GEO,
            summary="Upload a level's boundary GeoJSON to the draft",
            description="Stores the FeatureCollection in MinIO/S3 under the draft's key "
            "`geo/<country>/v<draft>/<level>.geojson` (never a published version's key) and records it on the "
            "draft; it becomes immutable on publish. Units whose geometry changed (features keyed by "
            "`properties.pcode`) get a BOUNDARY_CHANGE event at submit. Needs the boundary store configured.",
        )

        async def submit_geo_draft(req, body, p):
            return GeoDraftResponsePayload(draft=await G.submit_geo_draft(p, actor_from_request(req)))

        r(
            "/submit_geo_draft",
            SubmitGeoDraftPayload,
            GeoDraftResponsePayload,
            submit_geo_draft,
            permissions={"geo:edit"},
            tag=TAG_GEO,
            summary="Submit the geography draft for approval",
            description="Validates levels, units and every recorded event, completes the lineage (auto CREATE / "
            "RETIRE / RENAME / REPARENT / BOUNDARY_CHANGE events for anything not covered, flagged is_auto) and "
            "moves the draft to SUBMITTED; in awe mode opens an AWE request (`awe_policy_key_geo`, artifact "
            "`master_data.geo_version`).",
        )

        async def approve_geo_draft(req, body, p):
            return GeoDraftResponsePayload(draft=await G.approve_geo_draft(p, actor_from_request(req)))

        r(
            "/approve_geo_draft",
            DecideGeoDraftPayload,
            GeoDraftResponsePayload,
            approve_geo_draft,
            permissions={"geo:publish"},
            tag=TAG_GEO,
            summary="Approve and publish the geography draft (permission mode)",
            description="Publishes the SUBMITTED version (immutable), stamps valid_from / valid_to on new and "
            "retired units and — if in effect — refreshes the legacy /geo tables in the same transaction. "
            "Maker ≠ checker. Disabled in awe mode.",
        )

        async def reject_geo_draft(req, body, p):
            return GeoDraftResponsePayload(draft=await G.reject_geo_draft(p, actor_from_request(req)))

        r(
            "/reject_geo_draft",
            DecideGeoDraftPayload,
            GeoDraftResponsePayload,
            reject_geo_draft,
            permissions={"geo:publish"},
            tag=TAG_GEO,
            summary="Reject the geography draft (permission mode)",
            description="Requires `decision_note`. Maker ≠ checker.",
        )

        async def discard_geo_draft(req, body, p):
            return DiscardGeoDraftResponsePayload(
                discarded_version_no=await G.discard_geo_draft(actor_from_request(req))
            )

        r(
            "/discard_geo_draft",
            EmptyPayload,
            DiscardGeoDraftResponsePayload,
            discard_geo_draft,
            permissions={"geo:edit"},
            tag=TAG_GEO,
            summary="Discard the geography draft",
            description="Closes the open geography draft as DISCARDED (kept, so its number and boundary keys are "
            "never reused). Uploaded objects of the draft stay in the bucket under its own version's keys.",
        )

    # ------------------------------------------------------------------
    # Releases
    # ------------------------------------------------------------------

    def _register_releases(self) -> None:
        R = self.releases
        r = self._route

        async def get_releases(req, body, p):
            return GetReleasesResponsePayload(releases=await R.get_releases())

        r(
            "/get_releases",
            EmptyPayload,
            GetReleasesResponsePayload,
            get_releases,
            permissions=READ,
            tag=TAG_RELEASES,
            summary="All catalogue releases",
            description="Named sets of list versions plus one geography version, for consumers that pin "
            "everything at once. Any versioned read accepts `release` to answer from a release's pins.",
        )

        async def get_release(req, body, p):
            info, members = await R.get_release(p.release_code)
            return GetReleaseResponsePayload(release=info, members=members)

        r(
            "/get_release",
            ReleaseRef,
            GetReleaseResponsePayload,
            get_release,
            permissions=READ,
            tag=TAG_RELEASES,
            summary="One release with its members",
            description="`members: [{list_id, list_code, version_no}]` and `geo_version_no`.",
        )

        async def create_release(req, body, p):
            info, members = await R.create_release(p, actor_from_request(req))
            return GetReleaseResponsePayload(release=info, members=members)

        r(
            "/create_release",
            CreateReleasePayload,
            GetReleaseResponsePayload,
            create_release,
            permissions={"referenceData:edit"},
            tag=TAG_RELEASES,
            summary="Create a draft release",
            description="`release_code` (e.g. 2027.1), `title`, `note`.",
        )

        async def set_release_members(req, body, p):
            info, members = await R.set_release_members(p, actor_from_request(req))
            return GetReleaseResponsePayload(release=info, members=members)

        r(
            "/set_release_members",
            SetReleaseMembersPayload,
            GetReleaseResponsePayload,
            set_release_members,
            permissions={"referenceData:edit"},
            tag=TAG_RELEASES,
            summary="Pin list versions and a geography version",
            description="Only PUBLISHED versions can be members. `replace: true` (default) replaces all "
            "members; false adds / overwrites the given ones. `geo_version_no` sets the geography pin. DRAFT "
            "releases only.",
        )

        async def publish_release(req, body, p):
            info, members = await R.publish_release(p.release_code, actor_from_request(req))
            return GetReleaseResponsePayload(release=info, members=members)

        r(
            "/publish_release",
            ReleaseRef,
            GetReleaseResponsePayload,
            publish_release,
            permissions={"referenceData:publish"},
            tag=TAG_RELEASES,
            summary="Publish a release (immutable)",
            description="Checks every member is published and that `x-list-ref` references between member "
            "lists resolve within the release's own pins. Maker ≠ checker (publisher ≠ creator and ≠ whoever last "
            "set the members). Immutable "
            "afterwards (enforced in Postgres).",
        )

        async def delete_release(req, body, p):
            return DeleteReleaseResponsePayload(
                release_code=await R.delete_release(p.release_code, actor_from_request(req))
            )

        r(
            "/delete_release",
            ReleaseRef,
            DeleteReleaseResponsePayload,
            delete_release,
            permissions={"referenceData:delete"},
            tag=TAG_RELEASES,
            summary="Delete a draft release",
            description="Published releases cannot be deleted.",
        )

    # ------------------------------------------------------------------
    # Feed and configuration
    # ------------------------------------------------------------------

    def _register_feed(self) -> None:
        F = self.feed
        r = self._route

        async def get_changes(req, body, p):
            events, cursor, more = await F.get_changes(
                p.cursor, p.limit, p.subject_type, p.subject_id, p.event_types
            )
            return GetChangesResponsePayload(events=events, next_cursor=cursor, has_more=more)

        r(
            "/get_changes",
            GetChangesPayload,
            GetChangesResponsePayload,
            get_changes,
            permissions=READ,
            tag=TAG_FEED,
            summary="Change feed",
            description=(
                "Catalogue lifecycle events in order, from the append-only change log: list.created, "
                "list.updated, list.draft.created, list.draft.values_changed, list.draft.values_retired, "
                "list.draft.submitted, list.approval.requested, list.draft.approved, list.draft.rejected, "
                "list.version.published, list.version.effective, list.version.migrated, list.draft.discarded "
                "(and the geo.* equivalents, release.created / members_set / published / deleted). Pass the "
                "returned `next_cursor` as `cursor` to continue; `has_more` says whether to call again. Filter "
                "by `subject_type`, `subject_id`, `event_types`. `actor` is the stable user id (token sub) or a "
                "system name, `actor_name` a user's display name. Every event — including those written by the "
                "database (`*.version.effective`, `*.version.migrated`) and the country-pack loader — is "
                "relayed to the Audit Manager when configured, and `*.version.published`, "
                "`*.version.effective` and `release.published` to the WebSub hub, with retries."
            ),
        )

        async def get_catalogue_config(req, body, p):
            state = await F.config_state()
            return CatalogueConfigResponsePayload(
                approval_mode=approval_mode(),
                boundary_store_enabled=BoundaryStore.enabled(),
                audit_enabled=bool((_config.audit_manager_url or "").strip()),
                websub_enabled=bool((_config.websub_hub_url or "").strip()),
                country=state["country"],
                geo_current_version_no=state["geo_current_version_no"],
            )

        r(
            "/get_catalogue_config",
            EmptyPayload,
            CatalogueConfigResponsePayload,
            get_catalogue_config,
            permissions=READ,
            tag=TAG_FEED,
            summary="How this catalogue is configured",
            description="`approval_mode` (permission | awe — the UI shows approve/reject buttons only in "
            "permission mode), whether boundary upload, audit and WebSub are enabled, the country and the "
            "geography version currently in effect.",
        )

    # ------------------------------------------------------------------
    # AWE callback (HMAC, no JWT)
    # ------------------------------------------------------------------

    async def awe_callback(self, request: Request):
        raw = await request.body()
        try:
            result = await self.awe.handle(
                raw_body=raw,
                signature_header=request.headers.get("X-Approval-Signature"),
                timestamp_header=request.headers.get("X-Approval-Timestamp"),
                header_event_id=request.headers.get("X-Approval-Event-Id"),
            )
            return AweWebhookResponse(**result)
        except AweWebhookSignatureError as exc:
            _logger.warning("AWE callback signature rejected: %s", exc)
            return Response(
                content='{"detail":"invalid signature"}', status_code=401, media_type="application/json"
            )
        except CatalogueError as exc:
            _logger.error("AWE callback could not be applied: %s", exc.message)
            return Response(
                content='{"detail":"webhook processing failed"}',
                status_code=422,
                media_type="application/json",
            )
        except Exception:
            _logger.exception("Unexpected error handling the AWE callback")
            return Response(
                content='{"detail":"internal error"}', status_code=500, media_type="application/json"
            )
