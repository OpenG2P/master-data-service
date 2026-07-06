import hashlib
import logging
from typing import Optional

from fastapi_cache.decorator import cache
from openg2p_fastapi_common.controller import BaseController
from starlette.requests import Request
from starlette.responses import Response

from ..services import G2PGeoService
from ..helpers import RequestResponseHelper, get_data_policy_mnemonics
from iam_core.user_auth.helpers import require_permissions
from ..schemas import (
    GetGeoLevelsRequest,
    GetGeoLevelsResponse,
    GetAllGeoLevelsRequest,
    GetAllGeoLevelsResponse,
    GetGeoLevelValuesRequest,
    GetGeoLevelValuesResponse,
)
from ..config import Settings

_config = Settings.get_config()
_logger = logging.getLogger(_config.logging_default_logger_name)


def cache_key_builder_geo_levels(
    func,
    namespace: Optional[str] = "",
    request: Request = None,
    response: Response = None,
    *args,
    **kwargs,
):
    """Custom key builder for get_g2p_geo_levels endpoint."""
    prefix = f"{namespace}:{func.__module__}:{func.__name__}"
    req_body = kwargs.get("get_geo_levels_request")
    if req_body:
        body_hash = hashlib.md5(req_body.model_dump_json().encode()).hexdigest()
        return f"{prefix}:{body_hash}"
    return prefix


def cache_key_builder_geo_level_values(
    func,
    namespace: Optional[str] = "",
    request: Request = None,
    response: Response = None,
    *args,
    **kwargs,
):
    """Custom key builder for get_g2p_geo_level_values endpoint."""
    prefix = f"{namespace}:{func.__module__}:{func.__name__}"
    req_body = kwargs.get("get_geo_level_values_request")
    body_hash = ""
    if req_body:
        body_hash = hashlib.md5(req_body.model_dump_json().encode()).hexdigest()

    policy_key = ""
    http_request = kwargs.get("http_request")
    if http_request is not None:
        policy_key = ",".join(sorted(get_data_policy_mnemonics(http_request)))
    elif request is not None:
        policy_key = ",".join(sorted(get_data_policy_mnemonics(request)))

    return f"{prefix}:{body_hash}:{policy_key}"


class G2PGeoController(BaseController):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.router.tags += ["/geo"]
        self.geo_service = G2PGeoService.get_component()
        self.request_response_helper = RequestResponseHelper().get_component()
        self.router.prefix = "/geo"

        self.router.add_api_route(
            "/get_g2p_geo_levels",
            self.get_g2p_geo_levels,
            responses={200: {"model": GetGeoLevelsResponse}},
            methods=["POST"],
        )

        self.router.add_api_route(
            "/get_all_g2p_geo_levels",
            self.get_all_g2p_geo_levels,
            responses={200: {"model": GetAllGeoLevelsResponse}},
            methods=["POST"],
        )

        self.router.add_api_route(
            "/get_g2p_geo_level_values",
            self.get_g2p_geo_level_values,
            responses={200: {"model": GetGeoLevelValuesResponse}},
            methods=["POST"],
        )

    @cache(expire=_config.cache_expire_seconds, key_builder=cache_key_builder_geo_levels)
    async def get_g2p_geo_levels(
        self,
        get_geo_levels_request: GetGeoLevelsRequest,
    ) -> GetGeoLevelsResponse:
        _logger.debug("Get Geo Levels Request: %s", get_geo_levels_request)
        try:
            parent_level_id = get_geo_levels_request.request_body.request_payload.parent_level_id
            geo_levels = await self.geo_service.get_geo_levels(parent_level_id)

            _logger.debug("Geo levels: %s", geo_levels)

            return self.request_response_helper.construct_geo_levels_success_response(
                get_geo_levels_request, geo_levels
            )
        except Exception as e:
            _logger.error("Error getting geo levels: %s", str(e), exc_info=True)
            return self.request_response_helper.construct_geo_levels_error_response(e, get_geo_levels_request)

    async def get_all_g2p_geo_levels(
        self,
        get_all_geo_levels_request: GetAllGeoLevelsRequest,
    ) -> GetAllGeoLevelsResponse:
        _logger.debug("Get All Geo Levels Request: %s", get_all_geo_levels_request)
        try:
            geo_levels = await self.geo_service.get_all_geo_levels()

            _logger.debug("All geo levels: %s", geo_levels)

            return self.request_response_helper.construct_all_geo_levels_success_response(
                get_all_geo_levels_request, geo_levels
            )
        except Exception as e:
            _logger.error("Error getting all geo levels: %s", str(e), exc_info=True)
            return self.request_response_helper.construct_all_geo_levels_error_response(
                e, get_all_geo_levels_request
            )

    @cache(expire=_config.cache_expire_seconds, key_builder=cache_key_builder_geo_level_values)
    @require_permissions({})
    async def get_g2p_geo_level_values(
        self,
        http_request: Request,
        get_geo_level_values_request: GetGeoLevelValuesRequest,
    ) -> GetGeoLevelValuesResponse:
        _logger.debug("Get Geo Level Values Request: %s", get_geo_level_values_request)
        try:
            payload = get_geo_level_values_request.request_body.request_payload
            level_id = payload.level_id
            parent_level_value_id = payload.parent_level_value_id

            geo_level_values = await self.geo_service.get_geo_level_values(
                level_id,
                parent_level_value_id,
                policy_mnemonics=get_data_policy_mnemonics(http_request),
            )

            _logger.debug("Geo level values: %s", geo_level_values)

            return self.request_response_helper.construct_geo_level_values_success_response(
                get_geo_level_values_request, geo_level_values
            )
        except Exception as e:
            _logger.error("Error getting geo level values: %s", str(e), exc_info=True)
            return self.request_response_helper.construct_geo_level_values_error_response(
                e, get_geo_level_values_request
            )
