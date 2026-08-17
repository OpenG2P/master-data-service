from datetime import date
from typing import Any, Dict, List, Optional

from pydantic import BaseModel
from openg2p_fastapi_common.schemas import (
    G2PRequest,
    G2PRequestBody,
    G2PResponse,
    G2PResponseBody,
    G2PResponseHeader,
)


# Geo Level Data
class GeoLevelData(BaseModel):
    """A level in the hierarchy.

    Depth and naming are country-specific and come from data, so consumers
    must walk `parent_level_id` rather than assume any fixed set of levels.

    All fields below `parent_level_id` are additive and optional — existing
    clients that ignore them continue to work.
    """

    level_id: str
    level_mnemonic: str
    parent_level_id: Optional[str] = None

    # Translatable label for the level itself ("Province", not "province").
    display_name: Optional[str] = None
    display_name_i18n: Optional[Dict[str, Any]] = None

    # Structure vintage, so a report can state which version it used.
    version: Optional[str] = None
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None


# Get All Geo Levels Request/Response
class GetAllGeoLevelsRequestPayload(BaseModel):
    pass


class GetAllGeoLevelsRequestBody(G2PRequestBody):
    request_payload: GetAllGeoLevelsRequestPayload


class GetAllGeoLevelsRequest(G2PRequest):
    request_body: GetAllGeoLevelsRequestBody


class GetAllGeoLevelsResponseBody(G2PResponseBody):
    response_payload: List[GeoLevelData]


class GetAllGeoLevelsResponse(G2PResponse):
    response_header: G2PResponseHeader
    response_body: GetAllGeoLevelsResponseBody


# Geo Level Value Data
class GeoLevelValueData(BaseModel):
    """A node in the hierarchy.

    `level_value_id` stays the stable internal key. `pcode` is the join key to
    the outside world (boundary files, registry data) — name-based joins are
    unreliable and must not be used.
    """

    level_value_id: str
    level_id: str
    level_value_mnemonic: str
    parent_level_value_id: Optional[str] = None

    # Official administrative P-code + where it came from.
    pcode: Optional[str] = None
    pcode_source: Optional[str] = None

    # Boundary geometry pointers. The referenced GeoJSON must carry the same
    # `pcode` as a feature property.
    boundary_uri: Optional[str] = None
    boundary_simplified_uri: Optional[str] = None

    # Presentable, translatable label (mnemonic is a slug).
    display_name: Optional[str] = None
    display_name_i18n: Optional[Dict[str, Any]] = None

    version: Optional[str] = None
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None


# Geo Level Values Request/Response
class GetGeoLevelValuesRequestPayload(BaseModel):
    level_id: str
    parent_level_value_id: Optional[str] = None


class GetGeoLevelValuesRequestBody(G2PRequestBody):
    request_payload: GetGeoLevelValuesRequestPayload


class GetGeoLevelValuesRequest(G2PRequest):
    request_body: GetGeoLevelValuesRequestBody


class GetGeoLevelValuesResponseBody(G2PResponseBody):
    response_payload: List[GeoLevelValueData]


class GetGeoLevelValuesResponse(G2PResponse):
    response_header: G2PResponseHeader
    response_body: GetGeoLevelValuesResponseBody


# ── Geo Level write APIs ─────────────────────────────────────────────────────


class AddGeoLevelRequestPayload(BaseModel):
    level_mnemonic: str
    parent_level_id: Optional[str] = None
    display_name: Optional[str] = None
    display_name_i18n: Optional[Dict[str, Any]] = None
    version: Optional[str] = None
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None


class AddGeoLevelRequestBody(G2PRequestBody):
    request_payload: AddGeoLevelRequestPayload


class AddGeoLevelRequest(G2PRequest):
    request_body: AddGeoLevelRequestBody


class AddGeoLevelResponseBody(G2PResponseBody):
    response_payload: Optional[GeoLevelData] = None


class AddGeoLevelResponse(G2PResponse):
    response_header: G2PResponseHeader
    response_body: AddGeoLevelResponseBody


class UpdateGeoLevelRequestPayload(BaseModel):
    level_id: str
    level_mnemonic: Optional[str] = None
    parent_level_id: Optional[str] = None
    display_name: Optional[str] = None
    display_name_i18n: Optional[Dict[str, Any]] = None
    version: Optional[str] = None
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None


class UpdateGeoLevelRequestBody(G2PRequestBody):
    request_payload: UpdateGeoLevelRequestPayload


class UpdateGeoLevelRequest(G2PRequest):
    request_body: UpdateGeoLevelRequestBody


class UpdateGeoLevelResponseBody(G2PResponseBody):
    response_payload: Optional[GeoLevelData] = None


class UpdateGeoLevelResponse(G2PResponse):
    response_header: G2PResponseHeader
    response_body: UpdateGeoLevelResponseBody


class DeleteGeoLevelRequestPayload(BaseModel):
    level_id: str


class DeleteGeoLevelRequestBody(G2PRequestBody):
    request_payload: DeleteGeoLevelRequestPayload


class DeleteGeoLevelRequest(G2PRequest):
    request_body: DeleteGeoLevelRequestBody


class DeleteGeoLevelResponsePayload(BaseModel):
    level_id: str


class DeleteGeoLevelResponseBody(G2PResponseBody):
    response_payload: Optional[DeleteGeoLevelResponsePayload] = None


class DeleteGeoLevelResponse(G2PResponse):
    response_header: G2PResponseHeader
    response_body: DeleteGeoLevelResponseBody


# ── Geo Level Value write APIs ───────────────────────────────────────────────


class AddGeoLevelValueRequestPayload(BaseModel):
    level_id: str
    level_value_mnemonic: str
    parent_level_value_id: Optional[str] = None
    pcode: Optional[str] = None
    pcode_source: Optional[str] = None
    boundary_uri: Optional[str] = None
    boundary_simplified_uri: Optional[str] = None
    display_name: Optional[str] = None
    display_name_i18n: Optional[Dict[str, Any]] = None
    version: Optional[str] = None
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None


class AddGeoLevelValueRequestBody(G2PRequestBody):
    request_payload: AddGeoLevelValueRequestPayload


class AddGeoLevelValueRequest(G2PRequest):
    request_body: AddGeoLevelValueRequestBody


class AddGeoLevelValueResponseBody(G2PResponseBody):
    response_payload: Optional[GeoLevelValueData] = None


class AddGeoLevelValueResponse(G2PResponse):
    response_header: G2PResponseHeader
    response_body: AddGeoLevelValueResponseBody


class UpdateGeoLevelValueRequestPayload(BaseModel):
    level_value_id: str
    level_id: Optional[str] = None
    level_value_mnemonic: Optional[str] = None
    parent_level_value_id: Optional[str] = None
    pcode: Optional[str] = None
    pcode_source: Optional[str] = None
    boundary_uri: Optional[str] = None
    boundary_simplified_uri: Optional[str] = None
    display_name: Optional[str] = None
    display_name_i18n: Optional[Dict[str, Any]] = None
    version: Optional[str] = None
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None


class UpdateGeoLevelValueRequestBody(G2PRequestBody):
    request_payload: UpdateGeoLevelValueRequestPayload


class UpdateGeoLevelValueRequest(G2PRequest):
    request_body: UpdateGeoLevelValueRequestBody


class UpdateGeoLevelValueResponseBody(G2PResponseBody):
    response_payload: Optional[GeoLevelValueData] = None


class UpdateGeoLevelValueResponse(G2PResponse):
    response_header: G2PResponseHeader
    response_body: UpdateGeoLevelValueResponseBody


class DeleteGeoLevelValueRequestPayload(BaseModel):
    level_value_id: str


class DeleteGeoLevelValueRequestBody(G2PRequestBody):
    request_payload: DeleteGeoLevelValueRequestPayload


class DeleteGeoLevelValueRequest(G2PRequest):
    request_body: DeleteGeoLevelValueRequestBody


class DeleteGeoLevelValueResponsePayload(BaseModel):
    level_value_id: str


class DeleteGeoLevelValueResponseBody(G2PResponseBody):
    response_payload: Optional[DeleteGeoLevelValueResponsePayload] = None


class DeleteGeoLevelValueResponse(G2PResponse):
    response_header: G2PResponseHeader
    response_body: DeleteGeoLevelValueResponseBody
