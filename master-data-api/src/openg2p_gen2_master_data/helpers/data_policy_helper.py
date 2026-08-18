"""Master-data data-policy resolution helpers.

Attribute/geo policy merging for MDS lives here (not in iam-core). Register-record
resolution remains in ``iam_core.helpers.data_policy_helper`` for registry use.
"""

from iam_core.models.enum import DataPolicyTypeEnum, PolicyTargetEnum


class DataPolicyHelper:
    """Resolve ATTRIBUTE / GEO policies from middleware policy payloads."""

    @staticmethod
    def resolve_attribute_policy(
        data_policies: list[dict] | None,
    ) -> dict | None:
        """Resolve and merge global ATTRIBUTE policies from middleware response."""
        return DataPolicyHelper._resolve_target_policy(
            data_policies,
            PolicyTargetEnum.ATTRIBUTE.value,
        )

    @staticmethod
    def resolve_geo_policy(
        data_policies: list[dict] | None,
    ) -> dict | None:
        """Resolve and merge global GEO policies from middleware response."""
        return DataPolicyHelper._resolve_target_policy(
            data_policies,
            PolicyTargetEnum.GEO.value,
        )

    @staticmethod
    def _resolve_target_policy(
        data_policies: list[dict] | None,
        policy_target: str,
    ) -> dict | None:
        if not data_policies:
            return None

        policies_data = [
            p for p in data_policies if p.get("policy_target") == policy_target
        ]
        if not policies_data:
            return None

        allow_expressions: list[dict] = []
        disallow_expressions: list[dict] = []
        for policy in policies_data:
            expression = policy.get("policy_filter_expression")
            if not isinstance(expression, dict):
                continue
            if policy.get("policy_type") == DataPolicyTypeEnum.DISALLOW.value:
                disallow_expressions.append(expression)
            else:
                allow_expressions.append(expression)

        return DataPolicyHelper._merge_expressions(allow_expressions, disallow_expressions)

    @staticmethod
    def _merge_expressions(
        allow_expressions: list[dict],
        disallow_expressions: list[dict],
    ) -> dict | None:
        nodes: list[dict] = []

        if len(allow_expressions) == 1:
            nodes.append(allow_expressions[0])
        elif len(allow_expressions) > 1:
            nodes.append({"type": "GROUP", "operator": "OR", "children": allow_expressions})

        if len(disallow_expressions) == 1:
            nodes.append(
                {
                    "type": "GROUP",
                    "operator": "NOT",
                    "children": [disallow_expressions[0]],
                }
            )
        elif len(disallow_expressions) > 1:
            nodes.append(
                {
                    "type": "GROUP",
                    "operator": "NOT",
                    "children": [
                        {
                            "type": "GROUP",
                            "operator": "OR",
                            "children": disallow_expressions,
                        }
                    ],
                }
            )

        if not nodes:
            return None

        if len(nodes) == 1:
            return nodes[0]

        return {"type": "GROUP", "operator": "AND", "children": nodes}
