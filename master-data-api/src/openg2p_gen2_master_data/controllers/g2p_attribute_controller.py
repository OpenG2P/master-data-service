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
    AddAttributeRequest,
    AddAttributeResponse,
    AddAttributeValueRequest,
    AddAttributeValueResponse,
    DeleteAttributeRequest,
    DeleteAttributeResponse,
    DeleteAttributeValueRequest,
    DeleteAttributeValueResponse,
    GetAttributesRequest,
    GetAttributesResponse,
    GetAttributeValuesRequest,
    GetAttributeValuesResponse,
    UpdateAttributeRequest,
    UpdateAttributeResponse,
    UpdateAttributeValueRequest,
    UpdateAttributeValueResponse,
)
from ..services import G2PAttributeService

_config = Settings.get_config()
_logger = logging.getLogger(_config.logging_default_logger_name)


def cache_key_builder_attributes(
    func,
    namespace: Optional[str] = "",
    request: Request = None,
    response: Response = None,
    *args,
    **kwargs,
):
    """Custom key builder for get_all_attributes endpoint."""
    prefix = f"{namespace}:{func.__module__}:{func.__name__}"
    req_body = kwargs.get("get_attributes_request")
    if req_body:
        body_hash = hashlib.md5(req_body.model_dump_json().encode()).hexdigest()
        return f"{prefix}:{body_hash}"
    return prefix


def cache_key_builder_attribute_values(
    func,
    namespace: Optional[str] = "",
    request: Request = None,
    response: Response = None,
    *args,
    **kwargs,
):
    """Custom key builder for get_attribute_values endpoint."""
    prefix = f"{namespace}:{func.__module__}:{func.__name__}"
    req_body = kwargs.get("get_attribute_values_request")
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


class G2PAttributeController(BaseController):
    """Serves the country's code lists.

    Reads used by registry UI: auth only (``@require_permissions({})``) plus
    data-policy filtering on values. Mutations require MASTER_DATA_ADMIN
    permissions under the master-data-ui Keycloak client.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.router.tags += ["/attributes"]
        self.attribute_service = G2PAttributeService.get_component()
        self.request_response_helper = RequestResponseHelper().get_component()
        self.router.prefix = "/attributes"

        self.router.add_api_route(
            "/get_all_attributes",
            self.get_all_attributes,
            responses={200: {"model": GetAttributesResponse}},
            methods=["POST"],
        )

        self.router.add_api_route(
            "/get_attribute_values",
            self.get_attribute_values,
            responses={200: {"model": GetAttributeValuesResponse}},
            methods=["POST"],
        )

        self.router.add_api_route(
            "/add_attribute",
            self.add_attribute,
            responses={200: {"model": AddAttributeResponse}},
            methods=["POST"],
        )

        self.router.add_api_route(
            "/update_attribute",
            self.update_attribute,
            responses={200: {"model": UpdateAttributeResponse}},
            methods=["POST"],
        )

        self.router.add_api_route(
            "/delete_attribute",
            self.delete_attribute,
            responses={200: {"model": DeleteAttributeResponse}},
            methods=["POST"],
        )

        self.router.add_api_route(
            "/add_attribute_value",
            self.add_attribute_value,
            responses={200: {"model": AddAttributeValueResponse}},
            methods=["POST"],
        )

        self.router.add_api_route(
            "/update_attribute_value",
            self.update_attribute_value,
            responses={200: {"model": UpdateAttributeValueResponse}},
            methods=["POST"],
        )

        self.router.add_api_route(
            "/delete_attribute_value",
            self.delete_attribute_value,
            responses={200: {"model": DeleteAttributeValueResponse}},
            methods=["POST"],
        )

    @require_permissions({})
    @cache(expire=_config.cache_expire_seconds, key_builder=cache_key_builder_attributes)
    async def get_all_attributes(
        self,
        get_attributes_request: GetAttributesRequest,
    ) -> GetAttributesResponse:
        _logger.debug("Get Attributes Request: %s", get_attributes_request)
        try:
            attributes = await self.attribute_service.get_attributes()

            _logger.debug("Attributes: %s", len(attributes))

            return self.request_response_helper.construct_attributes_success_response(
                get_attributes_request, attributes
            )
        except Exception as e:
            _logger.error("Error getting attributes: %s", str(e), exc_info=True)
            return self.request_response_helper.construct_attributes_error_response(e, get_attributes_request)

    @require_permissions({})
    @data_policy
    @cache(expire=_config.cache_expire_seconds, key_builder=cache_key_builder_attribute_values)
    async def get_attribute_values(
        self,
        http_request: Request,
        get_attribute_values_request: GetAttributeValuesRequest,
    ) -> GetAttributeValuesResponse:
        _logger.debug("Get Attribute Values Request: %s", get_attribute_values_request)
        try:
            body = get_attribute_values_request.request_body
            payload = body.request_payload
            pagination = body.pagination_request
            page_size = pagination.page_size if pagination else 1000
            page_number = pagination.current_page if pagination else 1

            values, total = await self.attribute_service.get_attribute_values(
                attribute_id=payload.attribute_id if payload else None,
                page_size=page_size,
                page_number=page_number,
                data_policies=get_data_policies(http_request),
            )

            _logger.debug("Attribute values: %s of %s", len(values), total)

            return self.request_response_helper.construct_attribute_values_success_response(
                get_attribute_values_request, values, total, page_size=page_size
            )
        except Exception as e:
            _logger.error("Error getting attribute values: %s", str(e), exc_info=True)
            return self.request_response_helper.construct_attribute_values_error_response(
                e, get_attribute_values_request
            )

    @require_permissions({"referenceData:create"})
    async def add_attribute(
        self,
        add_attribute_request: AddAttributeRequest,
    ) -> AddAttributeResponse:
        _logger.debug("Add Attribute Request: %s", add_attribute_request)
        try:
            payload = add_attribute_request.request_body.request_payload
            attribute = await self.attribute_service.add_attribute(
                attribute_code=payload.attribute_code,
                attribute_display=payload.attribute_display,
                is_hierarchical=bool(payload.is_hierarchical),
            )
            return self.request_response_helper.construct_add_attribute_success_response(
                add_attribute_request, attribute
            )
        except Exception as e:
            _logger.error("Error adding attribute: %s", str(e), exc_info=True)
            return self.request_response_helper.construct_add_attribute_error_response(
                e, add_attribute_request
            )

    @require_permissions({"referenceData:edit"})
    async def update_attribute(
        self,
        update_attribute_request: UpdateAttributeRequest,
    ) -> UpdateAttributeResponse:
        _logger.debug("Update Attribute Request: %s", update_attribute_request)
        try:
            payload = update_attribute_request.request_body.request_payload
            attribute = await self.attribute_service.update_attribute(payload)
            return self.request_response_helper.construct_update_attribute_success_response(
                update_attribute_request, attribute
            )
        except Exception as e:
            _logger.error("Error updating attribute: %s", str(e), exc_info=True)
            return self.request_response_helper.construct_update_attribute_error_response(
                e, update_attribute_request
            )

    @require_permissions({"referenceData:delete"})
    async def delete_attribute(
        self,
        delete_attribute_request: DeleteAttributeRequest,
    ) -> DeleteAttributeResponse:
        _logger.debug("Delete Attribute Request: %s", delete_attribute_request)
        try:
            payload = delete_attribute_request.request_body.request_payload
            deleted_id = await self.attribute_service.delete_attribute(
                payload.attribute_id,
                cascade=payload.cascade,
            )
            return self.request_response_helper.construct_delete_attribute_success_response(
                delete_attribute_request, deleted_id
            )
        except Exception as e:
            _logger.error("Error deleting attribute: %s", str(e), exc_info=True)
            return self.request_response_helper.construct_delete_attribute_error_response(
                e, delete_attribute_request
            )

    @require_permissions({"referenceData:create"})
    async def add_attribute_value(
        self,
        add_attribute_value_request: AddAttributeValueRequest,
    ) -> AddAttributeValueResponse:
        _logger.debug("Add Attribute Value Request: %s", add_attribute_value_request)
        try:
            payload = add_attribute_value_request.request_body.request_payload
            value = await self.attribute_service.add_attribute_value(
                attribute_id=payload.attribute_id,
                value_code=payload.value_code,
                value_display=payload.value_display,
                parent_value_id=payload.parent_value_id,
                sort_order=payload.sort_order,
            )
            return self.request_response_helper.construct_add_attribute_value_success_response(
                add_attribute_value_request, value
            )
        except Exception as e:
            _logger.error("Error adding attribute value: %s", str(e), exc_info=True)
            return self.request_response_helper.construct_add_attribute_value_error_response(
                e, add_attribute_value_request
            )

    @require_permissions({"referenceData:edit"})
    async def update_attribute_value(
        self,
        update_attribute_value_request: UpdateAttributeValueRequest,
    ) -> UpdateAttributeValueResponse:
        _logger.debug("Update Attribute Value Request: %s", update_attribute_value_request)
        try:
            payload = update_attribute_value_request.request_body.request_payload
            value = await self.attribute_service.update_attribute_value(payload)
            return self.request_response_helper.construct_update_attribute_value_success_response(
                update_attribute_value_request, value
            )
        except Exception as e:
            _logger.error("Error updating attribute value: %s", str(e), exc_info=True)
            return self.request_response_helper.construct_update_attribute_value_error_response(
                e, update_attribute_value_request
            )

    @require_permissions({"referenceData:delete"})
    async def delete_attribute_value(
        self,
        delete_attribute_value_request: DeleteAttributeValueRequest,
    ) -> DeleteAttributeValueResponse:
        _logger.debug("Delete Attribute Value Request: %s", delete_attribute_value_request)
        try:
            payload = delete_attribute_value_request.request_body.request_payload
            value_id, attribute_id = await self.attribute_service.delete_attribute_value(
                payload.value_id,
                payload.attribute_id,
            )
            return self.request_response_helper.construct_delete_attribute_value_success_response(
                delete_attribute_value_request, value_id, attribute_id
            )
        except Exception as e:
            _logger.error("Error deleting attribute value: %s", str(e), exc_info=True)
            return self.request_response_helper.construct_delete_attribute_value_error_response(
                e, delete_attribute_value_request
            )
