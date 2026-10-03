from iam_core.user_auth.config import Settings as IamSettings
from pydantic_settings import SettingsConfigDict

from . import __version__


class Settings(IamSettings):
    """Master-data settings, including iam-core auth fields under one env prefix.

    Auth/CSRF/redis fields come from ``IamSettings`` but are read from
    ``MASTER_DATA_API_*`` (not ``COMMON_*``). Load this Settings before
    ``IAMInitializer`` so iam-core middleware ``get_config(strict=False)``
    picks up this instance.
    """

    model_config = SettingsConfigDict(
        env_prefix="master_data_api_",
        env_file=".env",
        extra="allow",
        env_nested_delimiter="__",
    )

    openapi_title: str = "OpenG2P Gen 2 Master Data"
    openapi_description: str = """
        FastAPI Service for OpenG2P Gen 2 Master Data API
        ***********************************
        Further details goes here
        ***********************************
        """
    openapi_version: str = __version__

    # Master Data Database
    db_driver: str = "postgresql+asyncpg"
    db_username: str = "postgres"
    db_password: str = "password"
    db_hostname: str = "localhost"
    db_port: int = 5432
    db_dbname: str = "master_data"

    # Keycloak client / staff-portal application mnemonic for MASTER_DATA_ADMIN.
    keycloak_client_id: str | None = "master-data"

    # Cache settings. The legacy read endpoints (/attributes/get_*, /geo/get_*)
    # are cached in memory PER WORKER for this long. After a publish (or a
    # future-effective version coming into effect) the worker that did it drops
    # its cache at once; every other worker (other processes, other pods) drops
    # its own when its background loop sees g2p_catalogue_state
    # ['legacy.generation'] move — within catalogue_outbox_relay_seconds — and
    # in any case the entry expires after cache_expire_seconds. Staleness of a
    # legacy read is therefore bounded by
    # min(cache_expire_seconds, catalogue_outbox_relay_seconds) after a publish,
    # plus up to catalogue_effective_refresh_seconds after a future effective
    # date passes. The /catalogue reads are not cached.
    cache_expire_seconds: int = 300  # 5 minutes default

    # ── Catalogue ────────────────────────────────────────────────────────────
    # How a submitted draft gets approved:
    #   "permission" — a user holding referenceData:publish (lists, releases) or
    #                  geo:publish (geography) approves via approve_*; the
    #                  approver must not be the draft's maker.
    #   "awe"        — submit opens an AWE approval request; the version is
    #                  published (or rejected) when AWE calls back. Needs
    #                  awe_base_url, else the service falls back to "permission".
    catalogue_approval_mode: str = "permission"
    # How often (seconds) to check whether a future-effective published version
    # has come into effect; if so the legacy tables are refreshed (once, in the
    # shared database) and *.version.effective is logged and announced. A
    # version therefore comes into effect at most this long after its
    # effective_from. 0 disables the periodic check (it still runs on start).
    catalogue_effective_refresh_seconds: int = 300
    # Outbox relay: how often (seconds) each worker's background loop forwards
    # change-log events not yet delivered to the Audit Manager / WebSub, and
    # checks whether its legacy read cache must be dropped. Only one worker in
    # the whole deployment forwards at a time (Postgres advisory lock); events
    # written by the API are also forwarded right after their commit. 0
    # disables the loop's relay and cache check.
    catalogue_outbox_relay_seconds: int = 30
    # Maximum events forwarded per relay batch.
    catalogue_outbox_batch_size: int = 200
    # Country code used in boundary object keys when the geography version does
    # not record one (the country-pack loader records the pack's).
    catalogue_country: str = ""
    # Default owner (department) for lists and geography that do not name one.
    catalogue_default_owner_org: str = ""

    # AWE (Approval Workflow Engine), used when catalogue_approval_mode = "awe".
    # Host only, e.g. http://awe-service (the client appends /v1/awe/...).
    awe_base_url: str = ""
    awe_http_timeout_seconds: float = 30.0
    awe_policy_key_list: str = "master_data.list_version.v1"
    awe_policy_key_geo: str = "master_data.geo_version.v1"
    # Where AWE posts decisions: this service's /catalogue/awe/callback.
    awe_callback_url: str | None = None
    # Id of the HMAC secret registered in AWE, and the secret itself (to verify
    # X-Approval-Signature on callbacks).
    awe_callback_secret_id: str | None = None
    awe_callback_hmac_secret: str | None = None
    awe_webhook_timestamp_tolerance_seconds: int = 300

    # Audit Manager (CloudEvents). Empty disables emission; the local change log
    # (g2p_catalogue_change_log) is always written and is the outbox: an event
    # is retried by the relay until the Audit Manager accepts it (a 4xx other
    # than 408/429 is logged and not retried).
    audit_manager_url: str = ""
    audit_source: str = "/openg2p/master-data"
    audit_timeout_seconds: float = 5.0

    # WebSub hub for version notifications. Empty disables. Topics:
    # <prefix>.<list|geo|release>.published (a version / release was published,
    # whatever its effective date) and <prefix>.<list|geo>.effective (a
    # future-effective version became the one in effect).
    websub_hub_url: str = ""
    websub_topic_prefix: str = "openg2p.master-data"

    # Boundary object store (S3 / MinIO). Empty endpoint disables uploads and
    # streaming; object keys recorded by the loader are still returned.
    boundary_s3_endpoint: str = ""
    boundary_s3_bucket: str = "openg2p-geo"
    boundary_s3_access_key: str = ""
    boundary_s3_secret_key: str = ""
    boundary_s3_region: str = "us-east-1"
    # Browser-reachable base URL for objects (<base>/<bucket>/<key>), if public.
    boundary_public_base_url: str = ""
    boundary_presign_seconds: int = 3600
