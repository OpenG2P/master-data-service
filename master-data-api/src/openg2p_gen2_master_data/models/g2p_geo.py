import uuid

from openg2p_fastapi_common.models import BaseORMModel
from sqlalchemy import String, UniqueConstraint
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
    __table_args__ = (UniqueConstraint("level_mnemonic", "parent_level_id", name="uq_level_mnemonic_parent"),)

    level_id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    level_mnemonic: Mapped[str] = mapped_column(String, nullable=False, index=True)
    parent_level_id: Mapped[str] = mapped_column(
        String,
        nullable=True,
        index=True,
    )


class G2PGeoLevelValue(BaseORMModel):
    __tablename__ = "g2p_geo_level_values"
    __table_args__ = (
        UniqueConstraint(
            "level_value_mnemonic", "parent_level_value_id", "level_id", name="uq_value_mnemonic_parent_level"
        ),
    )

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
