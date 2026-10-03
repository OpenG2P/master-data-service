#!/usr/bin/env python3

# ruff: noqa: I001, E402
from openg2p_gen2_master_data.config import Settings

_config = Settings.get_config()

from openg2p_gen2_master_data.app import Initializer
from openg2p_fastapi_common.ping import PingInitializer

from iam_core.user_auth.app import Initializer as IAMInitializer
from iam_core.user_auth.middleware import (
    CsrfMiddleware,
    ResolvePermissionMiddleware,
    ValidateAndRefreshTokenMiddleware,
)
from iam_core.user_auth.middleware.data_policy import DataPolicyMiddleware

# Safe / docs paths and any install-time seed callers that skip browser CSRF.
MASTER_DATA_CSRF_EXCLUDED_PATHS = (
    "/ping",
    "/openapi.json",
    "/docs",
    "/redoc",
    "/docs/oauth2-redirect",
    # Read-only attribute catalogue, pulled by each registry's db-seed Job at
    # install time. The comment above always claimed seed callers were exempt,
    # but no seed path was ever listed, so every registry install failed with
    # "Forbidden. CSRF token missing or invalid." the moment it tried to
    # populate its attributes.
    #
    # Safe to exempt: CsrfMiddleware is a double-submit check defending against
    # a BROWSER being induced to send a request with ambient cookies. db-seed is
    # a server-to-server caller with no cookies and no session, so there is no
    # ambient credential to abuse — and these two endpoints only read.
    "/attributes/get_all_attributes",
    "/attributes/get_attribute_values",
    # Same for geo reads: registry walks the hierarchy over REST instead of
    # connecting to the master-data database, and those calls are also
    # server-to-server with a Bearer token and no cookies.
    "/geo/get_all_geo_levels",
    "/geo/get_geo_level_values",
    # Catalogue reads: the same server-to-server consumers (registries, the
    # composite service) read versions, values and the change feed.
    "/catalogue/get_lists",
    "/catalogue/get_list",
    "/catalogue/get_list_values",
    "/catalogue/get_list_value",
    "/catalogue/get_list_versions",
    "/catalogue/get_list_diff",
    "/catalogue/get_geo_versions",
    "/catalogue/get_geo_levels",
    "/catalogue/get_geo_units",
    "/catalogue/get_geo_unit",
    "/catalogue/get_geo_changes",
    "/catalogue/get_geo_crosswalk",
    "/catalogue/get_geo_boundary",
    "/catalogue/get_releases",
    "/catalogue/get_release",
    "/catalogue/get_changes",
    "/catalogue/get_catalogue_config",
    # AWE posts decisions server-to-server; authenticated by its HMAC signature.
    "/catalogue/awe/callback",
)

# IAMInitializer after Settings.get_config() so iam-core middleware
# get_config(strict=False) resolves this MASTER_DATA_API_* instance.
IAMInitializer()
initializer = Initializer()
PingInitializer()

app = initializer.return_app()

# Middleware order (last added = outermost on inbound):
# CSRF -> ValidateAndRefresh -> ResolvePermission -> DataPolicy -> app
app.add_middleware(
    DataPolicyMiddleware,
    iam_api_url=_config.auth_provider_api_url,
)
app.add_middleware(
    ResolvePermissionMiddleware,
    client_id=_config.keycloak_client_id,
    allow_by_default=True,
)
app.add_middleware(ValidateAndRefreshTokenMiddleware)
app.add_middleware(
    CsrfMiddleware,
    enabled=_config.csrf_enabled,
    excluded_paths=MASTER_DATA_CSRF_EXCLUDED_PATHS,
)

if __name__ == "__main__":
    initializer.main()
