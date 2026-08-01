from datetime import date
from typing import Any, Dict, List, Optional

from openg2p_fastapi_common.schemas import (
    G2PRequest,
    G2PRequestBody,
    G2PResponse,
    G2PResponseBody,
)
from pydantic import BaseModel


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
    display_name_i18n: Optional[Dict[str, Any]] = None

    # Which pack, and which version, this came from — so a consumer can assert
    # it seeded against the pack it meant to rather than assume.
    country: Optional[str] = None
    version: Optional[str] = None


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
    display_name_i18n: Optional[Dict[str, Any]] = None

    # Semantic roles this value plays, from the pack's closed vocabulary.
    # Consumers should match on a role rather than on the literal value —
    # `relationship_to_head = 'SELF'` is only true for countries that happen to
    # use that code, and it fails silently for the rest.
    roles: Optional[List[str]] = None

    # NULL for the core lists; a domain name such as 'agriculture' otherwise.
    domain: Optional[str] = None
    country: Optional[str] = None
    version: Optional[str] = None
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None


# ---- get_all_attributes -----------------------------------------------------
class GetAttributesRequestPayload(BaseModel):
    # Restrict to one domain, or omit for the core lists every registry uses.
    domain: Optional[str] = None
    include_domains: Optional[bool] = False


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
    attribute_id: Optional[str] = None
    domain: Optional[str] = None
    include_domains: Optional[bool] = False
    page_size: Optional[int] = 1000
    page_number: Optional[int] = 1


class GetAttributeValuesRequestBody(G2PRequestBody):
    request_payload: Optional[GetAttributeValuesRequestPayload] = GetAttributeValuesRequestPayload()


class GetAttributeValuesRequest(G2PRequest):
    request_body: GetAttributeValuesRequestBody


class GetAttributeValuesResponsePayload(BaseModel):
    attribute_values: List[AttributeValueData] = []
    total: Optional[int] = None


class GetAttributeValuesResponseBody(G2PResponseBody):
    response_payload: Optional[GetAttributeValuesResponsePayload] = None


class GetAttributeValuesResponse(G2PResponse):
    response_body: Optional[GetAttributeValuesResponseBody] = None
