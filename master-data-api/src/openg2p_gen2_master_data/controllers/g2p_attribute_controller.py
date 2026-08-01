import hashlib
import logging
from typing import Optional

from fastapi_cache.decorator import cache
from openg2p_fastapi_common.controller import BaseController
from starlette.requests import Request
from starlette.responses import Response

from ..services import G2PAttributeService
from ..helpers import RequestResponseHelper
from ..schemas import (
    GetAttributesRequest,
    GetAttributesResponse,
    GetAttributeValuesRequest,
    GetAttributeValuesResponse,
)
from ..config import Settings

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
    if req_body:
        body_hash = hashlib.md5(req_body.model_dump_json().encode()).hexdigest()
        return f"{prefix}:{body_hash}"
    return prefix


class G2PAttributeController(BaseController):
    """Serves the country's code lists.

    Additive: a new router at a new prefix. No existing route changes shape, and
    these return an empty list until a deployment opts into loading code lists
    (geoSeed.load.codelists) — so an install that has not is unaffected.

    Unauthenticated, like the geo hierarchy routes alongside it: the intended
    caller is a registry's install-time seed Job, which has no user token. It
    copies these into the registry's own tables and validates against that copy
    afterwards, which keeps this an install-time dependency rather than one on
    every write.
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

    @cache(expire=_config.cache_expire_seconds, key_builder=cache_key_builder_attributes)
    async def get_all_attributes(
        self,
        get_attributes_request: GetAttributesRequest,
    ) -> GetAttributesResponse:
        _logger.debug("Get Attributes Request: %s", get_attributes_request)
        try:
            payload = get_attributes_request.request_body.request_payload
            attributes = await self.attribute_service.get_attributes(
                domain=payload.domain if payload else None,
                include_domains=bool(payload.include_domains) if payload else False,
            )

            _logger.debug("Attributes: %s", len(attributes))

            return self.request_response_helper.construct_attributes_success_response(
                get_attributes_request, attributes
            )
        except Exception as e:
            _logger.error("Error getting attributes: %s", str(e), exc_info=True)
            return self.request_response_helper.construct_attributes_error_response(e, get_attributes_request)

    @cache(expire=_config.cache_expire_seconds, key_builder=cache_key_builder_attribute_values)
    async def get_attribute_values(
        self,
        get_attribute_values_request: GetAttributeValuesRequest,
    ) -> GetAttributeValuesResponse:
        _logger.debug("Get Attribute Values Request: %s", get_attribute_values_request)
        try:
            payload = get_attribute_values_request.request_body.request_payload
            values, total = await self.attribute_service.get_attribute_values(
                attribute_id=payload.attribute_id if payload else None,
                domain=payload.domain if payload else None,
                include_domains=bool(payload.include_domains) if payload else False,
                page_size=payload.page_size if payload and payload.page_size else 1000,
                page_number=payload.page_number if payload and payload.page_number else 1,
            )

            _logger.debug("Attribute values: %s of %s", len(values), total)

            return self.request_response_helper.construct_attribute_values_success_response(
                get_attribute_values_request, values, total
            )
        except Exception as e:
            _logger.error("Error getting attribute values: %s", str(e), exc_info=True)
            return self.request_response_helper.construct_attribute_values_error_response(
                e, get_attribute_values_request
            )
