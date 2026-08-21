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

    # Cache settings
    cache_expire_seconds: int = 300  # 5 minutes default
