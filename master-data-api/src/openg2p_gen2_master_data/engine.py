"""Database engine and session management."""

import logging

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from openg2p_fastapi_common.context import dbengine

_logger = logging.getLogger("master-data-engine")

_engine: AsyncEngine | None = None
_registry_engine: AsyncEngine | None = None


def _construct_db_datasource(
    db_driver: str,
    db_username: str,
    db_password: str,
    db_hostname: str,
    db_port: int,
    db_dbname: str,
) -> str:
    datasource = ""
    if db_driver:
        datasource += f"{db_driver}://"
    if db_username:
        datasource += f"{db_username}:{db_password}@"
    if db_hostname:
        datasource += db_hostname
    if db_port:
        datasource += f":{db_port}"
    if db_dbname:
        datasource += f"/{db_dbname}"
    return datasource


def get_engine() -> AsyncEngine:
    """
    Get the master-data database engine.

    First tries the framework's context variable, then falls back to
    a module-level cached engine created from config.
    """
    global _engine

    engine = dbengine.get()
    if engine is not None:
        return engine

    if _engine is not None:
        return _engine

    from .config import Settings

    config = Settings.get_config()

    if config.db_datasource:
        _engine = create_async_engine(config.db_datasource, echo=config.db_logging)
        return _engine

    raise RuntimeError("Database not configured. Check db_datasource in settings.")


def get_registry_engine() -> AsyncEngine:
    """Get the registry database engine (read-only policy lookups)."""
    global _registry_engine

    if _registry_engine is not None:
        return _registry_engine

    from .config import Settings

    config = Settings.get_config()
    datasource = _construct_db_datasource(
        config.registry_db_driver,
        config.registry_db_username,
        config.registry_db_password,
        config.registry_db_hostname,
        config.registry_db_port,
        config.registry_db_dbname,
    )
    _logger.debug("Registry database datasource configured for policy resolution")
    _registry_engine = create_async_engine(datasource, poolclass=NullPool)
    return _registry_engine


def get_session_maker() -> async_sessionmaker[AsyncSession]:
    """Get an async session maker bound to the master-data database engine."""
    return async_sessionmaker(get_engine(), expire_on_commit=False)


def get_registry_session_maker() -> async_sessionmaker[AsyncSession]:
    """Get an async session maker bound to the registry database engine."""
    return async_sessionmaker(get_registry_engine(), expire_on_commit=False)
