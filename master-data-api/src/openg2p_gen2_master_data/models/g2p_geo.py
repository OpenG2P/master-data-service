import uuid

from openg2p_fastapi_common.models import BaseORMModel
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

# ---------------------------------------------------------------------------
# Geo hierarchy.
#
# The hierarchy is intentionally DATA, not code: depth and level names differ
# per country (region/district/ward vs state/district/block vs
# region/province/municipality/barangay), so nothing here assumes either.
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
