"""Attribute value data-access: ATTRIBUTE policy -> SQLAlchemy.

ATTRIBUTE policies use:

- ``field_id`` = attribute ``attribute_code`` (e.g. ``COPING_STRATEGY``)
- ``value`` / ``values`` = allowed ``value_code`` entries on ``G2PAttributeValue``

Cross-attribute top-level ``AND`` means the caller may access allowed values from
each attribute dimension. When filtering ``g2p_attribute_values`` rows, that
translates to ``OR`` across per-attribute clauses (each row belongs to one
attribute). When ``attribute_context`` is supplied (an ``attribute_code``),
only the subtree for that attribute is applied.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import and_, not_, or_, select
from sqlalchemy.sql.elements import ColumnElement

from ..models import G2PAttribute, G2PAttributeValue

_logger = logging.getLogger("attribute-value-repository")

_GROUP_TYPE = "GROUP"
_CONDITION_TYPE = "CONDITION"


class AttributeValueRepository:
    """Converts ATTRIBUTE-target data policies into SQL on ``G2PAttributeValue``."""

    @property
    def model(self) -> type[G2PAttributeValue]:
        return G2PAttributeValue

    def build_policy_condition(
        self,
        expression: Any,
        *,
        attribute_context: str | None = None,
    ) -> ColumnElement | None:
        """Convert a policy tree into a SQLAlchemy condition.

        ``attribute_context`` is an ``attribute_code`` that limits enforcement
        to one attribute when the API request is scoped to a single attribute.
        """
        node = self._as_dict(expression)
        if node is None:
            return None
        return self._build_node(node, attribute_context)

    def _build_node(
        self,
        node: dict,
        attribute_context: str | None,
    ) -> ColumnElement | None:
        node_type = node.get("type")
        if node_type == _CONDITION_TYPE:
            return self._build_pair_condition(node, attribute_context)
        if node_type == _GROUP_TYPE or "children" in node:
            return self._build_group(node, attribute_context)
        _logger.warning("Unrecognized ATTRIBUTE policy node type: %s", node_type)
        return None

    def _build_group(
        self,
        group: dict,
        attribute_context: str | None,
    ) -> ColumnElement | None:
        operator = str(group.get("operator") or "AND").upper()
        children = group.get("children") or []

        if operator == "OR":
            collapsed = self._try_collapse_same_attribute_or_group(children, attribute_context)
            if collapsed is not None:
                return collapsed

        conditions = [
            condition
            for child in children
            if (condition := self._build_node(child, attribute_context)) is not None
        ]
        if not conditions:
            return None

        if operator == "OR":
            return or_(*conditions)
        if operator == "NOT":
            return not_(and_(*conditions))

        # Cross-attribute AND: row-level filter uses OR (each row is one attribute).
        if not attribute_context and len(conditions) > 1:
            return or_(*conditions)
        return and_(*conditions)

    def _try_collapse_same_attribute_or_group(
        self,
        children: list[dict],
        attribute_context: str | None,
    ) -> ColumnElement | None:
        """Collapse OR [ (attr, v1), (attr, v2), ... ] into attr + value_code IN (...)."""
        if not children:
            return None

        field_ids: set[str] = set()
        value_codes: list[Any] = []
        operators: set[str] = set()

        for child in children:
            if child.get("type") != _CONDITION_TYPE:
                return None
            field_id = child.get("field_id")
            if not field_id or not self._field_matches_context(field_id, attribute_context):
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

        return self._build_attribute_value_clause(
            next(iter(field_ids)),
            "in",
            None,
            value_codes,
        )

    def _build_pair_condition(
        self,
        condition: dict,
        attribute_context: str | None,
    ) -> ColumnElement | None:
        attribute_code = condition.get("field_id")
        if not attribute_code:
            return None
        if attribute_context and attribute_code != attribute_context:
            return None

        operator = self._normalize_operator(condition.get("operator"))
        return self._build_attribute_value_clause(
            str(attribute_code),
            operator,
            condition.get("value"),
            condition.get("values"),
        )

    def _build_attribute_value_clause(
        self,
        attribute_code: str,
        operator: str,
        value: Any,
        values: Any,
    ) -> ColumnElement | None:
        attribute_match = self._attribute_code_match(attribute_code)
        value_column = G2PAttributeValue.value_code

        match operator:
            case "eq":
                if value is None:
                    return None
                return and_(attribute_match, value_column == value)
            case "neq":
                if value is None:
                    return None
                return and_(attribute_match, value_column != value)
            case "in":
                allowed = values or []
                if not allowed:
                    return None
                return and_(attribute_match, value_column.in_(allowed))
            case "nin":
                blocked = values or []
                if not blocked:
                    return None
                return and_(attribute_match, ~value_column.in_(blocked))
            case "contains":
                if value is None:
                    return None
                return and_(attribute_match, value_column.ilike(f"%{value}%"))
            case "startsWith":
                if value is None:
                    return None
                return and_(attribute_match, value_column.ilike(f"{value}%"))
            case "endsWith":
                if value is None:
                    return None
                return and_(attribute_match, value_column.ilike(f"%{value}"))
            case _:
                _logger.warning("Unsupported ATTRIBUTE policy operator: %s", operator)
                return None

    def _attribute_code_match(self, attribute_code: str) -> ColumnElement:
        return G2PAttributeValue.attribute_id.in_(
            select(G2PAttribute.attribute_id).where(G2PAttribute.attribute_code == attribute_code)
        )

    def _field_matches_context(self, attribute_code: str, attribute_context: str | None) -> bool:
        return not attribute_context or attribute_code == attribute_context

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
