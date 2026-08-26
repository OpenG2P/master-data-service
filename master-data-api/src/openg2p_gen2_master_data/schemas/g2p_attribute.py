from typing import List, Optional

from openg2p_fastapi_common.schemas import (
    G2PRequest,
    G2PRequestBody,
    G2PResponse,
    G2PResponseBody,
    G2PResponseHeader,
)
from pydantic import BaseModel, ConfigDict, Field


class AttributeData(BaseModel):
    """A code list this country defines — gender, education level, crop.

    Which lists exist and what they contain is country data, not platform code.
    A universal superset does not exist: gender is the plain case, where
    countries define genuinely different taxonomies rather than subsets of one.
    """

    attribute_id: str
    attribute_code: Optional[str] = None
    attribute_display: Optional[str] = None
    is_hierarchical: Optional[bool] = False


class AttributeValueData(BaseModel):
    """One value of a list.

    Identified by `attribute_id` PLUS `value_id`: the code alone is not unique,
    since 'OTHER' occurs in thirteen of Ethiopia's lists.
    """

    attribute_id: str
    value_id: str
    value_code: Optional[str] = None
    value_display: Optional[str] = None
    parent_value_id: Optional[str] = None
    sort_order: Optional[int] = None


# ---- get_all_attributes -----------------------------------------------------
class GetAttributesRequestPayload(BaseModel):
    pass


class GetAttributesRequestBody(G2PRequestBody):
    request_payload: Optional[GetAttributesRequestPayload] = GetAttributesRequestPayload()


class GetAttributesRequest(G2PRequest):
    request_body: GetAttributesRequestBody


class GetAttributesResponsePayload(BaseModel):
    attributes: List[AttributeData] = []


class GetAttributesResponseBody(G2PResponseBody):
    response_payload: Optional[GetAttributesResponsePayload] = None


class GetAttributesResponse(G2PResponse):
    response_body: Optional[GetAttributesResponseBody] = None


# ---- get_attribute_values ---------------------------------------------------
class GetAttributeValuesRequestPayload(BaseModel):
    # Omit attribute_id to fetch every value — which is what a registry's
    # install-time seed wants, rather than one round trip per list.
    attribute_id: Optional[str] = Field(
        default=None,
        description="Code-list id. When set, returns all values for that attribute.",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "attribute_id": "string",
            }
        }
    )


class GetAttributeValuesRequestBody(G2PRequestBody):
    # Required (like geo) so Swagger does not replace the payload with a
    # partial default that drops null optional fields.
    # Pagination lives on G2PRequestBody.pagination_request (current_page / page_size).
    request_payload: GetAttributeValuesRequestPayload


class GetAttributeValuesRequest(G2PRequest):
    request_body: GetAttributeValuesRequestBody


class GetAttributeValuesResponsePayload(BaseModel):
    attribute_values: List[AttributeValueData] = []
    total: Optional[int] = None


class GetAttributeValuesResponseBody(G2PResponseBody):
    response_payload: Optional[GetAttributeValuesResponsePayload] = None


class GetAttributeValuesResponse(G2PResponse):
    response_body: Optional[GetAttributeValuesResponseBody] = None


# ── Attribute write APIs ─────────────────────────────────────────────────────

class AddAttributeRequestPayload(BaseModel):
    attribute_code: str
    attribute_display: str
    is_hierarchical: Optional[bool] = False


class AddAttributeRequestBody(G2PRequestBody):
    request_payload: AddAttributeRequestPayload


class AddAttributeRequest(G2PRequest):
    request_body: AddAttributeRequestBody


class AddAttributeResponseBody(G2PResponseBody):
    response_payload: Optional[AttributeData] = None


class AddAttributeResponse(G2PResponse):
    response_header: G2PResponseHeader
    response_body: AddAttributeResponseBody


class UpdateAttributeRequestPayload(BaseModel):
    attribute_id: str
    attribute_code: Optional[str] = None
    attribute_display: Optional[str] = None
    is_hierarchical: Optional[bool] = None


class UpdateAttributeRequestBody(G2PRequestBody):
    request_payload: UpdateAttributeRequestPayload


class UpdateAttributeRequest(G2PRequest):
    request_body: UpdateAttributeRequestBody


class UpdateAttributeResponseBody(G2PResponseBody):
    response_payload: Optional[AttributeData] = None


class UpdateAttributeResponse(G2PResponse):
    response_header: G2PResponseHeader
    response_body: UpdateAttributeResponseBody


class DeleteAttributeRequestPayload(BaseModel):
    attribute_id: str
    cascade: bool = False


class DeleteAttributeRequestBody(G2PRequestBody):
    request_payload: DeleteAttributeRequestPayload


class DeleteAttributeRequest(G2PRequest):
    request_body: DeleteAttributeRequestBody


class DeleteAttributeResponsePayload(BaseModel):
    attribute_id: str


class DeleteAttributeResponseBody(G2PResponseBody):
    response_payload: Optional[DeleteAttributeResponsePayload] = None


class DeleteAttributeResponse(G2PResponse):
    response_header: G2PResponseHeader
    response_body: DeleteAttributeResponseBody


# ── Attribute Value write APIs ───────────────────────────────────────────────


class AddAttributeValueRequestPayload(BaseModel):
    attribute_id: str
    value_code: str
    value_display: str
    parent_value_id: Optional[str] = None
    sort_order: Optional[int] = 0


class AddAttributeValueRequestBody(G2PRequestBody):
    request_payload: AddAttributeValueRequestPayload


class AddAttributeValueRequest(G2PRequest):
    request_body: AddAttributeValueRequestBody


class AddAttributeValueResponseBody(G2PResponseBody):
    response_payload: Optional[AttributeValueData] = None


class AddAttributeValueResponse(G2PResponse):
    response_header: G2PResponseHeader
    response_body: AddAttributeValueResponseBody


class UpdateAttributeValueRequestPayload(BaseModel):
    value_id: str
    attribute_id: Optional[str] = None
    value_code: Optional[str] = None
    value_display: Optional[str] = None
    parent_value_id: Optional[str] = None
    sort_order: Optional[int] = None


class UpdateAttributeValueRequestBody(G2PRequestBody):
    request_payload: UpdateAttributeValueRequestPayload


class UpdateAttributeValueRequest(G2PRequest):
    request_body: UpdateAttributeValueRequestBody


class UpdateAttributeValueResponseBody(G2PResponseBody):
    response_payload: Optional[AttributeValueData] = None


class UpdateAttributeValueResponse(G2PResponse):
    response_header: G2PResponseHeader
    response_body: UpdateAttributeValueResponseBody


class DeleteAttributeValueRequestPayload(BaseModel):
    value_id: str
    attribute_id: Optional[str] = None


class DeleteAttributeValueRequestBody(G2PRequestBody):
    request_payload: DeleteAttributeValueRequestPayload


class DeleteAttributeValueRequest(G2PRequest):
    request_body: DeleteAttributeValueRequestBody


class DeleteAttributeValueResponsePayload(BaseModel):
    value_id: str
    attribute_id: Optional[str] = None


class DeleteAttributeValueResponseBody(G2PResponseBody):
    response_payload: Optional[DeleteAttributeValueResponsePayload] = None


class DeleteAttributeValueResponse(G2PResponse):
    response_header: G2PResponseHeader
    response_body: DeleteAttributeValueResponseBody
