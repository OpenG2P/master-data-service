# ruff: noqa: E402
import asyncio
import logging

from .config import Settings

_config = Settings.get_config()

from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend
from openg2p_fastapi_common.app import Initializer as BaseInitializer

from .controllers import G2PGeoController, G2PPartnerController
from .models import G2PGeoLevel, G2PGeoLevelValue, G2PPartner
from .helpers import RequestResponseHelper

from .services import G2PGeoService, G2PPartnerService

_logger = logging.getLogger(_config.logging_default_logger_name)


class Initializer(BaseInitializer):
    def initialize(self, **kwargs):
        super().initialize(**kwargs)
        RequestResponseHelper()

        G2PGeoService()
        G2PPartnerService()

        G2PGeoController().post_init()
        G2PPartnerController().post_init()

        # Initialize cache
        FastAPICache.init(InMemoryBackend(), prefix="master-data-cache")

    def migrate_database(self, args):
        _logger.info("Starting database migration")

        async def migrate():
            await G2PGeoLevel.create_migrate()
            await G2PGeoLevelValue.create_migrate()
            await G2PPartner.create_migrate()
            _logger.info("Database migration completed")

        asyncio.run(migrate())
