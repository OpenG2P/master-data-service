import logging
import uuid
from datetime import date
from typing import Any, Dict, List, Optional

from sqlalchemy import func, or_, select
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
            display_name=level.display_name,
            display_name_i18n=level.display_name_i18n,
            version=level.version,
            valid_from=level.valid_from,
            valid_to=level.valid_to,
        )

    @staticmethod
    def _to_value_data(value: G2PGeoLevelValue) -> GeoLevelValueData:
        return GeoLevelValueData(
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
        async with get_session_maker()() as session:
            query = select(G2PGeoLevel)
            levels = (await session.execute(query)).scalars().all()
            return [self._to_level_data(level) for level in levels]

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
                # Fall back to the level's NAME. Callers hand-configure this —
                # a form's geo dropdown is written by whoever built the form —
                # and "region" is what they reach for, not "l1". Failing that by
                # returning an empty list is the worst possible outcome: an empty
                # dropdown looks exactly like a country with no regions, so the
                # mistake surfaces as missing data rather than as an error.
                level = (
                    await session.execute(
                        select(G2PGeoLevel).where(G2PGeoLevel.level_mnemonic == level_id)
                    )
                ).scalars().first()
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

            values = (await session.execute(query)).scalars().all()
            return [self._to_value_data(value) for value in values]

    async def _mnemonic_exists(
        self,
        session,
        level_mnemonic: str,
        exclude_level_id: Optional[str] = None,
    ) -> bool:
        query = select(func.count()).select_from(G2PGeoLevel).where(
            G2PGeoLevel.level_mnemonic == level_mnemonic
        )
        if exclude_level_id:
            query = query.where(G2PGeoLevel.level_id != exclude_level_id)
        return (await session.execute(query)).scalar_one() > 0

    async def add_geo_level(
        self,
        *,
        level_mnemonic: str,
        parent_level_id: Optional[str] = None,
        display_name: Optional[str] = None,
        display_name_i18n: Optional[Dict[str, Any]] = None,
        version: Optional[str] = None,
        valid_from: Optional[date] = None,
        valid_to: Optional[date] = None,
    ) -> GeoLevelData:
        level_mnemonic = level_mnemonic.strip()
        if not level_mnemonic:
            raise GeoServiceError("G2P-GEO-400", "level_mnemonic is required")

        parent_level_id = self._empty_to_none(parent_level_id)

        async with get_session_maker()() as session:
            if await self._mnemonic_exists(session, level_mnemonic):
                raise GeoServiceError(
                    "G2P-GEO-409",
                    f"level_mnemonic already exists: {level_mnemonic}",
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
                display_name=display_name,
                display_name_i18n=display_name_i18n,
                version=version,
                valid_from=valid_from,
                valid_to=valid_to,
            )
            session.add(level)
            await session.commit()
            await session.refresh(level)
            return self._to_level_data(level)

    async def update_geo_level(self, payload) -> GeoLevelData:
        async with get_session_maker()() as session:
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
                if await self._mnemonic_exists(
                    session, level_mnemonic, exclude_level_id=payload.level_id
                ):
                    raise GeoServiceError(
                        "G2P-GEO-409",
                        f"level_mnemonic already exists: {level_mnemonic}",
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

            if "display_name" in fields_set:
                level.display_name = payload.display_name
            if "display_name_i18n" in fields_set:
                level.display_name_i18n = payload.display_name_i18n
            if "version" in fields_set:
                level.version = payload.version
            if "valid_from" in fields_set:
                level.valid_from = payload.valid_from
            if "valid_to" in fields_set:
                level.valid_to = payload.valid_to

            await session.commit()
            await session.refresh(level)
            return self._to_level_data(level)

    async def delete_geo_level(self, level_id: str) -> str:
        async with get_session_maker()() as session:
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
        pcode: Optional[str] = None,
        pcode_source: Optional[str] = None,
        boundary_uri: Optional[str] = None,
        boundary_simplified_uri: Optional[str] = None,
        display_name: Optional[str] = None,
        display_name_i18n: Optional[Dict[str, Any]] = None,
        version: Optional[str] = None,
        valid_from: Optional[date] = None,
        valid_to: Optional[date] = None,
    ) -> GeoLevelValueData:
        level_value_mnemonic = level_value_mnemonic.strip()
        if not level_id or not level_id.strip():
            raise GeoServiceError("G2P-GEO-400", "level_id is required")
        if not level_value_mnemonic:
            raise GeoServiceError("G2P-GEO-400", "level_value_mnemonic is required")

        parent_level_value_id = self._empty_to_none(parent_level_value_id)

        async with get_session_maker()() as session:
            level = await session.get(G2PGeoLevel, level_id)
            if not level:
                raise GeoServiceError("G2P-GEO-404", f"level_id not found: {level_id}")

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
                pcode=pcode,
                pcode_source=pcode_source,
                boundary_uri=boundary_uri,
                boundary_simplified_uri=boundary_simplified_uri,
                display_name=display_name,
                display_name_i18n=display_name_i18n,
                version=version,
                valid_from=valid_from,
                valid_to=valid_to,
            )
            session.add(value)
            await session.commit()
            await session.refresh(value)
            return self._to_value_data(value)

    async def update_geo_level_value(self, payload) -> GeoLevelValueData:
        async with get_session_maker()() as session:
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

            if "pcode" in fields_set:
                value.pcode = payload.pcode
            if "pcode_source" in fields_set:
                value.pcode_source = payload.pcode_source
            if "boundary_uri" in fields_set:
                value.boundary_uri = payload.boundary_uri
            if "boundary_simplified_uri" in fields_set:
                value.boundary_simplified_uri = payload.boundary_simplified_uri
            if "display_name" in fields_set:
                value.display_name = payload.display_name
            if "display_name_i18n" in fields_set:
                value.display_name_i18n = payload.display_name_i18n
            if "version" in fields_set:
                value.version = payload.version
            if "valid_from" in fields_set:
                value.valid_from = payload.valid_from
            if "valid_to" in fields_set:
                value.valid_to = payload.valid_to

            await session.commit()
            await session.refresh(value)
            return self._to_value_data(value)

    async def delete_geo_level_value(self, level_value_id: str) -> str:
        async with get_session_maker()() as session:
            value = await session.get(G2PGeoLevelValue, level_value_id)
            if not value:
                raise GeoServiceError(
                    "G2P-GEO-404",
                    f"level_value_id not found: {level_value_id}",
                )

            child_values = (
                await session.execute(
                    select(func.count())
                    .select_from(G2PGeoLevelValue)
                    .where(G2PGeoLevelValue.parent_level_value_id == level_value_id)
                )
            ).scalar_one()
            if child_values:
                raise GeoServiceError(
                    "G2P-GEO-409",
                    f"Cannot delete level value with {child_values} child value(s)",
                )

            await session.delete(value)
            await session.commit()
            return level_value_id
