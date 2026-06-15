from openg2p_fastapi_common.config import Settings as BaseSettings
from pydantic_settings import SettingsConfigDict

from . import __version__


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="gen2_master_data_api_", env_file=".env", extra="allow")

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
    db_dbname: str = "openg2p_gen2_master_data_db"

    # Cache settings
    cache_expire_seconds: int = 300  # 5 minutes default
