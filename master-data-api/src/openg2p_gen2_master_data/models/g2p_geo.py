import uuid
from datetime import date

from openg2p_fastapi_common.models import BaseORMModel
from sqlalchemy import Date, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

# ---------------------------------------------------------------------------
# Geo hierarchy.
#
# The hierarchy is intentionally DATA, not code: depth and level names differ
# per country (region/district/ward vs state/district/block vs
# region/province/municipality/barangay), so nothing here assumes either.
#
# Every column added below is nullable and additive — existing rows, existing
# API consumers and existing deployments keep working unchanged.
# ---------------------------------------------------------------------------


class G2PGeoLevel(BaseORMModel):
    __tablename__ = "g2p_geo_levels"

    level_id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    level_mnemonic: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    parent_level_id: Mapped[str] = mapped_column(
        String,
        nullable=True,
        index=True,
    )

    # Human-facing label for the LEVEL itself, so a breadcrumb can read
    # "Province" rather than the slug "province" — and be translated.
    display_name: Mapped[str] = mapped_column(String, nullable=True)
    display_name_i18n: Mapped[dict] = mapped_column(JSONB, nullable=True)

    # Structure vintage. Administrative structures change (a region splitting
    # into several is common), so reports must be able to state which version
    # they were drawn against.
    version: Mapped[str] = mapped_column(String, nullable=True, index=True)
    valid_from: Mapped[date] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date] = mapped_column(Date, nullable=True)


class G2PGeoLevelValue(BaseORMModel):
    __tablename__ = "g2p_geo_level_values"

    level_value_id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    level_id: Mapped[str] = mapped_column(
        String,
        nullable=False,
        index=True,
    )
    level_value_mnemonic: Mapped[str] = mapped_column(String, nullable=False, index=True)
    parent_level_value_id: Mapped[str] = mapped_column(
        String,
        nullable=True,
        index=True,
    )

    # ---- Join key to the outside world -----------------------------------
    # Official administrative P-code. `level_value_id` remains the stable
    # internal key; `pcode` is what boundary datasets (national statistics
    # agencies, OCHA/HDX COD-AB) and registry data key on.
    #
    # This exists because joining on NAMES is unreliable: measured against
    # real data, exact name matching reached only ~76% (91% with fuzzy
    # matching), ranged 56–94% across areas, and produced geographically
    # WRONG matches where the same name recurs under different parents.
    pcode: Mapped[str] = mapped_column(String, nullable=True, index=True)
    # Provenance matters when two sources disagree on a code.
    pcode_source: Mapped[str] = mapped_column(String, nullable=True)

    # ---- Geometry ---------------------------------------------------------
    # Pointer to this node's boundary polygon (e.g. an object-store URL). The
    # geometry itself is NOT stored here. The referenced GeoJSON MUST carry
    # the same `pcode` as a feature property — that is the join key; map
    # layers must never match on names.
    boundary_uri: Mapped[str] = mapped_column(String, nullable=True)
    # Web-optimised geometry. Full-resolution admin boundaries are far too
    # large to ship to a browser.
    boundary_simplified_uri: Mapped[str] = mapped_column(String, nullable=True)

    # ---- Presentation -----------------------------------------------------
    # `level_value_mnemonic` is a slug (e.g. "addis_ababa"); this is the
    # properly-cased, translatable label.
    display_name: Mapped[str] = mapped_column(String, nullable=True)
    display_name_i18n: Mapped[dict] = mapped_column(JSONB, nullable=True)

    # ---- Effective dating -------------------------------------------------
    version: Mapped[str] = mapped_column(String, nullable=True, index=True)
    valid_from: Mapped[date] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date] = mapped_column(Date, nullable=True)
