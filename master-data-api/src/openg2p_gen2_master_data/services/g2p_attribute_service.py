import logging
from typing import List, Optional

from openg2p_fastapi_common.context import get_async_session_maker
from openg2p_fastapi_common.service import BaseService
from sqlalchemy import func, select

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
    """Reads the country's code lists — the CURRENT PUBLISHED state.

    g2p_attributes / g2p_attribute_values are materialised from the catalogue's
    current published versions on every publish, so these reads are unchanged
    for every existing consumer.
    """

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
            current_version_no=row.current_version_no,
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

    async def get_list_versions(self, attribute_ids: List[str]) -> dict:
        """{attribute_id: current published version} for the given lists."""
        if not attribute_ids:
            return {}
        session_maker = get_async_session_maker()
        async with session_maker() as session:
            rows = (
                await session.execute(
                    select(G2PAttribute.attribute_id, G2PAttribute.current_version_no).where(
                        G2PAttribute.attribute_id.in_(set(attribute_ids))
                    )
                )
            ).all()
        return {a: v for a, v in rows}

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

    # Writes moved to G2PCatalogueListService: the /attributes write endpoints
    # now edit the list's open draft instead of the published rows.
