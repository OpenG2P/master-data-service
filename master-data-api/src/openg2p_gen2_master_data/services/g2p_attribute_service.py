import logging
import uuid
from typing import List, Optional

from openg2p_fastapi_common.context import get_async_session_maker
from openg2p_fastapi_common.service import BaseService
from sqlalchemy import delete, func, select

from ..helpers.data_policy_helper import DataPolicyHelper
from ..models import G2PAttribute, G2PAttributeValue
from ..repositories import AttributeValueRepository
from ..schemas import AttributeData, AttributeValueData

_config = None
try:
    from ..config import Settings

    _config = Settings.get_config()
except Exception:
    pass

_logger = logging.getLogger(_config.logging_default_logger_name if _config else "g2p-attribute-service")


class AttributeServiceError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


class G2PAttributeService(BaseService):
    """Reads the country's code lists."""

    def __init__(self) -> None:
        super().__init__()

    @staticmethod
    def _empty_to_none(value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @staticmethod
    def _to_attribute_data(row: G2PAttribute) -> AttributeData:
        return AttributeData(
            attribute_id=row.attribute_id,
            attribute_code=row.attribute_code,
            attribute_display=row.attribute_display,
            is_hierarchical=bool(row.is_hierarchical),
        )

    @staticmethod
    def _to_value_data(row: G2PAttributeValue) -> AttributeValueData:
        return AttributeValueData(
            attribute_id=row.attribute_id,
            value_id=row.value_id,
            value_code=row.value_code,
            value_display=row.value_display,
            parent_value_id=row.parent_value_id,
            sort_order=row.sort_order,
        )

    async def get_attributes(self) -> List[AttributeData]:
        session_maker = get_async_session_maker()
        async with session_maker() as session:
            stmt = select(G2PAttribute).order_by(G2PAttribute.attribute_id)
            rows = (await session.execute(stmt)).scalars().all()
        return [self._to_attribute_data(r) for r in rows]

    async def get_attribute_values(
        self,
        attribute_id: Optional[str] = None,
        page_size: int = 1000,
        page_number: int = 1,
        data_policies: Optional[List[dict]] = None,
    ) -> tuple[List[AttributeValueData], int]:
        session_maker = get_async_session_maker()
        async with session_maker() as session:
            policy_condition = await self._build_attribute_value_policy_condition(
                data_policies,
                session,
                attribute_id=attribute_id,
            )

            def scoped(stmt):
                if attribute_id:
                    stmt = stmt.where(G2PAttributeValue.attribute_id == attribute_id)
                if policy_condition is not None:
                    stmt = stmt.where(policy_condition)
                return stmt

            total = (
                await session.execute(scoped(select(func.count()).select_from(G2PAttributeValue)))
            ).scalar_one()
            stmt = scoped(select(G2PAttributeValue)).order_by(
                G2PAttributeValue.attribute_id, G2PAttributeValue.sort_order
            )
            stmt = stmt.limit(page_size).offset(max(0, (page_number - 1)) * page_size)
            rows = (await session.execute(stmt)).scalars().all()

        return [self._to_value_data(r) for r in rows], total

    async def _build_attribute_value_policy_condition(
        self,
        data_policies: Optional[List[dict]],
        session,
        attribute_id: Optional[str] = None,
    ):
        """Resolve ATTRIBUTE policy and translate it for ``G2PAttributeValue`` rows."""
        if not data_policies:
            return None

        merged_expression = DataPolicyHelper.resolve_attribute_policy(data_policies)
        if not merged_expression:
            return None

        attribute_context = None
        if attribute_id:
            attribute = await session.get(G2PAttribute, attribute_id)
            if attribute:
                attribute_context = attribute.attribute_code

        return AttributeValueRepository().build_policy_condition(
            merged_expression,
            attribute_context=attribute_context,
        )

    async def _attribute_code_exists(
        self,
        session,
        attribute_code: str,
        exclude_attribute_id: Optional[str] = None,
    ) -> bool:
        query = (
            select(func.count())
            .select_from(G2PAttribute)
            .where(G2PAttribute.attribute_code == attribute_code)
        )
        if exclude_attribute_id:
            query = query.where(G2PAttribute.attribute_id != exclude_attribute_id)
        return (await session.execute(query)).scalar_one() > 0

    async def _value_code_exists(
        self,
        session,
        attribute_id: str,
        value_code: str,
        exclude_value_id: Optional[str] = None,
    ) -> bool:
        query = (
            select(func.count())
            .select_from(G2PAttributeValue)
            .where(
                G2PAttributeValue.attribute_id == attribute_id,
                G2PAttributeValue.value_code == value_code,
            )
        )
        if exclude_value_id:
            query = query.where(G2PAttributeValue.value_id != exclude_value_id)
        return (await session.execute(query)).scalar_one() > 0

    async def _get_value_by_id(
        self,
        session,
        value_id: str,
        attribute_id: Optional[str] = None,
    ) -> Optional[G2PAttributeValue]:
        query = select(G2PAttributeValue).where(G2PAttributeValue.value_id == value_id)
        if attribute_id:
            query = query.where(G2PAttributeValue.attribute_id == attribute_id)
        return (await session.execute(query)).scalars().first()

    async def _validate_parent_value(
        self,
        session,
        *,
        attribute: G2PAttribute,
        attribute_id: str,
        parent_value_id: Optional[str],
        exclude_value_id: Optional[str] = None,
    ) -> None:
        if not parent_value_id:
            return

        if not attribute.is_hierarchical:
            raise AttributeServiceError(
                "G2P-ATTR-400",
                f"attribute '{attribute_id}' is not hierarchical; parent_value_id is not allowed",
            )

        if parent_value_id == exclude_value_id:
            raise AttributeServiceError("G2P-ATTR-400", "attribute value cannot be its own parent")

        parent = await self._get_value_by_id(session, parent_value_id, attribute_id)
        if not parent:
            raise AttributeServiceError(
                "G2P-ATTR-404",
                f"parent_value_id not found for attribute '{attribute_id}': {parent_value_id}",
            )

    async def add_attribute(
        self,
        *,
        attribute_code: str,
        attribute_display: str,
        is_hierarchical: bool = False,
    ) -> AttributeData:
        attribute_code = attribute_code.strip()
        attribute_display = attribute_display.strip()
        if not attribute_code or not attribute_display:
            raise AttributeServiceError(
                "G2P-ATTR-400",
                "attribute_code and attribute_display are required",
            )

        session_maker = get_async_session_maker()
        async with session_maker() as session:
            if await self._attribute_code_exists(session, attribute_code):
                raise AttributeServiceError(
                    "G2P-ATTR-409",
                    f"attribute_code already exists: {attribute_code}",
                )

            attribute = G2PAttribute(
                attribute_id=str(uuid.uuid4()),
                attribute_code=attribute_code,
                attribute_display=attribute_display,
                is_hierarchical=bool(is_hierarchical),
            )
            session.add(attribute)
            await session.commit()
            await session.refresh(attribute)
            return self._to_attribute_data(attribute)

    async def update_attribute(self, payload) -> AttributeData:
        session_maker = get_async_session_maker()
        async with session_maker() as session:
            attribute = await session.get(G2PAttribute, payload.attribute_id)
            if not attribute:
                raise AttributeServiceError(
                    "G2P-ATTR-404",
                    f"attribute_id not found: {payload.attribute_id}",
                )

            fields_set = payload.model_fields_set
            updatable = fields_set - {"attribute_id"}
            if not updatable:
                raise AttributeServiceError(
                    "G2P-ATTR-400",
                    "At least one field must be provided to update",
                )

            if "attribute_code" in fields_set:
                attribute_code = (payload.attribute_code or "").strip()
                if not attribute_code:
                    raise AttributeServiceError("G2P-ATTR-400", "attribute_code cannot be empty")
                if await self._attribute_code_exists(
                    session, attribute_code, exclude_attribute_id=payload.attribute_id
                ):
                    raise AttributeServiceError(
                        "G2P-ATTR-409",
                        f"attribute_code already exists: {attribute_code}",
                    )
                attribute.attribute_code = attribute_code

            if "attribute_display" in fields_set:
                attribute_display = (payload.attribute_display or "").strip()
                if not attribute_display:
                    raise AttributeServiceError(
                        "G2P-ATTR-400",
                        "attribute_display cannot be empty",
                    )
                attribute.attribute_display = attribute_display

            if "is_hierarchical" in fields_set:
                is_hierarchical = bool(payload.is_hierarchical)
                if not is_hierarchical:
                    hierarchical_count = (
                        await session.execute(
                            select(func.count())
                            .select_from(G2PAttributeValue)
                            .where(
                                G2PAttributeValue.attribute_id == payload.attribute_id,
                                G2PAttributeValue.parent_value_id.is_not(None),
                            )
                        )
                    ).scalar_one()
                    if hierarchical_count:
                        raise AttributeServiceError(
                            "G2P-ATTR-409",
                            (
                                f"Cannot set is_hierarchical=false for attribute "
                                f"'{payload.attribute_id}' while values have parent_value_id set"
                            ),
                        )
                attribute.is_hierarchical = is_hierarchical

            await session.commit()
            await session.refresh(attribute)
            return self._to_attribute_data(attribute)

    async def delete_attribute(
        self,
        attribute_id: str,
        *,
        cascade: bool = False,
    ) -> str:
        session_maker = get_async_session_maker()
        async with session_maker() as session:
            attribute = await session.get(G2PAttribute, attribute_id)
            if not attribute:
                raise AttributeServiceError(
                    "G2P-ATTR-404",
                    f"attribute_id not found: {attribute_id}",
                )

            value_count = (
                await session.execute(
                    select(func.count())
                    .select_from(G2PAttributeValue)
                    .where(G2PAttributeValue.attribute_id == attribute_id)
                )
            ).scalar_one()
            if value_count and not cascade:
                raise AttributeServiceError(
                    "G2P-ATTR-409",
                    f"Cannot delete attribute '{attribute_id}' while attribute values exist",
                )

            if value_count:
                await session.execute(
                    delete(G2PAttributeValue).where(G2PAttributeValue.attribute_id == attribute_id)
                )
            await session.delete(attribute)
            await session.commit()
            return attribute_id

    async def add_attribute_value(
        self,
        *,
        attribute_id: str,
        value_code: str,
        value_display: str,
        parent_value_id: Optional[str] = None,
        sort_order: Optional[int] = 0,
    ) -> AttributeValueData:
        value_code = value_code.strip()
        value_display = value_display.strip()
        if not attribute_id or not attribute_id.strip():
            raise AttributeServiceError("G2P-ATTR-400", "attribute_id is required")
        if not value_code or not value_display:
            raise AttributeServiceError(
                "G2P-ATTR-400",
                "value_code and value_display are required",
            )

        parent_value_id = self._empty_to_none(parent_value_id)

        session_maker = get_async_session_maker()
        async with session_maker() as session:
            attribute = await session.get(G2PAttribute, attribute_id)
            if not attribute:
                raise AttributeServiceError(
                    "G2P-ATTR-404",
                    f"attribute_id not found: {attribute_id}",
                )

            await self._validate_parent_value(
                session,
                attribute=attribute,
                attribute_id=attribute_id,
                parent_value_id=parent_value_id,
            )

            if await self._value_code_exists(session, attribute_id, value_code):
                raise AttributeServiceError(
                    "G2P-ATTR-409",
                    f"value_code already exists for attribute '{attribute_id}': {value_code}",
                )

            value = G2PAttributeValue(
                value_id=str(uuid.uuid4()),
                attribute_id=attribute_id,
                value_code=value_code,
                value_display=value_display,
                parent_value_id=parent_value_id,
                sort_order=0 if sort_order is None else sort_order,
            )
            session.add(value)
            await session.commit()
            await session.refresh(value)
            return self._to_value_data(value)

    async def update_attribute_value(self, payload) -> AttributeValueData:
        session_maker = get_async_session_maker()
        async with session_maker() as session:
            value = await self._get_value_by_id(
                session,
                payload.value_id,
                (
                    self._empty_to_none(payload.attribute_id)
                    if "attribute_id" in payload.model_fields_set
                    else None
                ),
            )
            if not value:
                raise AttributeServiceError(
                    "G2P-ATTR-404",
                    f"value_id not found: {payload.value_id}",
                )

            fields_set = payload.model_fields_set
            updatable = fields_set - {"value_id", "attribute_id"}
            if not updatable:
                raise AttributeServiceError(
                    "G2P-ATTR-400",
                    "At least one field must be provided to update",
                )

            attribute = await session.get(G2PAttribute, value.attribute_id)
            if not attribute:
                raise AttributeServiceError(
                    "G2P-ATTR-404",
                    f"attribute_id not found: {value.attribute_id}",
                )

            if "value_code" in fields_set:
                value_code = (payload.value_code or "").strip()
                if not value_code:
                    raise AttributeServiceError("G2P-ATTR-400", "value_code cannot be empty")
                if await self._value_code_exists(
                    session,
                    value.attribute_id,
                    value_code,
                    exclude_value_id=payload.value_id,
                ):
                    raise AttributeServiceError(
                        "G2P-ATTR-409",
                        (f"value_code already exists for attribute " f"'{value.attribute_id}': {value_code}"),
                    )
                value.value_code = value_code

            if "value_display" in fields_set:
                value_display = (payload.value_display or "").strip()
                if not value_display:
                    raise AttributeServiceError("G2P-ATTR-400", "value_display cannot be empty")
                value.value_display = value_display

            if "parent_value_id" in fields_set:
                parent_value_id = self._empty_to_none(payload.parent_value_id)
                await self._validate_parent_value(
                    session,
                    attribute=attribute,
                    attribute_id=value.attribute_id,
                    parent_value_id=parent_value_id,
                    exclude_value_id=payload.value_id,
                )
                value.parent_value_id = parent_value_id

            if "sort_order" in fields_set:
                value.sort_order = payload.sort_order

            await session.commit()
            await session.refresh(value)
            return self._to_value_data(value)

    async def delete_attribute_value(
        self,
        value_id: str,
        attribute_id: Optional[str] = None,
    ) -> tuple[str, str]:
        session_maker = get_async_session_maker()
        async with session_maker() as session:
            value = await self._get_value_by_id(session, value_id, attribute_id)
            if not value:
                raise AttributeServiceError(
                    "G2P-ATTR-404",
                    f"value_id not found: {value_id}",
                )

            child_count = (
                await session.execute(
                    select(func.count())
                    .select_from(G2PAttributeValue)
                    .where(
                        G2PAttributeValue.attribute_id == value.attribute_id,
                        G2PAttributeValue.parent_value_id == value_id,
                    )
                )
            ).scalar_one()
            if child_count:
                raise AttributeServiceError(
                    "G2P-ATTR-409",
                    f"Cannot delete attribute value with {child_count} child value(s)",
                )

            deleted_attribute_id = value.attribute_id
            await session.delete(value)
            await session.commit()
            return value_id, deleted_attribute_id
