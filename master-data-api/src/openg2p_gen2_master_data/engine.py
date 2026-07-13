"""Database engine and session management."""

import logging

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from openg2p_fastapi_common.context import dbengine

_logger = logging.getLogger("master-data-engine")

_engine: AsyncEngine | None = None


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


def get_session_maker() -> async_sessionmaker[AsyncSession]:
    """Get an async session maker bound to the master-data database engine."""
    return async_sessionmaker(get_engine(), expire_on_commit=False)
