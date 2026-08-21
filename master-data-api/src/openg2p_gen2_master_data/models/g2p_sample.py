from datetime import date

from openg2p_fastapi_common.models import BaseORMModel
from sqlalchemy import Date, Float, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

# ---------------------------------------------------------------------------
# Sample people, from the country pack.
#
# Sample data is the one kind of demo data that MUST be country-coherent: a
# reviewer opening the registry reads the names, and Ethiopian given-name +
# father's-name in a real Tigray woreda either looks right or does not. Bulk
# analytics data has no such requirement, which is why only this lives here.
#
# It lives in Master Data because the country is declared exactly once, here. A
# registry that shipped its own sample people would be declaring a country of
# its own, and the two could then disagree.
#
# What a registry stores is NOT this shape. These are the shared, cross-registry
# facts — who someone is, where they live. A registry reads them and adds its own
# fields, so one set of sample people populates a social registry and a farmer
# registry as the same people.
#
# Everything here is additive and stays empty unless a deployment asks for
# `--load samples`.
# ---------------------------------------------------------------------------


class G2PSampleIndividual(BaseORMModel):
    __tablename__ = "g2p_sample_individuals"

    individual_id: Mapped[str] = mapped_column(String, primary_key=True)
    household_id: Mapped[str] = mapped_column(String, nullable=True, index=True)

    given_name: Mapped[str] = mapped_column(String, nullable=True)
    fathers_name: Mapped[str] = mapped_column(String, nullable=True)
    full_name: Mapped[str] = mapped_column(String, nullable=True)

    # Codes, not labels — they are values of this pack's own code lists, so a
    # consumer resolves them through g2p_attribute_values like any other value.
    gender: Mapped[str] = mapped_column(String, nullable=True)
    relationship_to_head: Mapped[str] = mapped_column(String, nullable=True)
    marital_status: Mapped[str] = mapped_column(String, nullable=True)
    education_level: Mapped[str] = mapped_column(String, nullable=True)
    employment_status: Mapped[str] = mapped_column(String, nullable=True)
    disability_status: Mapped[str] = mapped_column(String, nullable=True)

    # The full date. birth_year and age are kept because existing packs carry
    # them and registries seeded from them for a release — but a registry's own
    # column is a DATE, so before this every sample person was given 1 January by
    # whichever loader got to them, and every birthday chart showed one January
    # spike. The pack now says which day it is.
    birth_date: Mapped[date] = mapped_column(Date, nullable=True)
    birth_year: Mapped[int] = mapped_column(Integer, nullable=True)
    age: Mapped[int] = mapped_column(Integer, nullable=True)
    phone: Mapped[str] = mapped_column(String, nullable=True)
    national_id: Mapped[str] = mapped_column(String, nullable=True)

    # The unit's own id in g2p_geo_level_values — a P-code for a real pack. The
    # administrative chain is NOT repeated as text; it is derivable from this.
    geo_pcode: Mapped[str] = mapped_column(String, nullable=True, index=True)
    # What is written BELOW the lowest administrative level, keyed by the
    # sub-level ids the pack's address.json declares (kebele, house_number).
    address_parts: Mapped[dict] = mapped_column(JSONB, nullable=True)
    latitude: Mapped[float] = mapped_column(Float, nullable=True)
    longitude: Mapped[float] = mapped_column(Float, nullable=True)

    country: Mapped[str] = mapped_column(String, nullable=True, index=True)
    version: Mapped[str] = mapped_column(String, nullable=True)


class G2PSampleHousehold(BaseORMModel):
    __tablename__ = "g2p_sample_households"

    household_id: Mapped[str] = mapped_column(String, primary_key=True)
    head_individual_id: Mapped[str] = mapped_column(String, nullable=True, index=True)
    headship_type: Mapped[str] = mapped_column(String, nullable=True)
    size_total: Mapped[int] = mapped_column(Integer, nullable=True)

    dwelling_type: Mapped[str] = mapped_column(String, nullable=True)
    tenure_status: Mapped[str] = mapped_column(String, nullable=True)
    water_source_type: Mapped[str] = mapped_column(String, nullable=True)
    sanitation_type: Mapped[str] = mapped_column(String, nullable=True)
    lighting_source: Mapped[str] = mapped_column(String, nullable=True)
    cooking_fuel_type: Mapped[str] = mapped_column(String, nullable=True)

    geo_pcode: Mapped[str] = mapped_column(String, nullable=True, index=True)
    address_parts: Mapped[dict] = mapped_column(JSONB, nullable=True)
    latitude: Mapped[float] = mapped_column(Float, nullable=True)
    longitude: Mapped[float] = mapped_column(Float, nullable=True)

    country: Mapped[str] = mapped_column(String, nullable=True, index=True)
    version: Mapped[str] = mapped_column(String, nullable=True)
