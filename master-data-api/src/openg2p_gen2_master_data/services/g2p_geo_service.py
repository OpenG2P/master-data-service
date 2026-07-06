import logging
from typing import List, Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from openg2p_fastapi_common.service import BaseService

from ..engine import get_registry_session_maker, get_session_maker
from ..models import G2PGeoLevel, G2PGeoLevelValue
from ..repositories import GeoLevelValuePolicyRepository
from ..schemas import (
    GeoLevelData,
    GeoLevelValueData,
)
from .g2p_data_policy_service import G2PDataPolicyService

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
        self._geo_policy_repo = GeoLevelValuePolicyRepository()

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
                )
                for level in levels
            ]

    async def get_geo_level_values(
        self,
        level_id: str,
        parent_level_value_id: Optional[str] = None,
        policy_mnemonics: Optional[list[str]] = None,
    ) -> List[GeoLevelValueData]:
        """
        Get geo level values for a specific level, optionally filtered by parent_level_value_id.

        Args:
            level_id: The level ID to get values for
            parent_level_value_id: Optional parent level value ID to filter by
            policy_mnemonics: DP_ policy mnemonics from the authenticated user token

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

            policy_condition = await self._build_geo_level_value_policy_condition(
                policy_mnemonics,
                session,
                level_mnemonic=level.level_mnemonic,
            )

            if policy_condition is not None:
                query = query.where(policy_condition)

            values = (await session.execute(query)).scalars().all()

            return [
                GeoLevelValueData(
                    level_value_id=value.level_value_id,
                    level_id=value.level_id,
                    level_value_mnemonic=value.level_value_mnemonic,
                    parent_level_value_id=value.parent_level_value_id,
                )
                for value in values
            ]

    async def _build_geo_level_value_policy_condition(
        self,
        policy_mnemonics: list[str] | None,
        session: AsyncSession,
        *,
        level_mnemonic: str,
    ):
        """Resolve GEO policy and translate it for ``g2p_geo_level_values`` rows."""
        if not policy_mnemonics:
            return None

        async with get_registry_session_maker()() as registry_session:
            merged_expression = await G2PDataPolicyService.get_component().resolve_geo_policy(
                policy_mnemonics, registry_session
            )

        if not merged_expression:
            return None

        allowed_subtree_ids = await self._geo_policy_repo.resolve_allowed_subtree_ids(
            session, merged_expression
        )
        return self._geo_policy_repo.build_policy_condition(
            merged_expression,
            level_mnemonic=level_mnemonic,
            allowed_subtree_ids=allowed_subtree_ids,
        )
