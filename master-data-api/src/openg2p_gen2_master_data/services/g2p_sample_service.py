"""Reads of the sample people and households a country pack loaded (``--load samples``).

Registries build their sample data from these (see models/g2p_sample.py for why
they live here), over the API rather than by reading this database.
"""

from typing import List, Optional, Tuple

from openg2p_fastapi_common.context import get_async_session_maker
from openg2p_fastapi_common.service import BaseService
from sqlalchemy import func, select

from ..models import G2PSampleHousehold, G2PSampleIndividual
from ..schemas.g2p_sample import SampleHousehold, SampleIndividual


def _filtered(stmt, model, **filters):
    for column, value in filters.items():
        if value is not None:
            stmt = stmt.where(getattr(model, column) == value)
    return stmt


class G2PSampleService(BaseService):
    async def get_individuals(
        self,
        *,
        household_id: Optional[str] = None,
        geo_pcode: Optional[str] = None,
        country: Optional[str] = None,
        page_size: int = 1000,
        page_number: int = 1,
    ) -> Tuple[List[SampleIndividual], int]:
        """One page of sample people, in individual_id order, and how many match."""
        M = G2PSampleIndividual
        filters = {"household_id": household_id, "geo_pcode": geo_pcode, "country": country}
        async with get_async_session_maker()() as s:
            total = (
                await s.execute(_filtered(select(func.count()).select_from(M), M, **filters))
            ).scalar_one()
            rows = (
                await s.execute(
                    _filtered(select(M), M, **filters)
                    .order_by(M.individual_id)
                    .limit(page_size)
                    .offset(max(page_number - 1, 0) * page_size)
                )
            ).scalars()
            return [SampleIndividual.model_validate(r, from_attributes=True) for r in rows], total

    async def get_households(
        self,
        *,
        geo_pcode: Optional[str] = None,
        country: Optional[str] = None,
        page_size: int = 1000,
        page_number: int = 1,
    ) -> Tuple[List[SampleHousehold], int]:
        """One page of sample households, in household_id order, and how many match."""
        M = G2PSampleHousehold
        filters = {"geo_pcode": geo_pcode, "country": country}
        async with get_async_session_maker()() as s:
            total = (
                await s.execute(_filtered(select(func.count()).select_from(M), M, **filters))
            ).scalar_one()
            rows = (
                await s.execute(
                    _filtered(select(M), M, **filters)
                    .order_by(M.household_id)
                    .limit(page_size)
                    .offset(max(page_number - 1, 0) * page_size)
                )
            ).scalars()
            return [SampleHousehold.model_validate(r, from_attributes=True) for r in rows], total
