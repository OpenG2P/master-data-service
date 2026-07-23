import logging
from typing import List, Optional

from sqlalchemy import or_, select
from openg2p_fastapi_common.service import BaseService

from ..engine import get_session_maker
from ..models import G2PGeoLevel, G2PGeoLevelValue
from ..schemas import (
    GeoLevelData,
    GeoLevelValueData,
)

_config = None
try:
    from ..config import Settings

    _config = Settings.get_config()
except Exception:
    pass

_logger = logging.getLogger(_config.logging_default_logger_name if _config else "g2p-geo-service")


class G2PGeoService(BaseService):
    def __init__(self) -> None:
        super().__init__()

    async def get_geo_levels(self, parent_level_id: Optional[str] = None) -> List[GeoLevelData]:
        """
        Get geo levels, optionally filtered by parent_level_id.

        Args:
            parent_level_id: Optional parent level ID to filter by

        Returns:
            List of GeoLevelData
        """
        async with get_session_maker()() as session:
            query = select(G2PGeoLevel)

            if parent_level_id is not None and parent_level_id != "":
                query = query.where(G2PGeoLevel.parent_level_id == parent_level_id)
            else:
                # Get top-level entries with null parent_level_id
                query = query.where(G2PGeoLevel.parent_level_id.is_(None))

            levels = (await session.execute(query)).scalars().all()

            return [
                GeoLevelData(
                    level_id=level.level_id,
                    level_mnemonic=level.level_mnemonic,
                    parent_level_id=level.parent_level_id,
                    display_name=level.display_name,
                    display_name_i18n=level.display_name_i18n,
                    version=level.version,
                    valid_from=level.valid_from,
                    valid_to=level.valid_to,
                )
                for level in levels
            ]

    async def get_all_geo_levels(self) -> List[GeoLevelData]:
        """
        Get all geo levels with their parent level IDs.

        Returns:
            List of GeoLevelData
        """
        async with get_session_maker()() as session:
            query = select(G2PGeoLevel)
            levels = (await session.execute(query)).scalars().all()

            return [
                GeoLevelData(
                    level_id=level.level_id,
                    level_mnemonic=level.level_mnemonic,
                    parent_level_id=level.parent_level_id,
                    display_name=level.display_name,
                    display_name_i18n=level.display_name_i18n,
                    version=level.version,
                    valid_from=level.valid_from,
                    valid_to=level.valid_to,
                )
                for level in levels
            ]

    async def get_geo_level_values(
        self,
        level_id: str,
        parent_level_value_id: Optional[str] = None,
    ) -> List[GeoLevelValueData]:
        """
        Get geo level values for a specific level, optionally filtered by parent_level_value_id.

        Args:
            level_id: The level ID to get values for
            parent_level_value_id: Optional parent level value ID to filter by

        Returns:
            List of GeoLevelValueData
        """
        async with get_session_maker()() as session:
            level = await session.get(G2PGeoLevel, level_id)
            if not level:
                return []

            query = select(G2PGeoLevelValue).where(G2PGeoLevelValue.level_id == level_id)

            if parent_level_value_id is not None and parent_level_value_id != "":
                query = query.where(G2PGeoLevelValue.parent_level_value_id == parent_level_value_id)
            else:
                # Get top-level entries with null parent_level_value_id
                query = query.where(
                    or_(
                        G2PGeoLevelValue.parent_level_value_id.is_(None),
                        G2PGeoLevelValue.parent_level_value_id == "NULL",
                        G2PGeoLevelValue.parent_level_value_id == "",
                    )
                )

            values = (await session.execute(query)).scalars().all()

            return [
                GeoLevelValueData(
                    level_value_id=value.level_value_id,
                    level_id=value.level_id,
                    level_value_mnemonic=value.level_value_mnemonic,
                    parent_level_value_id=value.parent_level_value_id,
                    pcode=value.pcode,
                    pcode_source=value.pcode_source,
                    boundary_uri=value.boundary_uri,
                    boundary_simplified_uri=value.boundary_simplified_uri,
                    display_name=value.display_name,
                    display_name_i18n=value.display_name_i18n,
                    version=value.version,
                    valid_from=value.valid_from,
                    valid_to=value.valid_to,
                )
                for value in values
            ]
