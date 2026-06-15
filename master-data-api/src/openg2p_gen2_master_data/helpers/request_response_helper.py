from datetime import datetime
from typing import List, Optional
from openg2p_fastapi_common.service import BaseService
from openg2p_fastapi_common.schemas import G2PResponseHeader, G2PResponseStatus

from ..schemas import (
    GeoLevelData,
    GetGeoLevelsRequest,
    GetGeoLevelsResponse,
    GetGeoLevelsResponseBody,
    GeoLevelValueData,
    GetGeoLevelValuesRequest,
    GetGeoLevelValuesResponse,
    GetGeoLevelValuesResponseBody,
    GetAllPartnersRequest,
    G2PPartnersResponse,
    G2PPartnersResponseBody,
    GetPartnerRequest,
    G2PPartnerResponse,
    G2PPartnerResponseBody,
    G2PPartnerData,
)


class RequestResponseHelper(BaseService):
    def construct_geo_levels_success_response(
        self,
        g2p_request: GetGeoLevelsRequest,
        levels: List[GeoLevelData],
    ) -> GetGeoLevelsResponse:
        """
        Construct a success response for get_g2p_geo_levels API.

        Args:
            g2p_request: The G2P request object
            levels: List of geo level data to return

        Returns:
            GetGeoLevelsResponse with success status
        """
        request_id = g2p_request.request_header.request_id if g2p_request.request_header else ""

        response_header = G2PResponseHeader(
            request_id=request_id,
            response_status=G2PResponseStatus.SUCCESS,
            response_error_code="",
            response_error_message="",
            response_timestamp=datetime.now(),
        )

        response_body = GetGeoLevelsResponseBody(
            pagination_response=None,
            response_payload=levels,
        )

        return GetGeoLevelsResponse(
            response_header=response_header,
            response_body=response_body,
        )

    def construct_geo_levels_error_response(
        self,
        error: Exception,
        g2p_request: GetGeoLevelsRequest = None,
    ) -> GetGeoLevelsResponse:
        """
        Construct an error response for get_g2p_geo_levels API.

        Args:
            error: The exception that occurred
            g2p_request: Optional G2P request object

        Returns:
            GetGeoLevelsResponse with error status
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

        response_body = GetGeoLevelsResponseBody(
            pagination_response=None,
            response_payload=[],
        )

        return GetGeoLevelsResponse(
            response_header=response_header,
            response_body=response_body,
        )

    def construct_geo_level_values_success_response(
        self,
        g2p_request: GetGeoLevelValuesRequest,
        values: List[GeoLevelValueData],
    ) -> GetGeoLevelValuesResponse:
        """
        Construct a success response for get_g2p_geo_level_values API.

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
        Construct an error response for get_g2p_geo_level_values API.

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
