#!/usr/bin/env python3

# ruff: noqa: I001, E402
from openg2p_gen2_master_data.config import Settings

Settings.get_config()

from openg2p_gen2_master_data.app import Initializer
from openg2p_fastapi_common.ping import PingInitializer

from iam_core.user_auth.app import Initializer as IAMInitializer
from iam_core.user_auth.middleware import (
    ResolvePermissionMiddleware,
    ValidateAndRefreshTokenMiddleware,
)
from iam_core.user_auth.data_policy_middleware import DataPolicyMiddleware

IAMInitializer()
initializer = Initializer()
PingInitializer()

_config = Settings.get_config()

app = initializer.return_app()

# Middleware order (last added = outermost on inbound):
# ValidateAndRefreshToken -> ResolvePermission -> DataPolicy -> app
app.add_middleware(
    DataPolicyMiddleware,
    client_id=_config.keycloak_client_id,
)
app.add_middleware(
    ResolvePermissionMiddleware,
    client_id=_config.keycloak_client_id,
    allow_by_default=True,
)
app.add_middleware(ValidateAndRefreshTokenMiddleware)

if __name__ == "__main__":
    initializer.main()
