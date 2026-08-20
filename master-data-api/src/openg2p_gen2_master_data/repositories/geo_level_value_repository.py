"""Geo level value data-access: GEO policy -> SQLAlchemy.

GEO policies use:

- ``field_id`` = geo level ``level_mnemonic`` (e.g. ``region``)
- ``value`` / ``values`` = allowed ``level_value_mnemonic`` entries

Cross-level top-level ``AND`` means the caller may access allowed values from
each level dimension. When filtering ``g2p_geo_level_values`` rows, that
translates to ``OR`` across per-level clauses (each row belongs to one level).
When ``level_context`` is supplied (a ``level_mnemonic``), only the subtree
for that level is applied.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import and_, not_, or_, select
from sqlalchemy.sql.elements import ColumnElement

from ..models import G2PGeoLevel, G2PGeoLevelValue

_logger = logging.getLogger("geo-level-value-repository")

_GROUP_TYPE = "GROUP"
_CONDITION_TYPE = "CONDITION"


class GeoLevelValueRepository:
    """Converts GEO-target data policies into SQL on ``G2PGeoLevelValue``."""

    @property
    def model(self) -> type[G2PGeoLevelValue]:
        return G2PGeoLevelValue

    def build_policy_condition(
        self,
        expression: Any,
        *,
        level_context: str | None = None,
    ) -> ColumnElement | None:
        """Convert a policy tree into a SQLAlchemy condition.

        ``level_context`` is a ``level_mnemonic`` that limits enforcement to one
        level when the API request is scoped to a single geo level.
        """
        node = self._as_dict(expression)
        if node is None:
            return None
        return self._build_node(node, level_context)

    def _build_node(
        self,
        node: dict,
        level_context: str | None,
    ) -> ColumnElement | None:
        node_type = node.get("type")
        if node_type == _CONDITION_TYPE:
            return self._build_pair_condition(node, level_context)
        if node_type == _GROUP_TYPE or "children" in node:
            return self._build_group(node, level_context)
        _logger.warning("Unrecognized GEO policy node type: %s", node_type)
        return None

    def _build_group(
        self,
        group: dict,
        level_context: str | None,
    ) -> ColumnElement | None:
        operator = str(group.get("operator") or "AND").upper()
        children = group.get("children") or []

        if operator == "OR":
            collapsed = self._try_collapse_same_level_or_group(children, level_context)
            if collapsed is not None:
                return collapsed

        conditions = [
            condition
            for child in children
            if (condition := self._build_node(child, level_context)) is not None
        ]
        if not conditions:
            return None

        if operator == "OR":
            return or_(*conditions)
        if operator == "NOT":
            return not_(and_(*conditions))

        # Cross-level AND: row-level filter uses OR (each row is one level).
        if not level_context and len(conditions) > 1:
            return or_(*conditions)
        return and_(*conditions)

    def _try_collapse_same_level_or_group(
        self,
        children: list[dict],
        level_context: str | None,
    ) -> ColumnElement | None:
        """Collapse OR [ (level, v1), (level, v2), ... ] into level + mnemonic IN (...)."""
        if not children:
            return None

        field_ids: set[str] = set()
        value_codes: list[Any] = []
        operators: set[str] = set()

        for child in children:
            if child.get("type") != _CONDITION_TYPE:
                return None
            field_id = child.get("field_id")
            if not field_id or not self._field_matches_context(field_id, level_context):
                return None
            operator = self._normalize_operator(child.get("operator"))
            operators.add(operator)
            field_ids.add(str(field_id))
            if operator == "eq" and child.get("value") is not None:
                value_codes.append(child.get("value"))
            elif operator == "in":
                value_codes.extend(child.get("values") or [])
            else:
                return None

        if len(field_ids) != 1 or not value_codes:
            return None
        if operators - {"eq", "in"}:
            return None

        return self._build_level_value_clause(
            next(iter(field_ids)),
            "in",
            None,
            value_codes,
        )

    def _build_pair_condition(
        self,
        condition: dict,
        level_context: str | None,
    ) -> ColumnElement | None:
        level_mnemonic = condition.get("field_id")
        if not level_mnemonic:
            return None
        if level_context and level_mnemonic != level_context:
            return None

        operator = self._normalize_operator(condition.get("operator"))
        return self._build_level_value_clause(
            str(level_mnemonic),
            operator,
            condition.get("value"),
            condition.get("values"),
        )

    def _build_level_value_clause(
        self,
        level_mnemonic: str,
        operator: str,
        value: Any,
        values: Any,
    ) -> ColumnElement | None:
        level_match = self._level_mnemonic_match(level_mnemonic)
        value_column = G2PGeoLevelValue.level_value_mnemonic

        match operator:
            case "eq":
                if value is None:
                    return None
                return and_(level_match, value_column == value)
            case "neq":
                if value is None:
                    return None
                return and_(level_match, value_column != value)
            case "in":
                allowed = values or []
                if not allowed:
                    return None
                return and_(level_match, value_column.in_(allowed))
            case "nin":
                blocked = values or []
                if not blocked:
                    return None
                return and_(level_match, ~value_column.in_(blocked))
            case "contains":
                if value is None:
                    return None
                return and_(level_match, value_column.ilike(f"%{value}%"))
            case "startsWith":
                if value is None:
                    return None
                return and_(level_match, value_column.ilike(f"{value}%"))
            case "endsWith":
                if value is None:
                    return None
                return and_(level_match, value_column.ilike(f"%{value}"))
            case _:
                _logger.warning("Unsupported GEO policy operator: %s", operator)
                return None

    def _level_mnemonic_match(self, level_mnemonic: str) -> ColumnElement:
        return G2PGeoLevelValue.level_id.in_(
            select(G2PGeoLevel.level_id).where(G2PGeoLevel.level_mnemonic == level_mnemonic)
        )

    def _field_matches_context(self, level_mnemonic: str, level_context: str | None) -> bool:
        return not level_context or level_mnemonic == level_context

    @staticmethod
    def _normalize_operator(operator: Any) -> str:
        if operator is None:
            return "eq"
        return operator.value if hasattr(operator, "value") else str(operator)

    @staticmethod
    def _as_dict(expression: Any) -> dict | None:
        if not expression:
            return None
        if isinstance(expression, dict):
            return expression
        if hasattr(expression, "model_dump"):
            return expression.model_dump()
        return None
