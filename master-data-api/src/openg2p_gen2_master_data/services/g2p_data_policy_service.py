"""Resolve registry data policies stored in the registry database."""

import logging
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from openg2p_fastapi_common.service import BaseService

from ..models import G2PRegistryDataPolicy

_logger = logging.getLogger("g2p-data-policy-service")


class G2PDataPolicyService(BaseService):
    async def resolve_geo_policy(
        self,
        policy_mnemonics: Sequence[str] | None,
        session: AsyncSession,
    ) -> dict | None:
        """Resolve and merge global GEO policies for the given mnemonics.

        GEO policies are register-agnostic (``register_id`` is null).
        ALLOW policies are unioned (OR); DISALLOW policies are negated and
        intersected (AND NOT). Returns ``None`` when no policy applies (no
        restriction).
        """
        if not policy_mnemonics:
            return None

        result = await session.execute(
            select(G2PRegistryDataPolicy).where(
                G2PRegistryDataPolicy.policy_mnemonic.in_(list(policy_mnemonics)),
                G2PRegistryDataPolicy.policy_target == "GEO"
            )
        )
        policies = result.scalars().all()
        if not policies:
            return None

        allow_expressions: list[dict] = []
        disallow_expressions: list[dict] = []
        for policy in policies:
            expression = policy.policy_filter_expression
            if not isinstance(expression, dict):
                continue
            if policy.policy_type == "DISALLOW":
                disallow_expressions.append(expression)
            else:
                allow_expressions.append(expression)

        return self._merge_expressions(allow_expressions, disallow_expressions)

    @staticmethod
    def _merge_expressions(
        allow_expressions: list[dict],
        disallow_expressions: list[dict],
    ) -> dict | None:
        nodes: list[dict] = []

        if len(allow_expressions) == 1:
            nodes.append(allow_expressions[0])
        elif len(allow_expressions) > 1:
            nodes.append(
                {"type": "GROUP", "operator": "OR", "children": allow_expressions}
            )

        for disallow_expression in disallow_expressions:
            nodes.append(
                {"type": "GROUP", "operator": "NOT", "children": [disallow_expression]}
            )

        if not nodes:
            return None
        if len(nodes) == 1:
            return nodes[0]
        return {"type": "GROUP", "operator": "AND", "children": nodes}
