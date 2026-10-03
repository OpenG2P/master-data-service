# ruff: noqa: E402
import asyncio
import logging

from .config import Settings

_config = Settings.get_config()

from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend  # per worker; see catalogue_outbox.py
from openg2p_fastapi_common.app import Initializer as BaseInitializer
from openg2p_fastapi_common.context import dbengine
from sqlalchemy import text

from .catalogue_sql import catalogue_statements, legacy_alter_statements, schema_marker_statements
from .controllers import G2PAttributeController, G2PCatalogueController, G2PGeoController
from .helpers import RequestResponseHelper
from .helpers.catalogue_integrations import (
    BoundaryStore,
    CatalogueAuditHelper,
    CatalogueAweHelper,
    CatalogueWebSubHelper,
    drain_background_tasks,
)
from .models import (
    G2PAttribute,
    G2PAttributeValue,
    G2PCatalogueAweEvent,
    G2PCatalogueChangeLog,
    G2PCatalogueRelease,
    G2PCatalogueReleaseMember,
    G2PCatalogueState,
    G2PGeoChange,
    G2PGeoLevel,
    G2PGeoLevelValue,
    G2PGeoVersion,
    G2PGeoVersionLevel,
    G2PGeoVersionUnit,
    G2PListVersion,
    G2PListVersionValue,
    G2PSampleHousehold,
    G2PSampleIndividual,
)
from .services.catalogue_outbox import BackgroundCycle
from .services import (
    G2PAttributeService,
    G2PCatalogueAweCallbackService,
    G2PCatalogueFeedService,
    G2PCatalogueGeoService,
    G2PCatalogueListService,
    G2PCatalogueReleaseService,
    G2PGeoService,
)

_logger = logging.getLogger(_config.logging_default_logger_name)


async def run_sql(statements: list[str]) -> None:
    async with dbengine.get().begin() as conn:
        for stmt in statements:
            await conn.exec_driver_sql(stmt)


async def migrate_catalogue() -> dict:
    """Catalogue tables, triggers, functions; then version 1 for pre-catalogue data.

    Idempotent: run on every start. Kept separate so tests can call it.
    """
    # Legacy tables first: the list versions reference g2p_attributes.
    await G2PGeoLevel.create_migrate()
    await G2PGeoLevelValue.create_migrate()
    await G2PAttribute.create_migrate()
    await G2PAttributeValue.create_migrate()
    # create_all never adds a column to an existing table.
    await run_sql(legacy_alter_statements())
    for model in (
        G2PListVersion,
        G2PListVersionValue,
        G2PGeoVersion,
        G2PGeoVersionLevel,
        G2PGeoVersionUnit,
        G2PGeoChange,
        G2PCatalogueRelease,
        G2PCatalogueReleaseMember,
        G2PCatalogueChangeLog,
        G2PCatalogueState,
        G2PCatalogueAweEvent,
    ):
        await model.create_migrate()
    await run_sql(catalogue_statements())
    # Every existing list -> version 1 PUBLISHED; existing geography -> geography
    # version 1 PUBLISHED. Skips anything that already has a version.
    async with dbengine.get().begin() as conn:
        summary = (
            await conn.execute(text("SELECT g2p_catalogue_bootstrap_v1(:actor)"), {"actor": "migration"})
        ).scalar_one()
        await conn.execute(text("SELECT g2p_catalogue_refresh_current()"))
    await run_sql(schema_marker_statements())
    return summary


class Initializer(BaseInitializer):
    def initialize(self, **kwargs):
        super().initialize(**kwargs)
        RequestResponseHelper()

        CatalogueAuditHelper()
        CatalogueWebSubHelper()
        CatalogueAweHelper()
        BoundaryStore()

        G2PGeoService()
        G2PAttributeService()
        G2PCatalogueListService()
        G2PCatalogueGeoService()
        G2PCatalogueReleaseService()
        G2PCatalogueFeedService()
        G2PCatalogueAweCallbackService()

        G2PGeoController().post_init()
        G2PAttributeController().post_init()
        G2PCatalogueController().post_init()

        # Initialize cache
        FastAPICache.init(InMemoryBackend(), prefix="master-data-cache")
        self._refresh_task = None

    async def fastapi_app_startup(self, app):
        await super().fastapi_app_startup(app)
        # One loop per worker: brings future-effective versions into effect
        # (every catalogue_effective_refresh_seconds), relays undelivered
        # change-log events to the Audit Manager / WebSub (one worker in the
        # deployment at a time, advisory lock) and drops this worker's legacy
        # read cache when another worker or pod changed the legacy tables. See
        # services/catalogue_outbox.py.
        if dbengine.get() is not None and (
            _config.catalogue_effective_refresh_seconds or _config.catalogue_outbox_relay_seconds
        ):
            self._refresh_task = asyncio.create_task(BackgroundCycle().loop())

    async def fastapi_app_shutdown(self, app):
        if self._refresh_task:
            self._refresh_task.cancel()
        await drain_background_tasks()
        await super().fastapi_app_shutdown(app)

    def migrate_database(self, args):
        _logger.info("Starting database migration")

        async def migrate():
            summary = await migrate_catalogue()
            _logger.info("Catalogue migration: %s", summary)
            # Sample tables last — the geo-seed Job waits on
            # g2p_sample_households as proof the full migration finished (and,
            # since the catalogue, on g2p_catalogue_state.schema_version).
            await G2PSampleIndividual.create_migrate()
            await G2PSampleHousehold.create_migrate()
            _logger.info("Database migration completed")

        asyncio.run(migrate())
