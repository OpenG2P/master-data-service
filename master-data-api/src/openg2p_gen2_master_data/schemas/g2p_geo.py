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


# Geo Level Request/Response
class GetGeoLevelsRequestPayload(BaseModel):
    parent_level_id: Optional[str] = None


class GetGeoLevelsRequestBody(G2PRequestBody):
    request_payload: GetGeoLevelsRequestPayload


class GetGeoLevelsRequest(G2PRequest):
    request_body: GetGeoLevelsRequestBody


class GetGeoLevelsResponseBody(G2PResponseBody):
    response_payload: List[GeoLevelData]


class GetGeoLevelsResponse(G2PResponse):
    response_header: G2PResponseHeader
    response_body: GetGeoLevelsResponseBody


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
