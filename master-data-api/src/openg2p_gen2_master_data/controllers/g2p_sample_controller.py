# NOTE: no `from __future__ import annotations` here — endpoint signatures must
# stay real types for FastAPI.
import logging
from datetime import datetime

from iam_core.user_auth.decorators import require_permissions
from openg2p_fastapi_common.controller import BaseController
from openg2p_fastapi_common.schemas import G2PPaginationResponse, G2PResponseHeader, G2PResponseStatus

from ..config import Settings
from ..schemas.g2p_catalogue import CatalogueRequest, CatalogueResponse, CatalogueResponseBody
from ..schemas.g2p_sample import (
    GetSampleHouseholdsPayload,
    GetSampleHouseholdsResponsePayload,
    GetSampleIndividualsPayload,
    GetSampleIndividualsResponsePayload,
)
from ..services.g2p_sample_service import G2PSampleService

_config = Settings.get_config()
_logger = logging.getLogger(_config.logging_default_logger_name)

TAG = "/samples"
_PAGING = (
    " Paged with `pagination_request` (`page_size`, `current_page`; default 1000 per page); "
    "`response_body.pagination_response` carries `number_of_items` and `number_of_pages`. Empty unless the "
    "deployment loaded the country pack's samples (`--load samples`)."
)

IndividualsRequest = CatalogueRequest[GetSampleIndividualsPayload]
IndividualsResponse = CatalogueResponse[GetSampleIndividualsResponsePayload]
HouseholdsRequest = CatalogueRequest[GetSampleHouseholdsPayload]
HouseholdsResponse = CatalogueResponse[GetSampleHouseholdsResponsePayload]


def _header(req, status: G2PResponseStatus, code: str = "", message: str = "") -> G2PResponseHeader:
    request_id = req.request_header.request_id if req is not None and req.request_header else ""
    return G2PResponseHeader(
        request_id=request_id,
        response_status=status,
        response_error_code=code,
        response_error_message=message,
        response_timestamp=datetime.now(),
    )


def _page(req) -> tuple[int, int]:
    p = req.request_body.pagination_request
    return (p.page_size, p.current_page) if p else (1000, 1)


def _pagination(total: int, size: int) -> G2PPaginationResponse:
    return G2PPaginationResponse(
        number_of_items=total, number_of_pages=(total + size - 1) // size if total else 0
    )


class G2PSampleController(BaseController):
    """Sample people and households from the country pack. Reads: an authenticated caller."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.router.prefix = "/samples"
        self.router.tags += [TAG]
        self.samples = G2PSampleService.get_component()

        self.router.add_api_route(
            "/get_individuals",
            self.get_individuals,
            methods=["POST"],
            responses={200: {"model": IndividualsResponse}},
            tags=[TAG],
            summary="Sample people (testing and demos only)",
            description=(
                "**For testing and demos only; not for production use.** Sample people are made-up demo "
                "data, not reference data: they are not versioned or approved, and a production deployment "
                "should not load them. "
                "The sample individuals the country pack loaded, in `individual_id` order: who they are "
                "(names, gender, birth date, national id, phone), where they live (`geo_pcode`, a unit of "
                "the geography, plus `address_parts` below the lowest level and coordinates) and coded facts "
                "(values of the pack's code lists). Registries seed their sample records from these, so one "
                "set of people populates every registry of the deployment. Optional filters: "
                "`household_id`, `geo_pcode`, `country`." + _PAGING
            ),
        )
        self.router.add_api_route(
            "/get_households",
            self.get_households,
            methods=["POST"],
            responses={200: {"model": HouseholdsResponse}},
            tags=[TAG],
            summary="Sample households (testing and demos only)",
            description=(
                "**For testing and demos only; not for production use.** "
                "The sample households the country pack loaded, in `household_id` order, with their head, "
                "size, dwelling and amenities (codes of the pack's lists) and location. Optional filters: "
                "`geo_pcode`, `country`." + _PAGING
            ),
        )

    @require_permissions({})
    async def get_individuals(self, request: IndividualsRequest) -> IndividualsResponse:
        body = CatalogueResponseBody[GetSampleIndividualsResponsePayload]
        try:
            p = request.request_body.request_payload
            size, page = _page(request)
            people, total = await self.samples.get_individuals(
                household_id=p.household_id,
                geo_pcode=p.geo_pcode,
                country=p.country,
                page_size=size,
                page_number=page,
            )
            return IndividualsResponse(
                response_header=_header(request, G2PResponseStatus.SUCCESS),
                response_body=body(
                    response_payload=GetSampleIndividualsResponsePayload(individuals=people, total=total),
                    pagination_response=_pagination(total, size),
                ),
            )
        except Exception as exc:  # noqa: BLE001 — errors go back in the envelope
            _logger.error("/samples/get_individuals failed: %s", exc, exc_info=True)
            return IndividualsResponse(
                response_header=_header(request, G2PResponseStatus.ERROR, "G2P-SMP-500", str(exc)),
                response_body=body(response_payload=None),
            )

    @require_permissions({})
    async def get_households(self, request: HouseholdsRequest) -> HouseholdsResponse:
        body = CatalogueResponseBody[GetSampleHouseholdsResponsePayload]
        try:
            p = request.request_body.request_payload
            size, page = _page(request)
            households, total = await self.samples.get_households(
                geo_pcode=p.geo_pcode, country=p.country, page_size=size, page_number=page
            )
            return HouseholdsResponse(
                response_header=_header(request, G2PResponseStatus.SUCCESS),
                response_body=body(
                    response_payload=GetSampleHouseholdsResponsePayload(households=households, total=total),
                    pagination_response=_pagination(total, size),
                ),
            )
        except Exception as exc:  # noqa: BLE001
            _logger.error("/samples/get_households failed: %s", exc, exc_info=True)
            return HouseholdsResponse(
                response_header=_header(request, G2PResponseStatus.ERROR, "G2P-SMP-500", str(exc)),
                response_body=body(response_payload=None),
            )
