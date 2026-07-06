"""GEO-target data policy -> SQLAlchemy on ``g2p_geo_level_values``.

GEO policies use the same GROUP/CONDITION tree as register/attribute policies, but
with different field semantics:

- ``field_id`` is the geo **level mnemonic** (e.g. ``country``, ``region``, ``ward``)
- ``value`` / ``values`` are **level value mnemonics** on ``G2PGeoLevelValue``

A top-level ``AND`` across different levels defines a single allowed **path**
through the hierarchy (country -> region -> district -> ...). The deepest
specified node anchors allowed IDs: **ancestors on the path**, the anchor,
and all descendant geo values.

Example::

    {
      "type": "GROUP",
      "operator": "AND",
      "children": [
        {"type": "CONDITION", "field_id": "country",  "operator": "eq", "value": "kamuntu"},
        {"type": "CONDITION", "field_id": "region",   "operator": "eq", "value": "chakula"},
        {"type": "CONDITION", "field_id": "district", "operator": "eq", "value": "njia"},
        {"type": "CONDITION", "field_id": "ward",     "operator": "eq", "value": "wingu"}
      ]
    }
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import and_, false, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from ..models import G2PGeoLevel, G2PGeoLevelValue

_logger = logging.getLogger("geo-level-value-policy-repository")

_GROUP_TYPE = "GROUP"
_CONDITION_TYPE = "CONDITION"


class GeoLevelValuePolicyRepository:
    """Converts GEO-target data policies into SQL on ``g2p_geo_level_values``."""

    @property
    def model(self) -> type[G2PGeoLevelValue]:
        return G2PGeoLevelValue

    def build_policy_condition(
        self,
        expression: Any,
        *,
        level_mnemonic: str,
        allowed_subtree_ids: set[str] | frozenset[str] | None = None,
    ) -> ColumnElement | None:
        """Convert a policy tree into a SQLAlchemy condition for one list query.

        ``level_mnemonic`` is the mnemonic of the level being listed (resolved
        from ``level_id``). ``allowed_subtree_ids`` should be precomputed via
        :meth:`resolve_allowed_subtree_ids` when the expression imposes path
        constraints.

        Returns ``None`` when the expression is empty or imposes no restriction.
        """
        node = self._as_dict(expression)
        if node is None:
            return None

        path_maps = self.extract_path_maps(node)
        if not path_maps:
            return None

        conditions: list[ColumnElement] = []

        if allowed_subtree_ids is not None:
            if not allowed_subtree_ids:
                return false()
            conditions.append(G2PGeoLevelValue.level_value_id.in_(allowed_subtree_ids))

        level_value_mnemonics: set[str] = set()
        for path_map in path_maps:
            values = path_map.get(level_mnemonic)
            if values:
                level_value_mnemonics.update(values)

        if level_value_mnemonics:
            conditions.append(G2PGeoLevelValue.level_value_mnemonic.in_(level_value_mnemonics))

        if not conditions:
            return None
        if len(conditions) == 1:
            return conditions[0]
        return and_(*conditions)

    def extract_path_maps(self, expression: Any) -> list[dict[str, list[str]]]:
        """Extract allowed geo paths as level_mnemonic -> value mnemonics maps."""
        node = self._as_dict(expression)
        if node is None:
            return []
        return self._extract_path_maps_from_node(node)

    async def resolve_allowed_subtree_ids(
        self,
        session: AsyncSession,
        expression: Any,
    ) -> set[str] | None:
        """Resolve all ``level_value_id`` values allowed by the policy subtree.

        Returns ``None`` when the expression is empty (no restriction).
        Returns an empty set when the policy applies but matches nothing.
        """
        node = self._as_dict(expression)
        if node is None:
            return None

        path_maps = self.extract_path_maps(node)
        if not path_maps:
            return None

        level_order = await self._load_level_mnemonic_order(session)
        allowed: set[str] = set()

        for path_map in path_maps:
            anchor_ids = await self._resolve_path_anchor_ids(session, path_map, level_order)
            if not anchor_ids:
                continue
            allowed.update(await self._collect_ancestor_ids(session, anchor_ids))
            allowed.update(await self._expand_subtree_ids(session, anchor_ids))

        return allowed

    async def _collect_ancestor_ids(
        self,
        session: AsyncSession,
        level_value_ids: list[str],
    ) -> set[str]:
        """Return anchor nodes and every ancestor up to the geo root."""
        ancestors: set[str] = set()

        for anchor_id in level_value_ids:
            current_id: str | None = anchor_id
            while current_id:
                if current_id in ancestors:
                    break
                ancestors.add(current_id)
                parent_id = (
                    await session.execute(
                        select(G2PGeoLevelValue.parent_level_value_id).where(
                            G2PGeoLevelValue.level_value_id == current_id
                        )
                    )
                ).scalar_one_or_none()
                current_id = parent_id

        return ancestors

    async def _load_level_mnemonic_order(self, session: AsyncSession) -> list[str]:
        """Return level mnemonics from root to leaf using ``parent_level_id``."""
        result = await session.execute(select(G2PGeoLevel).order_by(G2PGeoLevel.level_id))
        levels = result.scalars().all()
        if not levels:
            return []

        children_by_parent: dict[str | None, list[G2PGeoLevel]] = {}
        for level in levels:
            children_by_parent.setdefault(level.parent_level_id, []).append(level)

        roots = children_by_parent.get(None, [])
        if not roots:
            return [level.level_mnemonic for level in levels]

        ordered: list[str] = []

        def walk(node: G2PGeoLevel) -> None:
            ordered.append(node.level_mnemonic)
            for child in children_by_parent.get(node.level_id, []):
                walk(child)

        for root in roots:
            walk(root)

        return ordered

    async def _resolve_path_anchor_ids(
        self,
        session: AsyncSession,
        path_map: dict[str, list[str]],
        level_order: list[str],
    ) -> list[str]:
        """Find deepest level_value_id nodes that satisfy a path map."""
        active_levels = [level for level in level_order if level in path_map and path_map[level]]
        if not active_levels:
            return []

        deepest_level = active_levels[-1]
        deepest_values = path_map[deepest_level]

        result = await session.execute(
            select(G2PGeoLevelValue, G2PGeoLevel.level_mnemonic)
            .join(G2PGeoLevel, G2PGeoLevelValue.level_id == G2PGeoLevel.level_id)
            .where(
                G2PGeoLevel.level_mnemonic == deepest_level,
                G2PGeoLevelValue.level_value_mnemonic.in_(deepest_values),
            )
        )

        anchor_ids: list[str] = []
        for level_value, _level_mnemonic in result.all():
            if await self._path_matches(session, level_value.level_value_id, path_map):
                anchor_ids.append(level_value.level_value_id)

        return anchor_ids

    async def _path_matches(
        self,
        session: AsyncSession,
        level_value_id: str,
        path_map: dict[str, list[str]],
    ) -> bool:
        """Walk ancestors and verify each constrained level matches the path map."""
        current_id: str | None = level_value_id

        while current_id:
            row = await session.execute(
                select(
                    G2PGeoLevelValue.level_value_mnemonic,
                    G2PGeoLevelValue.parent_level_value_id,
                    G2PGeoLevel.level_mnemonic,
                )
                .join(G2PGeoLevel, G2PGeoLevelValue.level_id == G2PGeoLevel.level_id)
                .where(G2PGeoLevelValue.level_value_id == current_id)
            )
            match = row.one_or_none()
            if match is None:
                return False

            value_mnemonic, parent_id, level_mnemonic = match
            if level_mnemonic in path_map:
                allowed = path_map[level_mnemonic]
                if value_mnemonic not in allowed:
                    return False

            current_id = parent_id

        return True

    async def _expand_subtree_ids(
        self,
        session: AsyncSession,
        anchor_ids: list[str],
    ) -> set[str]:
        """Return anchor nodes and all descendant ``level_value_id`` values."""
        if not anchor_ids:
            return set()

        result = await session.execute(
            text(
                """
                WITH RECURSIVE subtree AS (
                    SELECT level_value_id
                    FROM g2p_geo_level_values
                    WHERE level_value_id = ANY(:anchor_ids)
                    UNION ALL
                    SELECT child.level_value_id
                    FROM g2p_geo_level_values child
                    JOIN subtree parent
                      ON child.parent_level_value_id = parent.level_value_id
                )
                SELECT level_value_id FROM subtree
                """
            ),
            {"anchor_ids": anchor_ids},
        )
        return {row[0] for row in result.fetchall()}

    def _extract_path_maps_from_node(self, node: dict) -> list[dict[str, list[str]]]:
        node_type = node.get("type")
        if node_type == _CONDITION_TYPE:
            path_map = self._condition_to_path_map(node)
            return [path_map] if path_map else []
        if node_type == _GROUP_TYPE or "children" in node:
            return self._extract_path_maps_from_group(node)
        _logger.warning("Unrecognized GEO policy node type: %s", node_type)
        return []

    def _extract_path_maps_from_group(self, group: dict) -> list[dict[str, list[str]]]:
        operator = str(group.get("operator") or "AND").upper()
        children = group.get("children") or []

        if operator == "OR":
            paths: list[dict[str, list[str]]] = []
            for child in children:
                paths.extend(self._extract_path_maps_from_node(child))
            return self._dedupe_path_maps(paths)

        if operator == "NOT":
            _logger.warning("NOT groups are not supported in GEO path extraction")
            return []

        # Multiple sibling GROUP children under AND are alternative geo paths
        # (union / OR semantics). Example: AND [ path(kilima), path(chakula), ... ].
        if len(children) > 1 and all(self._is_path_branch_group(child) for child in children):
            paths: list[dict[str, list[str]]] = []
            for child in children:
                paths.extend(self._extract_path_maps_from_node(child))
            return self._dedupe_path_maps(paths)

        child_path_lists = [self._extract_path_maps_from_node(child) for child in children]
        child_path_lists = [paths for paths in child_path_lists if paths]
        if not child_path_lists:
            return []

        combined: list[dict[str, list[str]]] = [{}]
        for child_paths in child_path_lists:
            merged_paths: list[dict[str, list[str]]] = []
            for base_path in combined:
                for child_path in child_paths:
                    merged = self._merge_path_maps(base_path, child_path)
                    if self._is_valid_path_map(merged):
                        merged_paths.append(merged)
            combined = merged_paths

        return self._dedupe_path_maps(
            [path_map for path_map in combined if self._is_valid_path_map(path_map)]
        )

    @staticmethod
    def _is_path_branch_group(node: dict) -> bool:
        """True when a node is a GROUP that defines one geo path branch."""
        return node.get("type") == _GROUP_TYPE or "children" in node

    @staticmethod
    def _is_valid_path_map(path_map: dict[str, list[str]]) -> bool:
        """Reject path maps where a level was intersected down to no allowed values."""
        if not path_map:
            return False
        return all(bool(values) for values in path_map.values())

    @staticmethod
    def _dedupe_path_maps(
        path_maps: list[dict[str, list[str]]],
    ) -> list[dict[str, list[str]]]:
        """Drop duplicate path maps while preserving order."""
        seen: set[tuple[tuple[str, tuple[str, ...]], ...]] = set()
        unique: list[dict[str, list[str]]] = []
        for path_map in path_maps:
            if not GeoLevelValuePolicyRepository._is_valid_path_map(path_map):
                continue
            key = tuple(sorted((level, tuple(values)) for level, values in path_map.items()))
            if key in seen:
                continue
            seen.add(key)
            unique.append(path_map)
        return unique

    def _condition_to_path_map(self, condition: dict) -> dict[str, list[str]]:
        level_mnemonic = condition.get("field_id")
        if not level_mnemonic:
            return {}

        operator = self._normalize_operator(condition.get("operator"))
        level_mnemonic = str(level_mnemonic)

        if operator == "eq" and condition.get("value") is not None:
            return {level_mnemonic: [condition["value"]]}
        if operator == "in":
            values = [value for value in (condition.get("values") or []) if value is not None]
            if values:
                return {level_mnemonic: values}
        if operator == "neq" and condition.get("value") is not None:
            _logger.warning(
                "neq operator on GEO policy level '%s' is not supported in path extraction",
                level_mnemonic,
            )

        _logger.warning(
            "Unsupported GEO policy condition for level '%s' operator '%s'",
            level_mnemonic,
            operator,
        )
        return {}

    @staticmethod
    def _merge_path_maps(
        left: dict[str, list[str]],
        right: dict[str, list[str]],
    ) -> dict[str, list[str]]:
        merged = {level: list(values) for level, values in left.items()}
        for level, values in right.items():
            if level in merged:
                intersection = list(set(merged[level]) & set(values))
                merged[level] = intersection
            else:
                merged[level] = list(values)
        return merged

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
