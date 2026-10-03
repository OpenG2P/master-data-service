import logging
from typing import List, Optional

from openg2p_fastapi_common.context import get_async_session_maker
from openg2p_fastapi_common.service import BaseService
from sqlalchemy import or_, select

from ..helpers.data_policy_helper import DataPolicyHelper
from ..models import G2PGeoLevel, G2PGeoLevelValue
from ..repositories import GeoLevelValueRepository
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


class GeoServiceError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


class G2PGeoService(BaseService):
    def __init__(self) -> None:
        super().__init__()

    @staticmethod
    def _to_level_data(level: G2PGeoLevel) -> GeoLevelData:
        return GeoLevelData(
            level_id=level.level_id,
            level_mnemonic=level.level_mnemonic,
            parent_level_id=level.parent_level_id,
        )

    @staticmethod
    def _to_value_data(value: G2PGeoLevelValue) -> GeoLevelValueData:
        return GeoLevelValueData(
            level_value_id=value.level_value_id,
            level_id=value.level_id,
            level_value_mnemonic=value.level_value_mnemonic,
            parent_level_value_id=value.parent_level_value_id,
        )

    @staticmethod
    def _empty_to_none(value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    async def get_all_geo_levels(self) -> List[GeoLevelData]:
        """
        Get all geo levels with their parent level IDs.

        Returns:
            List of GeoLevelData
        """
        session_maker = get_async_session_maker()
        async with session_maker() as session:
            query = select(G2PGeoLevel)
            levels = (await session.execute(query)).scalars().all()
            return [self._to_level_data(level) for level in levels]

    async def get_geo_level_values(
        self,
        level_id: str,
        parent_level_value_id: Optional[str] = None,
        data_policies: Optional[List[dict]] = None,
    ) -> List[GeoLevelValueData]:
        """
        Get geo level values for a specific level, optionally filtered by parent_level_value_id.

        Args:
            level_id: The level ID to get values for
            parent_level_value_id: Optional parent level value ID to filter by
            data_policies: Optional ATTRIBUTE/GEO data policies from middleware

        Returns:
            List of GeoLevelValueData
        """
        session_maker = get_async_session_maker()
        async with session_maker() as session:
            level = await session.get(G2PGeoLevel, level_id)
            if not level:
                # Fall back to the level's NAME. Callers hand-configure this —
                # a form's geo dropdown is written by whoever built the form —
                # and "region" is what they reach for, not "l1". Failing that by
                # returning an empty list is the worst possible outcome: an empty
                # dropdown looks exactly like a country with no regions, so the
                # mistake surfaces as missing data rather than as an error.
                level = (
                    (await session.execute(select(G2PGeoLevel).where(G2PGeoLevel.level_mnemonic == level_id)))
                    .scalars()
                    .first()
                )
                if not level:
                    return []
                level_id = level.level_id

            query = select(G2PGeoLevelValue).where(G2PGeoLevelValue.level_id == level_id)

            if parent_level_value_id is not None and parent_level_value_id != "":
                query = query.where(G2PGeoLevelValue.parent_level_value_id == parent_level_value_id)
            elif level.parent_level_id:
                # A level below the root, asked for without a parent: return every
                # unit at that level.
                #
                # It used to filter on "parent is null", which for a non-root
                # level matches nothing — the country pack makes the country an
                # actual level, so regions hang off it rather than off nothing.
                # A form whose first dropdown asks for regions and passes no
                # parent therefore came back empty, which reads as a country with
                # no regions rather than as a bad request.
                pass
            else:
                # The root level itself — the units with no parent.
                query = query.where(
                    or_(
                        G2PGeoLevelValue.parent_level_value_id.is_(None),
                        G2PGeoLevelValue.parent_level_value_id == "NULL",
                        G2PGeoLevelValue.parent_level_value_id == "",
                    )
                )

            policy_condition = self._build_geo_level_value_policy_condition(
                data_policies,
                level_context=level.level_mnemonic,
            )
            if policy_condition is not None:
                query = query.where(policy_condition)

            values = (await session.execute(query)).scalars().all()
            return [self._to_value_data(value) for value in values]

    def _build_geo_level_value_policy_condition(
        self,
        data_policies: Optional[List[dict]],
        *,
        level_context: Optional[str] = None,
    ):
        """Resolve GEO policy and translate it for ``G2PGeoLevelValue`` rows."""
        if not data_policies:
            return None

        merged_expression = DataPolicyHelper.resolve_geo_policy(data_policies)
        if not merged_expression:
            return None

        return GeoLevelValueRepository().build_policy_condition(
            merged_expression,
            level_context=level_context,
        )

    # Writes moved to G2PCatalogueGeoService: the /geo write endpoints now edit
    # the open geography draft instead of the published rows.
