import logging
from typing import List, Optional

from openg2p_fastapi_common.service import BaseService
from sqlalchemy import func, select

from ..engine import get_session_maker
from ..models import G2PAttribute, G2PAttributeValue
from ..schemas import AttributeData, AttributeValueData

_config = None
try:
    from ..config import Settings

    _config = Settings.get_config()
except Exception:
    pass

_logger = logging.getLogger(_config.logging_default_logger_name if _config else "g2p-attribute-service")


class G2PAttributeService(BaseService):
    """Reads the country's code lists.

    Domain lists (crops, livestock) are excluded by default: a social registry
    has no use for them, and returning everything would make the common case pay
    for the uncommon one.
    """

    def __init__(self) -> None:
        super().__init__()

    async def get_attributes(
        self, domain: Optional[str] = None, include_domains: bool = False
    ) -> List[AttributeData]:
        async with get_session_maker()() as session:
            stmt = select(G2PAttribute).order_by(G2PAttribute.attribute_id)
            rows = (await session.execute(stmt)).scalars().all()

        if domain or not include_domains:
            # Attributes carry no domain of their own — it lives on the values —
            # so filter by which attributes actually have values in scope.
            ids = await self._attribute_ids_in_scope(domain, include_domains)
            rows = [r for r in rows if r.attribute_id in ids]

        return [
            AttributeData(
                attribute_id=r.attribute_id,
                attribute_code=r.attribute_code,
                attribute_display=r.attribute_display,
                is_hierarchical=bool(r.is_hierarchical),
                display_name_i18n=r.display_name_i18n,
                country=r.country,
                version=r.version,
            )
            for r in rows
        ]

    async def _attribute_ids_in_scope(self, domain, include_domains) -> set:
        async with get_session_maker()() as session:
            stmt = select(G2PAttributeValue.attribute_id).distinct()
            if domain:
                stmt = stmt.where(G2PAttributeValue.domain == domain)
            elif not include_domains:
                stmt = stmt.where(G2PAttributeValue.domain.is_(None))
            return set((await session.execute(stmt)).scalars().all())

    async def get_attribute_values(
        self,
        attribute_id: Optional[str] = None,
        domain: Optional[str] = None,
        include_domains: bool = False,
        page_size: int = 1000,
        page_number: int = 1,
    ) -> tuple[List[AttributeValueData], int]:
        def scoped(stmt):
            if attribute_id:
                stmt = stmt.where(G2PAttributeValue.attribute_id == attribute_id)
            if domain:
                stmt = stmt.where(G2PAttributeValue.domain == domain)
            elif not include_domains:
                stmt = stmt.where(G2PAttributeValue.domain.is_(None))
            return stmt

        async with get_session_maker()() as session:
            total = (
                await session.execute(scoped(select(func.count()).select_from(G2PAttributeValue)))
            ).scalar_one()
            stmt = scoped(select(G2PAttributeValue)).order_by(
                G2PAttributeValue.attribute_id, G2PAttributeValue.sort_order
            )
            stmt = stmt.limit(page_size).offset(max(0, (page_number - 1)) * page_size)
            rows = (await session.execute(stmt)).scalars().all()

        return [
            AttributeValueData(
                attribute_id=r.attribute_id,
                value_id=r.value_id,
                value_code=r.value_code,
                value_display=r.value_display,
                parent_value_id=r.parent_value_id,
                sort_order=r.sort_order,
                display_name_i18n=r.display_name_i18n,
                roles=r.roles or [],
                domain=r.domain,
                country=r.country,
                version=r.version,
                valid_from=r.valid_from,
                valid_to=r.valid_to,
            )
            for r in rows
        ], total
