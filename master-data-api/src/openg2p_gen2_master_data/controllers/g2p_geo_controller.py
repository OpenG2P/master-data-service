import hashlib
import logging
from typing import Optional

from fastapi_cache.decorator import cache
from openg2p_fastapi_common.controller import BaseController
from starlette.requests import Request
from starlette.responses import Response

from ..services import G2PGeoService
from ..helpers import RequestResponseHelper
from ..schemas import (
    GetAllGeoLevelsRequest,
    GetAllGeoLevelsResponse,
    GetGeoLevelValuesRequest,
    GetGeoLevelValuesResponse,
    AddGeoLevelRequest,
    AddGeoLevelResponse,
    UpdateGeoLevelRequest,
    UpdateGeoLevelResponse,
    DeleteGeoLevelRequest,
    DeleteGeoLevelResponse,
    AddGeoLevelValueRequest,
    AddGeoLevelValueResponse,
    UpdateGeoLevelValueRequest,
    UpdateGeoLevelValueResponse,
    DeleteGeoLevelValueRequest,
    DeleteGeoLevelValueResponse,
)
from ..config import Settings

_config = Settings.get_config()
_logger = logging.getLogger(_config.logging_default_logger_name)


def cache_key_builder_geo_level_values(
    func,
    namespace: Optional[str] = "",
    request: Request = None,
    response: Response = None,
    *args,
    **kwargs,
):
    """Custom key builder for get_geo_level_values endpoint."""
    prefix = f"{namespace}:{func.__module__}:{func.__name__}"
    req_body = kwargs.get("get_geo_level_values_request")
    if req_body:
        body_hash = hashlib.md5(req_body.model_dump_json().encode()).hexdigest()
        return f"{prefix}:{body_hash}"
    return prefix


class G2PGeoController(BaseController):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.router.tags += ["/geo"]
        self.geo_service = G2PGeoService.get_component()
        self.request_response_helper = RequestResponseHelper().get_component()
        self.router.prefix = "/geo"

        self.router.add_api_route(
            "/get_all_geo_levels",
            self.get_all_geo_levels,
            responses={200: {"model": GetAllGeoLevelsResponse}},
            methods=["POST"],
        )

        self.router.add_api_route(
            "/get_geo_level_values",
            self.get_geo_level_values,
            responses={200: {"model": GetGeoLevelValuesResponse}},
            methods=["POST"],
        )

        self.router.add_api_route(
            "/add_geo_level",
            self.add_geo_level,
            responses={200: {"model": AddGeoLevelResponse}},
            methods=["POST"],
        )

        self.router.add_api_route(
            "/update_geo_level",
            self.update_geo_level,
            responses={200: {"model": UpdateGeoLevelResponse}},
            methods=["POST"],
        )

        self.router.add_api_route(
            "/delete_geo_level",
            self.delete_geo_level,
            responses={200: {"model": DeleteGeoLevelResponse}},
            methods=["POST"],
        )

        self.router.add_api_route(
            "/add_geo_level_value",
            self.add_geo_level_value,
            responses={200: {"model": AddGeoLevelValueResponse}},
            methods=["POST"],
        )

        self.router.add_api_route(
            "/update_geo_level_value",
            self.update_geo_level_value,
            responses={200: {"model": UpdateGeoLevelValueResponse}},
            methods=["POST"],
        )

        self.router.add_api_route(
            "/delete_geo_level_value",
            self.delete_geo_level_value,
            responses={200: {"model": DeleteGeoLevelValueResponse}},
            methods=["POST"],
        )
        
    async def get_all_geo_levels(
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
    async def get_geo_level_values(
        self,
        _http_request: Request,
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

    async def add_geo_level(
        self,
        add_geo_level_request: AddGeoLevelRequest,
    ) -> AddGeoLevelResponse:
        _logger.debug("Add Geo Level Request: %s", add_geo_level_request)
        try:
            payload = add_geo_level_request.request_body.request_payload
            level = await self.geo_service.add_geo_level(
                level_mnemonic=payload.level_mnemonic,
                parent_level_id=payload.parent_level_id,
                display_name=payload.display_name,
                display_name_i18n=payload.display_name_i18n,
                version=payload.version,
                valid_from=payload.valid_from,
                valid_to=payload.valid_to,
            )
            return self.request_response_helper.construct_add_geo_level_success_response(
                add_geo_level_request, level
            )
        except Exception as e:
            _logger.error("Error adding geo level: %s", str(e), exc_info=True)
            return self.request_response_helper.construct_add_geo_level_error_response(
                e, add_geo_level_request
            )

    async def update_geo_level(
        self,
        update_geo_level_request: UpdateGeoLevelRequest,
    ) -> UpdateGeoLevelResponse:
        _logger.debug("Update Geo Level Request: %s", update_geo_level_request)
        try:
            payload = update_geo_level_request.request_body.request_payload
            level = await self.geo_service.update_geo_level(payload)
            return self.request_response_helper.construct_update_geo_level_success_response(
                update_geo_level_request, level
            )
        except Exception as e:
            _logger.error("Error updating geo level: %s", str(e), exc_info=True)
            return self.request_response_helper.construct_update_geo_level_error_response(
                e, update_geo_level_request
            )

    async def delete_geo_level(
        self,
        delete_geo_level_request: DeleteGeoLevelRequest,
    ) -> DeleteGeoLevelResponse:
        _logger.debug("Delete Geo Level Request: %s", delete_geo_level_request)
        try:
            level_id = delete_geo_level_request.request_body.request_payload.level_id
            deleted_id = await self.geo_service.delete_geo_level(level_id)
            return self.request_response_helper.construct_delete_geo_level_success_response(
                delete_geo_level_request, deleted_id
            )
        except Exception as e:
            _logger.error("Error deleting geo level: %s", str(e), exc_info=True)
            return self.request_response_helper.construct_delete_geo_level_error_response(
                e, delete_geo_level_request
            )

    async def add_geo_level_value(
        self,
        add_geo_level_value_request: AddGeoLevelValueRequest,
    ) -> AddGeoLevelValueResponse:
        _logger.debug("Add Geo Level Value Request: %s", add_geo_level_value_request)
        try:
            payload = add_geo_level_value_request.request_body.request_payload
            value = await self.geo_service.add_geo_level_value(
                level_id=payload.level_id,
                level_value_mnemonic=payload.level_value_mnemonic,
                parent_level_value_id=payload.parent_level_value_id,
                pcode=payload.pcode,
                pcode_source=payload.pcode_source,
                boundary_uri=payload.boundary_uri,
                boundary_simplified_uri=payload.boundary_simplified_uri,
                display_name=payload.display_name,
                display_name_i18n=payload.display_name_i18n,
                version=payload.version,
                valid_from=payload.valid_from,
                valid_to=payload.valid_to,
            )
            return self.request_response_helper.construct_add_geo_level_value_success_response(
                add_geo_level_value_request, value
            )
        except Exception as e:
            _logger.error("Error adding geo level value: %s", str(e), exc_info=True)
            return self.request_response_helper.construct_add_geo_level_value_error_response(
                e, add_geo_level_value_request
            )

    async def update_geo_level_value(
        self,
        update_geo_level_value_request: UpdateGeoLevelValueRequest,
    ) -> UpdateGeoLevelValueResponse:
        _logger.debug("Update Geo Level Value Request: %s", update_geo_level_value_request)
        try:
            payload = update_geo_level_value_request.request_body.request_payload
            value = await self.geo_service.update_geo_level_value(payload)
            return self.request_response_helper.construct_update_geo_level_value_success_response(
                update_geo_level_value_request, value
            )
        except Exception as e:
            _logger.error("Error updating geo level value: %s", str(e), exc_info=True)
            return self.request_response_helper.construct_update_geo_level_value_error_response(
                e, update_geo_level_value_request
            )

    async def delete_geo_level_value(
        self,
        delete_geo_level_value_request: DeleteGeoLevelValueRequest,
    ) -> DeleteGeoLevelValueResponse:
        _logger.debug("Delete Geo Level Value Request: %s", delete_geo_level_value_request)
        try:
            level_value_id = (
                delete_geo_level_value_request.request_body.request_payload.level_value_id
            )
            deleted_id = await self.geo_service.delete_geo_level_value(level_value_id)
            return self.request_response_helper.construct_delete_geo_level_value_success_response(
                delete_geo_level_value_request, deleted_id
            )
        except Exception as e:
            _logger.error("Error deleting geo level value: %s", str(e), exc_info=True)
            return self.request_response_helper.construct_delete_geo_level_value_error_response(
                e, delete_geo_level_value_request
            )
