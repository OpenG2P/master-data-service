from typing import Optional, List
from pydantic import BaseModel
from openg2p_fastapi_common.schemas import (
    G2PRequest,
    G2PRequestBody,
    G2PResponse,
    G2PResponseBody,
)


# G2PPartner Data
class G2PPartnerData(BaseModel):
    partner_id: str
    partner_mnemonic: str
    keymanager_reference_id: str
    is_active: bool

    class Config:
        from_attributes: bool = True


# Get All Partners Request/Response
class GetAllPartnersRequestPayload(BaseModel):
    pass


class GetAllPartnersRequestBody(G2PRequestBody):
    request_payload: GetAllPartnersRequestPayload


class GetAllPartnersRequest(G2PRequest):
    request_body: GetAllPartnersRequestBody


class G2PPartnersResponseBody(G2PResponseBody):
    response_payload: Optional[List[G2PPartnerData]] = None


class G2PPartnersResponse(G2PResponse):
    response_body: Optional[G2PPartnersResponseBody] = None


# Get Partner Request/Response
class GetPartnerRequestPayload(BaseModel):
    partner_id: str


class GetPartnerRequestBody(G2PRequestBody):
    request_payload: GetPartnerRequestPayload


class GetPartnerRequest(G2PRequest):
    request_body: GetPartnerRequestBody


class G2PPartnerResponseBody(G2PResponseBody):
    response_payload: Optional[G2PPartnerData] = None


class G2PPartnerResponse(G2PResponse):
    response_body: Optional[G2PPartnerResponseBody] = None

