"""Integration tests for the Master Data catalogue — against a real Postgres.

The database comes from MDS_TEST_DB_* (defaults: localhost:5432, postgres /
postgres, database ``mds_catalogue_test``). The database is dropped and
re-created at the start of the session, migrated with the API's own migration,
and every test starts from empty tables.

    MDS_TEST_DB_PORT=55432 pytest tests
"""

import os

# Settings are read at import time, so the environment comes first.
DB_HOST = os.environ.get("MDS_TEST_DB_HOST", "localhost")
DB_PORT = os.environ.get("MDS_TEST_DB_PORT", "5432")
DB_USER = os.environ.get("MDS_TEST_DB_USER", "postgres")
DB_PASSWORD = os.environ.get("MDS_TEST_DB_PASSWORD", "postgres")
DB_NAME = os.environ.get("MDS_TEST_DB_NAME", "mds_catalogue_test")

os.environ.update(
    {
        "MASTER_DATA_API_DB_HOSTNAME": DB_HOST,
        "MASTER_DATA_API_DB_PORT": DB_PORT,
        "MASTER_DATA_API_DB_USERNAME": DB_USER,
        "MASTER_DATA_API_DB_PASSWORD": DB_PASSWORD,
        "MASTER_DATA_API_DB_DBNAME": DB_NAME,
        "MASTER_DATA_API_CSRF_ENABLED": "false",
        "MASTER_DATA_API_CATALOGUE_EFFECTIVE_REFRESH_SECONDS": "0",
        "MASTER_DATA_API_CATALOGUE_OUTBOX_RELAY_SECONDS": "0",
        "MASTER_DATA_API_CATALOGUE_COUNTRY": "TST",
        "MASTER_DATA_API_AUDIT_MANAGER_URL": "",
        "MASTER_DATA_API_WEBSUB_HUB_URL": "",
        "MASTER_DATA_API_BOUNDARY_S3_ENDPOINT": "",
    }
)

import psycopg2  # noqa: E402
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402

_TABLES = [
    "g2p_catalogue_awe_events",
    "g2p_catalogue_change_log",
    "g2p_catalogue_release_members",
    "g2p_catalogue_releases",
    "g2p_geo_changes",
    "g2p_geo_version_units",
    "g2p_geo_version_levels",
    "g2p_geo_versions",
    "g2p_list_version_values",
    "g2p_list_versions",
    "g2p_attribute_values",
    "g2p_attributes",
    "g2p_geo_level_values",
    "g2p_geo_levels",
    "g2p_sample_individuals",
    "g2p_sample_households",
]


def pg_connect(dbname=DB_NAME):
    return psycopg2.connect(host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD, dbname=dbname)


def _recreate_database():
    admin = pg_connect("postgres")
    admin.autocommit = True
    with admin.cursor() as cur:
        cur.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()",
            (DB_NAME,),
        )
        cur.execute(f'DROP DATABASE IF EXISTS "{DB_NAME}"')
        cur.execute(f'CREATE DATABASE "{DB_NAME}"')
    admin.close()


_recreate_database()

from openg2p_gen2_master_data.app import Initializer, migrate_catalogue  # noqa: E402
from openg2p_gen2_master_data.models import G2PSampleHousehold, G2PSampleIndividual  # noqa: E402

_initializer = Initializer()
APP = _initializer.return_app()


class _TestAuthMiddleware:
    """Stands in for iam-core: ``X-Test-User`` becomes request.state.auth (its ``sub``;
    also its ``name`` unless ``X-Test-Name`` gives a different display name)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            from iam_core.schemas import AuthPrincipal

            headers = dict(scope.get("headers") or [])
            user = headers.get(b"x-test-user")
            if user:
                name = headers.get(b"x-test-name") or user
                scope.setdefault("state", {})
                scope["state"]["auth"] = AuthPrincipal(
                    credentials="test-token", name=name.decode(), sub=user.decode()
                )
        await self.app(scope, receive, send)


APP.add_middleware(_TestAuthMiddleware)


@pytest_asyncio.fixture(scope="session", loop_scope="session", autouse=True)
async def migrated():
    await migrate_catalogue()
    await G2PSampleIndividual.create_migrate()
    await G2PSampleHousehold.create_migrate()
    yield


@pytest.fixture()
def db():
    conn = pg_connect()
    conn.autocommit = True
    yield conn
    conn.close()


@pytest.fixture(autouse=True)
def clean(migrated):
    conn = pg_connect()
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(f"TRUNCATE {', '.join(_TABLES)} RESTART IDENTITY CASCADE")
        cur.execute("DELETE FROM g2p_catalogue_state WHERE key <> 'schema_version'")
    conn.close()
    yield


@pytest.fixture()
def settings():
    from openg2p_gen2_master_data.config import Settings

    cfg = Settings.get_config()
    saved = cfg.model_dump()
    yield cfg
    for k, v in saved.items():
        try:
            setattr(cfg, k, v)
        except Exception:
            pass


def envelope(payload, page=None):
    body = {"request_payload": payload}
    if page:
        body["pagination_request"] = {"current_page": page[0], "page_size": page[1]}
    return {
        "request_header": {
            "sender_app_mnemonic": "test",
            "sender_app_url": "http://test",
            "request_id": "req-1",
            "request_timestamp": "2026-10-02T00:00:00",
        },
        "request_body": body,
    }


@pytest_asyncio.fixture(loop_scope="session")
async def client():
    import httpx
    from fastapi_cache import FastAPICache

    await FastAPICache.clear()
    transport = httpx.ASGITransport(app=APP)
    async with httpx.AsyncClient(transport=transport, base_url="http://mds") as c:

        async def call(path, payload, user="maker", page=None, name=None):
            headers = {"X-Test-User": user, **({"X-Test-Name": name} if name else {})}
            resp = await c.post(path, json=envelope(payload, page), headers=headers)
            assert resp.status_code == 200, resp.text
            return resp.json()

        c.call = call
        yield c
