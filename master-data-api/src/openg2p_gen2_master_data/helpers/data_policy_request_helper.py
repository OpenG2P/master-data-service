"""Read data-policy state set by iam-core DataPolicyMiddleware."""

from fastapi import Request
from iam_core.user_auth.middleware.data_policy import (
    STATE_KEY_DATA_POLICIES,
    STATE_KEY_DATA_POLICY_MNEMONICS,
)


def get_data_policy_mnemonics(request: Request) -> list[str]:
    return list(getattr(request.state, STATE_KEY_DATA_POLICY_MNEMONICS, []) or [])


def get_data_policies(request: Request) -> list[dict]:
    return list(getattr(request.state, STATE_KEY_DATA_POLICIES, []) or [])
