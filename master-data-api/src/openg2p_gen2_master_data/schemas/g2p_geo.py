from typing import List, Optional

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
    """

    level_id: str
    level_mnemonic: str
    parent_level_id: Optional[str] = None


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

    `level_value_id` is the stable internal key.
    """

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


# ── Geo Level write APIs ─────────────────────────────────────────────────────


class AddGeoLevelRequestPayload(BaseModel):
    level_mnemonic: str
    parent_level_id: Optional[str] = None


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
    cascade: bool = False


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
