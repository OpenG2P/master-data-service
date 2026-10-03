"""Request/response models of the ``/samples`` reads.

The sample people (and households) a country pack loaded with ``--load
samples`` — the shared, cross-registry facts registries build their sample data
from. Same envelope as ``/catalogue``: ``request_header`` +
``request_body.request_payload`` (+ optional ``pagination_request``) in,
``response_header`` + ``response_body.response_payload`` (+
``pagination_response``) out; errors come back with HTTP 200 and
``response_status = ERROR``.
"""

from datetime import date
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class GetSampleIndividualsPayload(BaseModel):
    household_id: Optional[str] = Field(default=None, description="Only the members of this household.")
    geo_pcode: Optional[str] = Field(default=None, description="Only people living in this geography unit.")
    country: Optional[str] = Field(
        default=None, description="Only people of this country (pack country code)."
    )


class SampleIndividual(BaseModel):
    individual_id: str
    household_id: Optional[str] = None
    given_name: Optional[str] = None
    fathers_name: Optional[str] = None
    full_name: Optional[str] = None
    gender: Optional[str] = None
    relationship_to_head: Optional[str] = None
    marital_status: Optional[str] = None
    education_level: Optional[str] = None
    employment_status: Optional[str] = None
    disability_status: Optional[str] = None
    birth_date: Optional[date] = None
    birth_year: Optional[int] = None
    age: Optional[int] = None
    phone: Optional[str] = None
    national_id: Optional[str] = None
    geo_pcode: Optional[str] = None
    address_parts: Optional[Dict[str, Any]] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    country: Optional[str] = None
    version: Optional[str] = None


class GetSampleIndividualsResponsePayload(BaseModel):
    individuals: List[SampleIndividual] = []
    total: int = 0


class GetSampleHouseholdsPayload(BaseModel):
    geo_pcode: Optional[str] = Field(default=None, description="Only households in this geography unit.")
    country: Optional[str] = Field(default=None, description="Only households of this country.")


class SampleHousehold(BaseModel):
    household_id: str
    head_individual_id: Optional[str] = None
    headship_type: Optional[str] = None
    size_total: Optional[int] = None
    dwelling_type: Optional[str] = None
    tenure_status: Optional[str] = None
    water_source_type: Optional[str] = None
    sanitation_type: Optional[str] = None
    lighting_source: Optional[str] = None
    cooking_fuel_type: Optional[str] = None
    geo_pcode: Optional[str] = None
    address_parts: Optional[Dict[str, Any]] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    country: Optional[str] = None
    version: Optional[str] = None


class GetSampleHouseholdsResponsePayload(BaseModel):
    households: List[SampleHousehold] = []
    total: int = 0
