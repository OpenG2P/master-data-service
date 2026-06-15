import logging
from openg2p_fastapi_common.controller import BaseController

from ..services import G2PPartnerService
from ..helpers import RequestResponseHelper
from ..schemas import (
    GetAllPartnersRequest,
    GetPartnerRequest,
    G2PPartnerResponse,
    G2PPartnersResponse,
)
from ..config import Settings

_config = Settings.get_config()
_logger = logging.getLogger(_config.logging_default_logger_name)


class G2PPartnerController(BaseController):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.router.tags += ["/partner"]
        self.partner_service = G2PPartnerService.get_component()
        self.request_response_helper = RequestResponseHelper().get_component()
        self.router.prefix = "/partner"

        self.router.add_api_route(
            "/get_all_partners",
            self.get_all_partners,
            responses={200: {"model": G2PPartnersResponse}},
            methods=["POST"],
        )

        self.router.add_api_route(
            "/get_partner",
            self.get_partner,
            responses={200: {"model": G2PPartnerResponse}},
            methods=["POST"],
        )

    async def get_all_partners(
        self,
        request: GetAllPartnersRequest,
    ) -> G2PPartnersResponse:
        _logger.debug("Get All Partners Request: %s", request)
        try:
            partners = await self.partner_service.get_all_partners()

            _logger.debug("Partners: %s", partners)

            return self.request_response_helper.construct_partners_success_response(request, partners)
        except Exception as e:
            _logger.error("Error getting all partners: %s", str(e), exc_info=True)
            return self.request_response_helper.construct_partners_error_response(e, request)

    async def get_partner(
        self,
        request: GetPartnerRequest,
    ) -> G2PPartnerResponse:
        _logger.debug("Get Partner Request: %s", request)
        try:
            request_payload = request.request_body.request_payload
            partner = await self.partner_service.get_partner(
                partner_id=request_payload.partner_id,
            )

            _logger.debug("Partner: %s", partner)

            return self.request_response_helper.construct_partner_success_response(request, partner)
        except Exception as e:
            _logger.error("Error getting partner: %s", str(e), exc_info=True)
            return self.request_response_helper.construct_partner_error_response(e, request)
