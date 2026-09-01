# ruff: noqa: E402
import asyncio
import logging

from .config import Settings

_config = Settings.get_config()

from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend
from openg2p_fastapi_common.app import Initializer as BaseInitializer

from .controllers import G2PAttributeController, G2PGeoController
from .models import (
    G2PAttribute,
    G2PAttributeValue,
    G2PGeoLevel,
    G2PGeoLevelValue,
)
from .helpers import RequestResponseHelper

from .services import G2PAttributeService, G2PGeoService

_logger = logging.getLogger(_config.logging_default_logger_name)


class Initializer(BaseInitializer):
    def initialize(self, **kwargs):
        super().initialize(**kwargs)
        RequestResponseHelper()

        G2PGeoService()
        G2PAttributeService()

        G2PGeoController().post_init()
        G2PAttributeController().post_init()

        # Initialize cache
        FastAPICache.init(InMemoryBackend(), prefix="master-data-cache")

    def migrate_database(self, args):
        _logger.info("Starting database migration")

        async def migrate():
            await G2PGeoLevel.create_migrate()
            await G2PGeoLevelValue.create_migrate()
            # Created unconditionally, and empty unless the seed Job was told to
            # load code lists. An empty table answers "this country defines no
            # such list" the same way a missing one would, without making the
            # endpoint's behaviour depend on which switch a deployment set.
            await G2PAttribute.create_migrate()
            await G2PAttributeValue.create_migrate()
            _logger.info("Database migration completed")

        asyncio.run(migrate())
