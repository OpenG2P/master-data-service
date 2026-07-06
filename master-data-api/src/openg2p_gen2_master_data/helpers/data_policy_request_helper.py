from fastapi import Request

from iam_core.user_auth.data_policy_middleware import STATE_KEY_DATA_POLICY_MNEMONICS


def get_data_policy_mnemonics(request: Request) -> list[str]:
    """Read DP_ policy mnemonics extracted from the token by DataPolicyMiddleware."""
    return list(getattr(request.state, STATE_KEY_DATA_POLICY_MNEMONICS, []) or [])
