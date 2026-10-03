"""The change log as an outbox: every event reaches the Audit Manager / WebSub — including
events the database writes itself — failures are retried, and every worker's legacy read
cache follows the legacy tables."""

import asyncio
import json
from datetime import datetime, timedelta, timezone

import httpx
import psycopg2
import pytest
from catalogue_helpers import MAKER, publish_list, submit_and_approve, svc, values
from openg2p_gen2_master_data.helpers import catalogue_integrations as integrations
from openg2p_gen2_master_data.schemas.g2p_catalogue import CreateListDraftPayload
from openg2p_gen2_master_data.services import catalogue_outbox as outbox

pytestmark = pytest.mark.asyncio(loop_scope="session")


class Receiver:
    """Mock Audit Manager + WebSub hub; ``fail`` makes the Audit Manager answer 503."""

    def __init__(self):
        self.audit = []
        self.websub = []
        self.fail = False

    def handler(self, request: httpx.Request):
        if request.url.host == "audit":
            if self.fail:
                return httpx.Response(503)
            self.audit.append(json.loads(request.content))
            return httpx.Response(202)
        form = dict(httpx.QueryParams(request.content.decode()))
        if form.get("hub.mode") == "publish":
            self.websub.append((form["hub.topic"], json.loads(form["hub.content"])))
        return httpx.Response(202)


@pytest.fixture()
def receiver(settings, monkeypatch):
    settings.audit_manager_url = "http://audit"
    settings.websub_hub_url = "http://hub"
    r = Receiver()
    real = httpx.AsyncClient

    def client_factory(*a, **kw):
        kw["transport"] = httpx.MockTransport(r.handler)
        return real(*a, **kw)

    monkeypatch.setattr(integrations.httpx, "AsyncClient", client_factory)
    return r


def pending(db):
    with db.cursor() as cur:
        cur.execute(
            "SELECT event_type FROM g2p_catalogue_change_log WHERE forwarded_at IS NULL ORDER BY event_id"
        )
        return [r[0] for r in cur.fetchall()]


async def test_api_events_delivered_after_commit_and_marked(receiver, db):
    await publish_list("OB", ("A",))
    await integrations.drain_background_tasks()
    assert pending(db) == []
    types = [e["type"] for e in receiver.audit]
    assert types[-1] == "org.openg2p.master_data.list.version.published"
    # Delivered in change-log order, with ids stable per event (retries de-duplicate).
    ids = [e["data"]["context"]["change_log_event_id"] for e in receiver.audit]
    assert ids == sorted(ids)
    assert receiver.audit[-1]["data"]["actor"] == {"type": "user", "id": "checker", "name": "checker"}
    assert [t for t, _ in receiver.websub] == ["openg2p.master-data.list.published"]


async def test_failed_delivery_is_retried_by_the_relay(receiver, db):
    receiver.fail = True
    await publish_list("RETRY", ("A",))
    await integrations.drain_background_tasks()
    # Nothing delivered: everything still pending, in order.
    assert pending(db)[-1] == "list.version.published" and receiver.audit == []
    assert receiver.websub == []  # the audit failure stopped the queue before WebSub
    receiver.fail = False
    n = await outbox.relay_pending()
    assert n == len(receiver.audit) > 0 and pending(db) == []
    assert receiver.audit[-1]["type"] == "org.openg2p.master_data.list.version.published"
    assert [t for t, _ in receiver.websub] == ["openg2p.master-data.list.published"]
    # Nothing left: a second run sends nothing.
    assert await outbox.relay_pending() == 0


async def test_future_version_becoming_effective_is_announced(receiver, db):
    s = svc()
    await publish_list("SOON2", ("A",))
    await s.create_list_draft(CreateListDraftPayload(list_code="SOON2"), MAKER)
    await s.upsert_draft_values("SOON2", values("B"), MAKER)
    await submit_and_approve("SOON2", effective_from=datetime.now(timezone.utc) + timedelta(seconds=2))
    await integrations.drain_background_tasks()
    receiver.audit.clear()
    receiver.websub.clear()
    await asyncio.sleep(2.5)

    # The background cycle (every catalogue_effective_refresh_seconds in production).
    result = await outbox.BackgroundCycle().run_once(force_refresh=True)
    assert result["effective"] == 1 and result["forwarded"] == 1
    assert [e["type"] for e in receiver.audit] == ["org.openg2p.master_data.list.version.effective"]
    event = receiver.audit[0]
    assert event["data"]["actor"]["type"] == "system" and event["data"]["resource"]["version_no"] == 2
    topic, payload = receiver.websub[0]
    assert topic == "openg2p.master-data.list.effective"
    assert (
        payload["list_id"] == "SOON2" and payload["version_no"] == 2 and payload["previous_version_no"] == 1
    )
    assert pending(db) == []


async def test_db_and_loader_events_are_relayed(receiver, db):
    # Written straight into the log, as the migration and the country-pack loader do.
    with db.cursor() as cur:
        cur.execute(
            "SELECT g2p_catalogue_log('list.version.migrated', 'list', 'OLD', 1, 'migration', '{}'::jsonb)"
        )
        cur.execute(
            "SELECT g2p_catalogue_log('geo.version.published', 'geo', 'geography', 4, "
            "'country-pack-loader', '{\"source\": \"pack\"}'::jsonb)"
        )
    assert pending(db) == ["list.version.migrated", "geo.version.published"]
    assert await outbox.relay_pending() == 2
    assert [e["type"] for e in receiver.audit] == [
        "org.openg2p.master_data.list.version.migrated",
        "org.openg2p.master_data.geo.version.published",
    ]
    assert all(e["data"]["actor"]["type"] == "system" for e in receiver.audit)
    # Only version published/effective events go to WebSub.
    assert receiver.websub == [
        (
            "openg2p.master-data.geo.published",
            {
                "source": "pack",
                "event_id": receiver.audit[1]["data"]["context"]["change_log_event_id"],
                "event_type": "geo.version.published",
                "subject_type": "geo",
                "subject_id": "geography",
                "version_no": 4,
            },
        )
    ]


async def test_nothing_configured_marks_events_forwarded(settings, db):
    settings.audit_manager_url = ""
    settings.websub_hub_url = ""
    await publish_list("QUIET", ("A",))
    assert pending(db)  # no immediate attempt without a destination
    assert await outbox.relay_pending() > 0
    assert pending(db) == []


async def test_only_forwarded_at_of_the_change_log_can_change(db):
    await publish_list("AO", ("A",))
    with db.cursor() as cur:
        cur.execute("UPDATE g2p_catalogue_change_log SET forwarded_at = now()")
        with pytest.raises(psycopg2.Error, match="G2P-CAT-IMMUTABLE"):
            cur.execute("UPDATE g2p_catalogue_change_log SET actor = 'someone-else'")
    with db.cursor() as cur:
        with pytest.raises(psycopg2.Error, match="G2P-CAT-IMMUTABLE"):
            cur.execute("DELETE FROM g2p_catalogue_change_log")


async def test_every_worker_drops_its_legacy_cache_when_the_tables_change(db):
    """Another worker or pod publishes: this worker's cache goes within one relay tick."""
    from fastapi_cache import FastAPICache

    await outbox.sync_read_cache()  # this worker has caught up
    backend = FastAPICache.get_backend()
    await backend.set("master-data-cache:probe", b"stale", 300)
    assert not await outbox.sync_read_cache()
    assert await backend.get("master-data-cache:probe") == b"stale"
    # A publish elsewhere re-materialises the legacy tables (bumps the generation).
    with db.cursor() as cur:
        cur.execute("SELECT g2p_catalogue_bump_legacy_generation()")
    assert await outbox.sync_read_cache()
    assert await backend.get("master-data-cache:probe") is None


async def test_upgrade_marks_existing_history_forwarded(db):
    """On an existing deployment the outbox column arrives with history already sent
    (best effort, by the pre-outbox code): it must not be replayed to the Audit Manager."""
    from openg2p_gen2_master_data.app import run_sql
    from openg2p_gen2_master_data.catalogue_sql import catalogue_statements

    await publish_list("OLDHIST", ("A",))
    with db.cursor() as cur:
        cur.execute("ALTER TABLE g2p_catalogue_change_log DROP COLUMN forwarded_at")
    await run_sql(catalogue_statements())
    assert pending(db) == []
    # Idempotent, and new events are pending again.
    await run_sql(catalogue_statements())
    with db.cursor() as cur:
        cur.execute("SELECT g2p_catalogue_log('list.updated', 'list', 'OLDHIST', NULL, 'u', '{}'::jsonb)")
    assert pending(db) == ["list.updated"]
