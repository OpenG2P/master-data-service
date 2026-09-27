import hashlib
import logging
from typing import Optional

from fastapi_cache.decorator import cache
from iam_core.user_auth.decorators import data_policy, require_permissions
from openg2p_fastapi_common.controller import BaseController
from starlette.requests import Request
from starlette.responses import Response

from ..config import Settings
from ..helpers import RequestResponseHelper
from ..helpers.data_policy_request_helper import get_data_policies, get_data_policy_mnemonics
from ..schemas import (
    AddGeoLevelRequest,
    AddGeoLevelResponse,
    AddGeoLevelValueRequest,
    AddGeoLevelValueResponse,
    DeleteGeoLevelRequest,
    DeleteGeoLevelResponse,
    DeleteGeoLevelValueRequest,
    DeleteGeoLevelValueResponse,
    GetAllGeoLevelsRequest,
    GetAllGeoLevelsResponse,
    GetGeoLevelValuesRequest,
    GetGeoLevelValuesResponse,
    UpdateGeoLevelRequest,
    UpdateGeoLevelResponse,
    UpdateGeoLevelValueRequest,
    UpdateGeoLevelValueResponse,
)
from ..services import G2PGeoService

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
    parts = []
    if req_body:
        parts.append(hashlib.md5(req_body.model_dump_json().encode()).hexdigest())
    if request is not None:
        mnemonics = sorted(get_data_policy_mnemonics(request))
        if mnemonics:
            parts.append(hashlib.md5("|".join(mnemonics).encode()).hexdigest())
    if parts:
        return f"{prefix}:{':'.join(parts)}"
    return prefix


class G2PGeoController(BaseController):
    """Geo hierarchy APIs.

    Reads used by registry UI: auth only (``@require_permissions({})``) plus
    data-policy filtering on values. Mutations require MASTER_DATA_ADMIN
    permissions under the master-data-ui Keycloak client.
    """

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

    @require_permissions({})
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

    @require_permissions({})
    @data_policy
    @cache(expire=_config.cache_expire_seconds, key_builder=cache_key_builder_geo_level_values)
    async def get_geo_level_values(
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
                data_policies=get_data_policies(http_request),
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

    @require_permissions({"geo:create"})
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
            )
            return self.request_response_helper.construct_add_geo_level_success_response(
                add_geo_level_request, level
            )
        except Exception as e:
            _logger.error("Error adding geo level: %s", str(e), exc_info=True)
            return self.request_response_helper.construct_add_geo_level_error_response(
                e, add_geo_level_request
            )

    @require_permissions({"geo:edit"})
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

    @require_permissions({"geo:delete"})
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

    @require_permissions({"geo:create"})
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
            )
            return self.request_response_helper.construct_add_geo_level_value_success_response(
                add_geo_level_value_request, value
            )
        except Exception as e:
            _logger.error("Error adding geo level value: %s", str(e), exc_info=True)
            return self.request_response_helper.construct_add_geo_level_value_error_response(
                e, add_geo_level_value_request
            )

    @require_permissions({"geo:edit"})
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

    @require_permissions({"geo:delete"})
    async def delete_geo_level_value(
        self,
        delete_geo_level_value_request: DeleteGeoLevelValueRequest,
    ) -> DeleteGeoLevelValueResponse:
        _logger.debug("Delete Geo Level Value Request: %s", delete_geo_level_value_request)
        try:
            payload = delete_geo_level_value_request.request_body.request_payload
            deleted_id = await self.geo_service.delete_geo_level_value(
                payload.level_value_id,
                cascade=payload.cascade,
            )
            return self.request_response_helper.construct_delete_geo_level_value_success_response(
                delete_geo_level_value_request, deleted_id
            )
        except Exception as e:
            _logger.error("Error deleting geo level value: %s", str(e), exc_info=True)
            return self.request_response_helper.construct_delete_geo_level_value_error_response(
                e, delete_geo_level_value_request
            )
