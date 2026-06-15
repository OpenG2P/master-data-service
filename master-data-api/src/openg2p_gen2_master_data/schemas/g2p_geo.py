from typing import Optional, List
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
    level_id: str
    level_mnemonic: str
    parent_level_id: Optional[str] = None


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


# Geo Level Value Data
class GeoLevelValueData(BaseModel):
    level_value_id: str
    level_id: str
    level_value_mnemonic: str
    parent_level_value_id: Optional[str] = None


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
