import logging
import uuid
from typing import List, Optional

from openg2p_fastapi_common.context import get_async_session_maker
from openg2p_fastapi_common.service import BaseService
from sqlalchemy import delete, func, or_, select

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

    async def _mnemonic_exists(
        self,
        session,
        level_mnemonic: str,
        parent_level_id: Optional[str] = None,
        exclude_level_id: Optional[str] = None,
    ) -> bool:
        query = (
            select(func.count()).select_from(G2PGeoLevel).where(G2PGeoLevel.level_mnemonic == level_mnemonic)
        )
        if parent_level_id is not None:
            query = query.where(G2PGeoLevel.parent_level_id == parent_level_id)
        else:
            query = query.where(G2PGeoLevel.parent_level_id.is_(None))
        if exclude_level_id:
            query = query.where(G2PGeoLevel.level_id != exclude_level_id)
        return (await session.execute(query)).scalar_one() > 0

    async def _value_mnemonic_exists(
        self,
        session,
        level_id: str,
        level_value_mnemonic: str,
        parent_level_value_id: Optional[str] = None,
        exclude_level_value_id: Optional[str] = None,
    ) -> bool:
        query = (
            select(func.count())
            .select_from(G2PGeoLevelValue)
            .where(
                G2PGeoLevelValue.level_id == level_id,
                G2PGeoLevelValue.level_value_mnemonic == level_value_mnemonic,
            )
        )
        if parent_level_value_id is not None:
            query = query.where(G2PGeoLevelValue.parent_level_value_id == parent_level_value_id)
        else:
            query = query.where(G2PGeoLevelValue.parent_level_value_id.is_(None))
        if exclude_level_value_id:
            query = query.where(G2PGeoLevelValue.level_value_id != exclude_level_value_id)
        return (await session.execute(query)).scalar_one() > 0

    async def add_geo_level(
        self,
        *,
        level_mnemonic: str,
        parent_level_id: Optional[str] = None,
    ) -> GeoLevelData:
        level_mnemonic = level_mnemonic.strip()
        if not level_mnemonic:
            raise GeoServiceError("G2P-GEO-400", "level_mnemonic is required")

        parent_level_id = self._empty_to_none(parent_level_id)

        session_maker = get_async_session_maker()
        async with session_maker() as session:
            if await self._mnemonic_exists(session, level_mnemonic, parent_level_id):
                raise GeoServiceError(
                    "G2P-GEO-409",
                    f"level_mnemonic already exists with this parent: {level_mnemonic}",
                )

            if parent_level_id:
                parent = await session.get(G2PGeoLevel, parent_level_id)
                if not parent:
                    raise GeoServiceError(
                        "G2P-GEO-404",
                        f"parent_level_id not found: {parent_level_id}",
                    )

            level = G2PGeoLevel(
                level_id=str(uuid.uuid4()),
                level_mnemonic=level_mnemonic,
                parent_level_id=parent_level_id,
            )
            session.add(level)
            await session.commit()
            await session.refresh(level)
            return self._to_level_data(level)

    async def update_geo_level(self, payload) -> GeoLevelData:
        session_maker = get_async_session_maker()
        async with session_maker() as session:
            level = await session.get(G2PGeoLevel, payload.level_id)
            if not level:
                raise GeoServiceError("G2P-GEO-404", f"level_id not found: {payload.level_id}")

            fields_set = payload.model_fields_set
            updatable = fields_set - {"level_id"}
            if not updatable:
                raise GeoServiceError("G2P-GEO-400", "At least one field must be provided to update")

            if "level_mnemonic" in fields_set:
                level_mnemonic = (payload.level_mnemonic or "").strip()
                if not level_mnemonic:
                    raise GeoServiceError("G2P-GEO-400", "level_mnemonic cannot be empty")
                # Get the current parent_level_id (either from payload or existing level)
                parent_level_id = level.parent_level_id
                if "parent_level_id" in fields_set:
                    parent_level_id = self._empty_to_none(payload.parent_level_id)
                if await self._mnemonic_exists(
                    session, level_mnemonic, parent_level_id, exclude_level_id=payload.level_id
                ):
                    raise GeoServiceError(
                        "G2P-GEO-409",
                        f"level_mnemonic already exists with this parent: {level_mnemonic}",
                    )
                level.level_mnemonic = level_mnemonic

            if "parent_level_id" in fields_set:
                parent_level_id = self._empty_to_none(payload.parent_level_id)
                if parent_level_id == payload.level_id:
                    raise GeoServiceError("G2P-GEO-400", "level cannot be its own parent")
                if parent_level_id:
                    parent = await session.get(G2PGeoLevel, parent_level_id)
                    if not parent:
                        raise GeoServiceError(
                            "G2P-GEO-404",
                            f"parent_level_id not found: {parent_level_id}",
                        )
                level.parent_level_id = parent_level_id

            await session.commit()
            await session.refresh(level)
            return self._to_level_data(level)

    async def delete_geo_level(self, level_id: str) -> str:
        session_maker = get_async_session_maker()
        async with session_maker() as session:
            level = await session.get(G2PGeoLevel, level_id)
            if not level:
                raise GeoServiceError("G2P-GEO-404", f"level_id not found: {level_id}")

            child_levels = (
                await session.execute(
                    select(func.count())
                    .select_from(G2PGeoLevel)
                    .where(G2PGeoLevel.parent_level_id == level_id)
                )
            ).scalar_one()
            if child_levels:
                raise GeoServiceError(
                    "G2P-GEO-409",
                    f"Cannot delete level with {child_levels} child level(s)",
                )

            child_values = (
                await session.execute(
                    select(func.count())
                    .select_from(G2PGeoLevelValue)
                    .where(G2PGeoLevelValue.level_id == level_id)
                )
            ).scalar_one()
            if child_values:
                raise GeoServiceError(
                    "G2P-GEO-409",
                    f"Cannot delete level with {child_values} level value(s)",
                )

            await session.delete(level)
            await session.commit()
            return level_id

    async def add_geo_level_value(
        self,
        *,
        level_id: str,
        level_value_mnemonic: str,
        parent_level_value_id: Optional[str] = None,
    ) -> GeoLevelValueData:
        level_value_mnemonic = level_value_mnemonic.strip()
        if not level_id or not level_id.strip():
            raise GeoServiceError("G2P-GEO-400", "level_id is required")
        if not level_value_mnemonic:
            raise GeoServiceError("G2P-GEO-400", "level_value_mnemonic is required")

        parent_level_value_id = self._empty_to_none(parent_level_value_id)

        session_maker = get_async_session_maker()
        async with session_maker() as session:
            level = await session.get(G2PGeoLevel, level_id)
            if not level:
                raise GeoServiceError("G2P-GEO-404", f"level_id not found: {level_id}")

            if await self._value_mnemonic_exists(
                session, level_id, level_value_mnemonic, parent_level_value_id
            ):
                raise GeoServiceError(
                    "G2P-GEO-409",
                    f"level_value_mnemonic already exists with this parent and level: {level_value_mnemonic}",
                )

            if parent_level_value_id:
                parent_value = await session.get(G2PGeoLevelValue, parent_level_value_id)
                if not parent_value:
                    raise GeoServiceError(
                        "G2P-GEO-404",
                        f"parent_level_value_id not found: {parent_level_value_id}",
                    )

            value = G2PGeoLevelValue(
                level_value_id=str(uuid.uuid4()),
                level_id=level_id,
                level_value_mnemonic=level_value_mnemonic,
                parent_level_value_id=parent_level_value_id,
            )
            session.add(value)
            await session.commit()
            await session.refresh(value)
            return self._to_value_data(value)

    async def update_geo_level_value(self, payload) -> GeoLevelValueData:
        session_maker = get_async_session_maker()
        async with session_maker() as session:
            value = await session.get(G2PGeoLevelValue, payload.level_value_id)
            if not value:
                raise GeoServiceError(
                    "G2P-GEO-404",
                    f"level_value_id not found: {payload.level_value_id}",
                )

            fields_set = payload.model_fields_set
            updatable = fields_set - {"level_value_id"}
            if not updatable:
                raise GeoServiceError("G2P-GEO-400", "At least one field must be provided to update")

            if "level_id" in fields_set:
                level_id = (payload.level_id or "").strip()
                if not level_id:
                    raise GeoServiceError("G2P-GEO-400", "level_id cannot be empty")
                level = await session.get(G2PGeoLevel, level_id)
                if not level:
                    raise GeoServiceError("G2P-GEO-404", f"level_id not found: {level_id}")
                value.level_id = level_id

            if "level_value_mnemonic" in fields_set:
                level_value_mnemonic = (payload.level_value_mnemonic or "").strip()
                if not level_value_mnemonic:
                    raise GeoServiceError("G2P-GEO-400", "level_value_mnemonic cannot be empty")
                # Get the current parent_level_value_id (either from payload or existing value)
                parent_level_value_id = value.parent_level_value_id
                if "parent_level_value_id" in fields_set:
                    parent_level_value_id = self._empty_to_none(payload.parent_level_value_id)
                if await self._value_mnemonic_exists(
                    session,
                    value.level_id,
                    level_value_mnemonic,
                    parent_level_value_id,
                    exclude_level_value_id=payload.level_value_id,
                ):
                    raise GeoServiceError(
                        "G2P-GEO-409",
                        f"level_value_mnemonic already exists with this parent and level: {level_value_mnemonic}",
                    )
                value.level_value_mnemonic = level_value_mnemonic

            if "parent_level_value_id" in fields_set:
                parent_level_value_id = self._empty_to_none(payload.parent_level_value_id)
                if parent_level_value_id == payload.level_value_id:
                    raise GeoServiceError("G2P-GEO-400", "level value cannot be its own parent")
                if parent_level_value_id:
                    parent_value = await session.get(G2PGeoLevelValue, parent_level_value_id)
                    if not parent_value:
                        raise GeoServiceError(
                            "G2P-GEO-404",
                            f"parent_level_value_id not found: {parent_level_value_id}",
                        )
                value.parent_level_value_id = parent_level_value_id

            await session.commit()
            await session.refresh(value)
            return self._to_value_data(value)

    async def delete_geo_level_value(
        self,
        level_value_id: str,
        *,
        cascade: bool = False,
    ) -> str:
        session_maker = get_async_session_maker()
        async with session_maker() as session:
            value = await session.get(G2PGeoLevelValue, level_value_id)
            if not value:
                raise GeoServiceError(
                    "G2P-GEO-404",
                    f"level_value_id not found: {level_value_id}",
                )

            descendants: list[str] = []
            frontier = [level_value_id]
            seen = {level_value_id}
            while frontier:
                child_ids = list(
                    (
                        await session.execute(
                            select(G2PGeoLevelValue.level_value_id).where(
                                G2PGeoLevelValue.parent_level_value_id.in_(frontier)
                            )
                        )
                    ).scalars()
                )
                frontier = [child_id for child_id in child_ids if child_id not in seen]
                seen.update(frontier)
                descendants.extend(frontier)

            if descendants and not cascade:
                raise GeoServiceError(
                    "G2P-GEO-409",
                    f"Cannot delete level value with {len(descendants)} descendant value(s)",
                )

            await session.execute(
                delete(G2PGeoLevelValue).where(
                    G2PGeoLevelValue.level_value_id.in_([*descendants, level_value_id])
                )
            )
            await session.commit()
            return level_value_id
