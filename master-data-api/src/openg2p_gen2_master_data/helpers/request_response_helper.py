from datetime import datetime
from typing import List, Optional
from openg2p_fastapi_common.service import BaseService
from openg2p_fastapi_common.schemas import (
    G2PPaginationResponse,
    G2PResponseHeader,
    G2PResponseStatus,
)

from ..schemas import (
    GeoLevelData,
    GetAllGeoLevelsRequest,
    GetAllGeoLevelsResponse,
    GetAllGeoLevelsResponseBody,
    GeoLevelValueData,
    GetGeoLevelValuesRequest,
    GetGeoLevelValuesResponse,
    GetGeoLevelValuesResponseBody,
    AddGeoLevelRequest,
    AddGeoLevelResponse,
    AddGeoLevelResponseBody,
    UpdateGeoLevelRequest,
    UpdateGeoLevelResponse,
    UpdateGeoLevelResponseBody,
    DeleteGeoLevelRequest,
    DeleteGeoLevelResponse,
    DeleteGeoLevelResponseBody,
    DeleteGeoLevelResponsePayload,
    AddGeoLevelValueRequest,
    AddGeoLevelValueResponse,
    AddGeoLevelValueResponseBody,
    UpdateGeoLevelValueRequest,
    UpdateGeoLevelValueResponse,
    UpdateGeoLevelValueResponseBody,
    DeleteGeoLevelValueRequest,
    DeleteGeoLevelValueResponse,
    DeleteGeoLevelValueResponseBody,
    DeleteGeoLevelValueResponsePayload,
    GetAllPartnersRequest,
    G2PPartnersResponse,
    G2PPartnersResponseBody,
    GetPartnerRequest,
    G2PPartnerResponse,
    G2PPartnerResponseBody,
    G2PPartnerData,
    AttributeData,
    AttributeValueData,
    GetAttributesRequest,
    GetAttributesResponse,
    GetAttributesResponseBody,
    GetAttributesResponsePayload,
    GetAttributeValuesRequest,
    GetAttributeValuesResponse,
    GetAttributeValuesResponseBody,
    GetAttributeValuesResponsePayload,
    AddAttributeRequest,
    AddAttributeResponse,
    AddAttributeResponseBody,
    UpdateAttributeRequest,
    UpdateAttributeResponse,
    UpdateAttributeResponseBody,
    DeleteAttributeRequest,
    DeleteAttributeResponse,
    DeleteAttributeResponseBody,
    DeleteAttributeResponsePayload,
    AddAttributeValueRequest,
    AddAttributeValueResponse,
    AddAttributeValueResponseBody,
    UpdateAttributeValueRequest,
    UpdateAttributeValueResponse,
    UpdateAttributeValueResponseBody,
    DeleteAttributeValueRequest,
    DeleteAttributeValueResponse,
    DeleteAttributeValueResponseBody,
    DeleteAttributeValueResponsePayload,
)


class RequestResponseHelper(BaseService):
    def construct_all_geo_levels_success_response(
        self,
        g2p_request: GetAllGeoLevelsRequest,
        levels: List[GeoLevelData],
    ) -> GetAllGeoLevelsResponse:
        """
        Construct a success response for get_all_geo_levels API.

        Args:
            g2p_request: The G2P request object
            levels: List of geo level data to return

        Returns:
            GetAllGeoLevelsResponse with success status
        """
        request_id = g2p_request.request_header.request_id if g2p_request.request_header else ""

        response_header = G2PResponseHeader(
            request_id=request_id,
            response_status=G2PResponseStatus.SUCCESS,
            response_error_code="",
            response_error_message="",
            response_timestamp=datetime.now(),
        )

        response_body = GetAllGeoLevelsResponseBody(
            pagination_response=None,
            response_payload=levels,
        )

        return GetAllGeoLevelsResponse(
            response_header=response_header,
            response_body=response_body,
        )

    def construct_all_geo_levels_error_response(
        self,
        error: Exception,
        g2p_request: GetAllGeoLevelsRequest = None,
    ) -> GetAllGeoLevelsResponse:
        """
        Construct an error response for get_all_geo_levels API.

        Args:
            error: The exception that occurred
            g2p_request: Optional G2P request object

        Returns:
            GetAllGeoLevelsResponse with error status
        """
        if hasattr(error, "code") and hasattr(error, "message"):
            error_code = str(error.code)
            error_message = error.message
        else:
            error_code = "500"
            error_message = str(error)

        request_id = ""
        if g2p_request and g2p_request.request_header:
            request_id = g2p_request.request_header.request_id

        response_header = G2PResponseHeader(
            request_id=request_id,
            response_status=G2PResponseStatus.ERROR,
            response_error_code=error_code,
            response_error_message=error_message,
            response_timestamp=datetime.now(),
        )

        response_body = GetAllGeoLevelsResponseBody(
            pagination_response=None,
            response_payload=[],
        )

        return GetAllGeoLevelsResponse(
            response_header=response_header,
            response_body=response_body,
        )

    def construct_geo_level_values_success_response(
        self,
        g2p_request: GetGeoLevelValuesRequest,
        values: List[GeoLevelValueData],
    ) -> GetGeoLevelValuesResponse:
        """
        Construct a success response for get_geo_level_values API.

        Args:
            g2p_request: The G2P request object
            values: List of geo level value data to return

        Returns:
            GetGeoLevelValuesResponse with success status
        """
        request_id = g2p_request.request_header.request_id if g2p_request.request_header else ""

        response_header = G2PResponseHeader(
            request_id=request_id,
            response_status=G2PResponseStatus.SUCCESS,
            response_error_code="",
            response_error_message="",
            response_timestamp=datetime.now(),
        )

        response_body = GetGeoLevelValuesResponseBody(
            pagination_response=None,
            response_payload=values,
        )

        return GetGeoLevelValuesResponse(
            response_header=response_header,
            response_body=response_body,
        )

    def construct_geo_level_values_error_response(
        self,
        error: Exception,
        g2p_request: GetGeoLevelValuesRequest = None,
    ) -> GetGeoLevelValuesResponse:
        """
        Construct an error response for get_geo_level_values API.

        Args:
            error: The exception that occurred
            g2p_request: Optional G2P request object

        Returns:
            GetGeoLevelValuesResponse with error status
        """
        if hasattr(error, "code") and hasattr(error, "message"):
            error_code = str(error.code)
            error_message = error.message
        else:
            error_code = "500"
            error_message = str(error)

        request_id = ""
        if g2p_request and g2p_request.request_header:
            request_id = g2p_request.request_header.request_id

        response_header = G2PResponseHeader(
            request_id=request_id,
            response_status=G2PResponseStatus.ERROR,
            response_error_code=error_code,
            response_error_message=error_message,
            response_timestamp=datetime.now(),
        )

        response_body = GetGeoLevelValuesResponseBody(
            pagination_response=None,
            response_payload=[],
        )

        return GetGeoLevelValuesResponse(
            response_header=response_header,
            response_body=response_body,
        )

    def construct_partners_success_response(
        self,
        g2p_request: GetAllPartnersRequest,
        partners: List[G2PPartnerData],
    ) -> G2PPartnersResponse:
        """
        Construct a success response for get_all_partners API.

        Args:
            g2p_request: The G2P request object
            partners: List of partner data to return

        Returns:
            G2PPartnersResponse with success status
        """
        request_id = g2p_request.request_header.request_id if g2p_request.request_header else ""

        response_header = G2PResponseHeader(
            request_id=request_id,
            response_status=G2PResponseStatus.SUCCESS,
            response_error_code="",
            response_error_message="",
            response_timestamp=datetime.now(),
        )

        response_body = G2PPartnersResponseBody(
            pagination_response=None,
            response_payload=partners,
        )

        return G2PPartnersResponse(
            response_header=response_header,
            response_body=response_body,
        )

    def construct_partners_error_response(
        self,
        error: Exception,
        g2p_request: GetAllPartnersRequest = None,
    ) -> G2PPartnersResponse:
        """
        Construct an error response for get_all_partners API.

        Args:
            error: The exception that occurred
            g2p_request: Optional G2P request object

        Returns:
            G2PPartnersResponse with error status
        """
        if hasattr(error, "code") and hasattr(error, "message"):
            error_code = str(error.code)
            error_message = error.message
        else:
            error_code = "500"
            error_message = str(error)

        request_id = ""
        if g2p_request and g2p_request.request_header:
            request_id = g2p_request.request_header.request_id

        response_header = G2PResponseHeader(
            request_id=request_id,
            response_status=G2PResponseStatus.ERROR,
            response_error_code=error_code,
            response_error_message=error_message,
            response_timestamp=datetime.now(),
        )

        response_body = G2PPartnersResponseBody(
            pagination_response=None,
            response_payload=[],
        )

        return G2PPartnersResponse(
            response_header=response_header,
            response_body=response_body,
        )

    def construct_partner_success_response(
        self,
        g2p_request: GetPartnerRequest,
        partner: Optional[G2PPartnerData],
    ) -> G2PPartnerResponse:
        """
        Construct a success response for get_partner API.

        Args:
            g2p_request: The G2P request object
            partner: Partner data to return

        Returns:
            G2PPartnerResponse with success status
        """
        request_id = g2p_request.request_header.request_id if g2p_request.request_header else ""

        response_header = G2PResponseHeader(
            request_id=request_id,
            response_status=G2PResponseStatus.SUCCESS,
            response_error_code="",
            response_error_message="",
            response_timestamp=datetime.now(),
        )

        response_body = G2PPartnerResponseBody(
            pagination_response=None,
            response_payload=partner,
        )

        return G2PPartnerResponse(
            response_header=response_header,
            response_body=response_body,
        )

    def construct_partner_error_response(
        self,
        error: Exception,
        g2p_request: GetPartnerRequest = None,
    ) -> G2PPartnerResponse:
        """
        Construct an error response for get_partner API.

        Args:
            error: The exception that occurred
            g2p_request: Optional G2P request object

        Returns:
            G2PPartnerResponse with error status
        """
        if hasattr(error, "code") and hasattr(error, "message"):
            error_code = str(error.code)
            error_message = error.message
        else:
            error_code = "500"
            error_message = str(error)

        request_id = ""
        if g2p_request and g2p_request.request_header:
            request_id = g2p_request.request_header.request_id

        response_header = G2PResponseHeader(
            request_id=request_id,
            response_status=G2PResponseStatus.ERROR,
            response_error_code=error_code,
            response_error_message=error_message,
            response_timestamp=datetime.now(),
        )

        response_body = G2PPartnerResponseBody(
            pagination_response=None,
            response_payload=None,
        )

        return G2PPartnerResponse(
            response_header=response_header,
            response_body=response_body,
        )

    # ── Country code lists ───────────────────────────────────────────────────
    # Additive. These build responses for the new /attributes routes; no
    # existing method above changes.

    def _attribute_response_header(self, g2p_request, error: Exception = None) -> G2PResponseHeader:
        request_id = ""
        if g2p_request and g2p_request.request_header:
            request_id = g2p_request.request_header.request_id

        if error is None:
            return G2PResponseHeader(
                request_id=request_id,
                response_status=G2PResponseStatus.SUCCESS,
                response_error_code="",
                response_error_message="",
                response_timestamp=datetime.now(),
            )

        if hasattr(error, "code") and hasattr(error, "message"):
            error_code = str(error.code)
            error_message = error.message
        else:
            error_code = "500"
            error_message = str(error)

        return G2PResponseHeader(
            request_id=request_id,
            response_status=G2PResponseStatus.ERROR,
            response_error_code=error_code,
            response_error_message=error_message,
            response_timestamp=datetime.now(),
        )

    def construct_attributes_success_response(
        self,
        g2p_request: GetAttributesRequest,
        attributes: List[AttributeData],
    ) -> GetAttributesResponse:
        """Construct a success response for get_all_attributes API."""
        return GetAttributesResponse(
            response_header=self._attribute_response_header(g2p_request),
            response_body=GetAttributesResponseBody(
                pagination_response=None,
                response_payload=GetAttributesResponsePayload(attributes=attributes),
            ),
        )

    def construct_attributes_error_response(
        self,
        error: Exception,
        g2p_request: GetAttributesRequest = None,
    ) -> GetAttributesResponse:
        """Construct an error response for get_all_attributes API."""
        return GetAttributesResponse(
            response_header=self._attribute_response_header(g2p_request, error),
            response_body=GetAttributesResponseBody(
                pagination_response=None,
                response_payload=None,
            ),
        )

    def construct_attribute_values_success_response(
        self,
        g2p_request: GetAttributeValuesRequest,
        values: List[AttributeValueData],
        total: Optional[int] = None,
        page_size: Optional[int] = None,
    ) -> GetAttributeValuesResponse:
        """Construct a success response for get_attribute_values API.

        `total` is the unpaginated count, so a seed job can tell a short last
        page from a truncated one instead of guessing from the page size.
        """
        total_items = total if total is not None else len(values)
        pagination_response = None
        if page_size and page_size > 0:
            number_of_pages = (total_items + page_size - 1) // page_size if total_items else 0
            pagination_response = G2PPaginationResponse(
                number_of_items=total_items,
                number_of_pages=number_of_pages,
            )

        return GetAttributeValuesResponse(
            response_header=self._attribute_response_header(g2p_request),
            response_body=GetAttributeValuesResponseBody(
                pagination_response=pagination_response,
                response_payload=GetAttributeValuesResponsePayload(
                    attribute_values=values,
                    total=total_items,
                ),
            ),
        )

    def construct_attribute_values_error_response(
        self,
        error: Exception,
        g2p_request: GetAttributeValuesRequest = None,
    ) -> GetAttributeValuesResponse:
        """Construct an error response for get_attribute_values API."""
        return GetAttributeValuesResponse(
            response_header=self._attribute_response_header(g2p_request, error),
            response_body=GetAttributeValuesResponseBody(
                pagination_response=None,
                response_payload=None,
            ),
        )

    def _geo_write_response_header(self, g2p_request=None, error: Exception = None) -> G2PResponseHeader:
        request_id = ""
        if g2p_request and g2p_request.request_header:
            request_id = g2p_request.request_header.request_id

        if error is None:
            return G2PResponseHeader(
                request_id=request_id,
                response_status=G2PResponseStatus.SUCCESS,
                response_error_code="",
                response_error_message="",
                response_timestamp=datetime.now(),
            )

        if hasattr(error, "code") and hasattr(error, "message"):
            error_code = str(error.code)
            error_message = error.message
        else:
            error_code = "500"
            error_message = str(error)

        return G2PResponseHeader(
            request_id=request_id,
            response_status=G2PResponseStatus.ERROR,
            response_error_code=error_code,
            response_error_message=error_message,
            response_timestamp=datetime.now(),
        )

    def construct_add_geo_level_success_response(
        self,
        g2p_request: AddGeoLevelRequest,
        level: GeoLevelData,
    ) -> AddGeoLevelResponse:
        return AddGeoLevelResponse(
            response_header=self._geo_write_response_header(g2p_request),
            response_body=AddGeoLevelResponseBody(
                pagination_response=None,
                response_payload=level,
            ),
        )

    def construct_add_geo_level_error_response(
        self,
        error: Exception,
        g2p_request: AddGeoLevelRequest = None,
    ) -> AddGeoLevelResponse:
        return AddGeoLevelResponse(
            response_header=self._geo_write_response_header(g2p_request, error),
            response_body=AddGeoLevelResponseBody(
                pagination_response=None,
                response_payload=None,
            ),
        )

    def construct_update_geo_level_success_response(
        self,
        g2p_request: UpdateGeoLevelRequest,
        level: GeoLevelData,
    ) -> UpdateGeoLevelResponse:
        return UpdateGeoLevelResponse(
            response_header=self._geo_write_response_header(g2p_request),
            response_body=UpdateGeoLevelResponseBody(
                pagination_response=None,
                response_payload=level,
            ),
        )

    def construct_update_geo_level_error_response(
        self,
        error: Exception,
        g2p_request: UpdateGeoLevelRequest = None,
    ) -> UpdateGeoLevelResponse:
        return UpdateGeoLevelResponse(
            response_header=self._geo_write_response_header(g2p_request, error),
            response_body=UpdateGeoLevelResponseBody(
                pagination_response=None,
                response_payload=None,
            ),
        )

    def construct_delete_geo_level_success_response(
        self,
        g2p_request: DeleteGeoLevelRequest,
        level_id: str,
    ) -> DeleteGeoLevelResponse:
        return DeleteGeoLevelResponse(
            response_header=self._geo_write_response_header(g2p_request),
            response_body=DeleteGeoLevelResponseBody(
                pagination_response=None,
                response_payload=DeleteGeoLevelResponsePayload(level_id=level_id),
            ),
        )

    def construct_delete_geo_level_error_response(
        self,
        error: Exception,
        g2p_request: DeleteGeoLevelRequest = None,
    ) -> DeleteGeoLevelResponse:
        return DeleteGeoLevelResponse(
            response_header=self._geo_write_response_header(g2p_request, error),
            response_body=DeleteGeoLevelResponseBody(
                pagination_response=None,
                response_payload=None,
            ),
        )

    def construct_add_geo_level_value_success_response(
        self,
        g2p_request: AddGeoLevelValueRequest,
        value: GeoLevelValueData,
    ) -> AddGeoLevelValueResponse:
        return AddGeoLevelValueResponse(
            response_header=self._geo_write_response_header(g2p_request),
            response_body=AddGeoLevelValueResponseBody(
                pagination_response=None,
                response_payload=value,
            ),
        )

    def construct_add_geo_level_value_error_response(
        self,
        error: Exception,
        g2p_request: AddGeoLevelValueRequest = None,
    ) -> AddGeoLevelValueResponse:
        return AddGeoLevelValueResponse(
            response_header=self._geo_write_response_header(g2p_request, error),
            response_body=AddGeoLevelValueResponseBody(
                pagination_response=None,
                response_payload=None,
            ),
        )

    def construct_update_geo_level_value_success_response(
        self,
        g2p_request: UpdateGeoLevelValueRequest,
        value: GeoLevelValueData,
    ) -> UpdateGeoLevelValueResponse:
        return UpdateGeoLevelValueResponse(
            response_header=self._geo_write_response_header(g2p_request),
            response_body=UpdateGeoLevelValueResponseBody(
                pagination_response=None,
                response_payload=value,
            ),
        )

    def construct_update_geo_level_value_error_response(
        self,
        error: Exception,
        g2p_request: UpdateGeoLevelValueRequest = None,
    ) -> UpdateGeoLevelValueResponse:
        return UpdateGeoLevelValueResponse(
            response_header=self._geo_write_response_header(g2p_request, error),
            response_body=UpdateGeoLevelValueResponseBody(
                pagination_response=None,
                response_payload=None,
            ),
        )

    def construct_delete_geo_level_value_success_response(
        self,
        g2p_request: DeleteGeoLevelValueRequest,
        level_value_id: str,
    ) -> DeleteGeoLevelValueResponse:
        return DeleteGeoLevelValueResponse(
            response_header=self._geo_write_response_header(g2p_request),
            response_body=DeleteGeoLevelValueResponseBody(
                pagination_response=None,
                response_payload=DeleteGeoLevelValueResponsePayload(level_value_id=level_value_id),
            ),
        )

    def construct_delete_geo_level_value_error_response(
        self,
        error: Exception,
        g2p_request: DeleteGeoLevelValueRequest = None,
    ) -> DeleteGeoLevelValueResponse:
        return DeleteGeoLevelValueResponse(
            response_header=self._geo_write_response_header(g2p_request, error),
            response_body=DeleteGeoLevelValueResponseBody(
                pagination_response=None,
                response_payload=None,
            ),
        )

    def construct_add_attribute_success_response(
        self,
        g2p_request: AddAttributeRequest,
        attribute: AttributeData,
    ) -> AddAttributeResponse:
        return AddAttributeResponse(
            response_header=self._attribute_response_header(g2p_request),
            response_body=AddAttributeResponseBody(
                pagination_response=None,
                response_payload=attribute,
            ),
        )

    def construct_add_attribute_error_response(
        self,
        error: Exception,
        g2p_request: AddAttributeRequest = None,
    ) -> AddAttributeResponse:
        return AddAttributeResponse(
            response_header=self._attribute_response_header(g2p_request, error),
            response_body=AddAttributeResponseBody(
                pagination_response=None,
                response_payload=None,
            ),
        )

    def construct_update_attribute_success_response(
        self,
        g2p_request: UpdateAttributeRequest,
        attribute: AttributeData,
    ) -> UpdateAttributeResponse:
        return UpdateAttributeResponse(
            response_header=self._attribute_response_header(g2p_request),
            response_body=UpdateAttributeResponseBody(
                pagination_response=None,
                response_payload=attribute,
            ),
        )

    def construct_update_attribute_error_response(
        self,
        error: Exception,
        g2p_request: UpdateAttributeRequest = None,
    ) -> UpdateAttributeResponse:
        return UpdateAttributeResponse(
            response_header=self._attribute_response_header(g2p_request, error),
            response_body=UpdateAttributeResponseBody(
                pagination_response=None,
                response_payload=None,
            ),
        )

    def construct_delete_attribute_success_response(
        self,
        g2p_request: DeleteAttributeRequest,
        attribute_id: str,
    ) -> DeleteAttributeResponse:
        return DeleteAttributeResponse(
            response_header=self._attribute_response_header(g2p_request),
            response_body=DeleteAttributeResponseBody(
                pagination_response=None,
                response_payload=DeleteAttributeResponsePayload(attribute_id=attribute_id),
            ),
        )

    def construct_delete_attribute_error_response(
        self,
        error: Exception,
        g2p_request: DeleteAttributeRequest = None,
    ) -> DeleteAttributeResponse:
        return DeleteAttributeResponse(
            response_header=self._attribute_response_header(g2p_request, error),
            response_body=DeleteAttributeResponseBody(
                pagination_response=None,
                response_payload=None,
            ),
        )

    def construct_add_attribute_value_success_response(
        self,
        g2p_request: AddAttributeValueRequest,
        value: AttributeValueData,
    ) -> AddAttributeValueResponse:
        return AddAttributeValueResponse(
            response_header=self._attribute_response_header(g2p_request),
            response_body=AddAttributeValueResponseBody(
                pagination_response=None,
                response_payload=value,
            ),
        )

    def construct_add_attribute_value_error_response(
        self,
        error: Exception,
        g2p_request: AddAttributeValueRequest = None,
    ) -> AddAttributeValueResponse:
        return AddAttributeValueResponse(
            response_header=self._attribute_response_header(g2p_request, error),
            response_body=AddAttributeValueResponseBody(
                pagination_response=None,
                response_payload=None,
            ),
        )

    def construct_update_attribute_value_success_response(
        self,
        g2p_request: UpdateAttributeValueRequest,
        value: AttributeValueData,
    ) -> UpdateAttributeValueResponse:
        return UpdateAttributeValueResponse(
            response_header=self._attribute_response_header(g2p_request),
            response_body=UpdateAttributeValueResponseBody(
                pagination_response=None,
                response_payload=value,
            ),
        )

    def construct_update_attribute_value_error_response(
        self,
        error: Exception,
        g2p_request: UpdateAttributeValueRequest = None,
    ) -> UpdateAttributeValueResponse:
        return UpdateAttributeValueResponse(
            response_header=self._attribute_response_header(g2p_request, error),
            response_body=UpdateAttributeValueResponseBody(
                pagination_response=None,
                response_payload=None,
            ),
        )

    def construct_delete_attribute_value_success_response(
        self,
        g2p_request: DeleteAttributeValueRequest,
        value_id: str,
        attribute_id: Optional[str] = None,
    ) -> DeleteAttributeValueResponse:
        return DeleteAttributeValueResponse(
            response_header=self._attribute_response_header(g2p_request),
            response_body=DeleteAttributeValueResponseBody(
                pagination_response=None,
                response_payload=DeleteAttributeValueResponsePayload(
                    value_id=value_id,
                    attribute_id=attribute_id,
                ),
            ),
        )

    def construct_delete_attribute_value_error_response(
        self,
        error: Exception,
        g2p_request: DeleteAttributeValueRequest = None,
    ) -> DeleteAttributeValueResponse:
        return DeleteAttributeValueResponse(
            response_header=self._attribute_response_header(g2p_request, error),
            response_body=DeleteAttributeValueResponseBody(
                pagination_response=None,
                response_payload=None,
            ),
        )
