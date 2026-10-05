"""Releases (pinning), the change feed, AWE approval mode, Audit Manager emission."""

import json
import time

import httpx
import psycopg2
import pytest
from catalogue_helpers import CHECKER, MAKER, publish_list, svc, values
from openg2p_gen2_master_data.helpers import catalogue_integrations as integrations
from openg2p_gen2_master_data.schemas.g2p_catalogue import (
    CreateListDraftPayload,
    CreateListPayload,
    CreateReleasePayload,
    DecideDraftPayload,
    ReleaseMemberInput,
    SetReleaseMembersPayload,
    SubmitDraftPayload,
    VersionSelector,
)
from openg2p_gen2_master_data.services import G2PCatalogueFeedService, G2PCatalogueReleaseService
from openg2p_gen2_master_data.services.catalogue_common import CatalogueError

pytestmark = pytest.mark.asyncio(loop_scope="session")


def rel():
    return G2PCatalogueReleaseService.get_component()


async def test_release_pins_versions(db):
    s = svc()
    await publish_list("CROP", ("TEFF",))
    await rel().create_release(CreateReleasePayload(release_code="2027.1", title="Season 2027"), MAKER)
    with pytest.raises(CatalogueError, match="not published"):
        await rel().set_release_members(
            SetReleaseMembersPayload(
                release_code="2027.1", members=[ReleaseMemberInput(list_code="CROP", version_no=2)]
            ),
            MAKER,
        )
    await rel().set_release_members(
        SetReleaseMembersPayload(
            release_code="2027.1", members=[ReleaseMemberInput(list_code="CROP", version_no=1)]
        ),
        MAKER,
    )
    with pytest.raises(CatalogueError) as e:
        await rel().publish_release("2027.1", MAKER)
    assert e.value.code == "G2P-CAT-403"
    info, members = await rel().publish_release("2027.1", CHECKER)
    assert info.status == "PUBLISHED" and [(m.list_code, m.version_no) for m in members] == [("CROP", 1)]

    # Version 2 is published later; the release still answers with version 1.
    await s.create_list_draft(CreateListDraftPayload(list_code="CROP"), MAKER)
    await s.upsert_draft_values("CROP", values("MAIZE"), MAKER)
    await s.submit_draft(SubmitDraftPayload(list_code="CROP"), MAKER)
    await s.approve_draft(DecideDraftPayload(list_code="CROP"), CHECKER)
    _, v, vals, _ = await s.get_list_values("CROP", VersionSelector(release="2027.1"))
    assert v.version_no == 1 and [x.value_code for x in vals] == ["TEFF"]
    _, latest, _, _ = await s.get_list_values("CROP", None)
    assert latest.version_no == 2
    with pytest.raises(CatalogueError, match="cannot be changed"):
        await rel().set_release_members(SetReleaseMembersPayload(release_code="2027.1", members=[]), MAKER)
    with db.cursor() as cur:
        with pytest.raises(psycopg2.Error, match="G2P-CAT-IMMUTABLE"):
            cur.execute("DELETE FROM g2p_catalogue_release_members WHERE release_code = '2027.1'")


async def test_release_checks_list_refs_within_release():
    s = svc()
    await publish_list("CROP", ("TEFF",))
    schema = {"type": "object", "properties": {"crop": {"type": "string", "x-list-ref": "CROP"}}}
    await s.create_list(
        CreateListPayload(list_code="VARIETY", display="Variety", attribute_schema=schema), MAKER
    )
    # MAIZE arrives in CROP v2 (published first), and VARIETY v1 references it...
    await s.create_list_draft(CreateListDraftPayload(list_code="CROP"), MAKER)
    await s.upsert_draft_values("CROP", values("MAIZE"), MAKER)
    await s.submit_draft(SubmitDraftPayload(list_code="CROP"), MAKER)
    await s.approve_draft(DecideDraftPayload(list_code="CROP"), CHECKER)
    from openg2p_gen2_master_data.schemas.g2p_catalogue import DraftValueInput

    await s.upsert_draft_values(
        "VARIETY", [DraftValueInput(value_code="BH661", display="BH661", attributes={"crop": "MAIZE"})], MAKER
    )
    await s.submit_draft(SubmitDraftPayload(list_code="VARIETY"), MAKER)
    await s.approve_draft(DecideDraftPayload(list_code="VARIETY"), CHECKER)
    # ...so a release pinning CROP v1 with VARIETY v1 is inconsistent.
    await rel().create_release(CreateReleasePayload(release_code="R1"), MAKER)
    await rel().set_release_members(
        SetReleaseMembersPayload(
            release_code="R1",
            members=[
                ReleaseMemberInput(list_code="CROP", version_no=1),
                ReleaseMemberInput(list_code="VARIETY", version_no=1),
            ],
        ),
        MAKER,
    )
    with pytest.raises(CatalogueError, match="MAIZE"):
        await rel().publish_release("R1", CHECKER)


async def test_change_feed_cursor():
    await publish_list("A1", ("X",))
    await publish_list("A2", ("Y",))
    feed = G2PCatalogueFeedService.get_component()
    events, cursor, more = await feed.get_changes(0, 3)
    assert len(events) == 3 and more
    ids = [e.event_id for e in events]
    assert ids == sorted(ids) and cursor == ids[-1]
    rest, cursor2, more2 = await feed.get_changes(cursor, 100)
    assert not more2 and all(e.event_id > cursor for e in rest)
    types = [e.event_type for e in events + rest]
    assert types.count("list.version.published") == 2
    assert {
        "list.created",
        "list.draft.created",
        "list.draft.values_changed",
        "list.draft.submitted",
        "list.draft.approved",
    } <= set(types)
    again, cursor3, _ = await feed.get_changes(cursor2, 100)
    assert again == [] and cursor3 == cursor2
    only, _, _ = await feed.get_changes(0, 100, "list", "A2", ["list.version.published"])
    assert len(only) == 1 and only[0].version_no == 1


async def test_awe_mode_publishes_on_signed_callback(settings, monkeypatch, client):
    settings.catalogue_approval_mode = "awe"
    settings.awe_base_url = "http://awe"
    settings.awe_callback_hmac_secret = "s3cret"
    calls = []

    async def fake_create_request(self, token, **kw):
        calls.append((token, kw))
        return {"request_id": "awe-req-1", "status": "pending"}

    monkeypatch.setattr(integrations.CatalogueAweHelper, "create_request", fake_create_request)
    s = svc()
    await s.create_list(CreateListPayload(list_code="AWEL", display="Awe list", owner_org="MoA"), MAKER)
    await s.upsert_draft_values("AWEL", values("A"), MAKER)
    _, draft = await s.submit_draft(SubmitDraftPayload(list_code="AWEL"), MAKER)
    assert draft.approval_ref == "awe-req-1"
    token, kw = calls[0]
    assert token == "maker-token" and kw["artifact_type"] == "master_data.list_version"
    assert kw["artifact_id"] == "AWEL:1" and kw["context"]["owner_org"] == "MoA"
    with pytest.raises(CatalogueError, match="AWE"):
        await s.approve_draft(DecideDraftPayload(list_code="AWEL"), CHECKER)

    event = {
        "event_id": "ev-1",
        "event_type": "request_approved",
        "request_id": "awe-req-1",
        "artifact_type": "master_data.list_version",
        "artifact_id": "AWEL:1",
        "status": "approved",
        "actor": "approver-x",
        "occurred_at": "2026-10-02T10:00:00Z",
    }
    body = json.dumps(event).encode()
    ts = int(time.time())
    bad = await client.post(
        "/catalogue/awe/callback",
        content=body,
        headers={"X-Approval-Timestamp": str(ts), "X-Approval-Signature": "sha256=00"},
    )
    assert bad.status_code == 401
    headers = {
        "X-Approval-Timestamp": str(ts),
        "X-Approval-Signature": integrations.sign_awe_webhook("s3cret", ts, body),
        "X-Approval-Event-Id": "ev-1",
        "Content-Type": "application/json",
    }
    ok = await client.post("/catalogue/awe/callback", content=body, headers=headers)
    assert ok.status_code == 200 and ok.json()["applied"] is True
    _, versions = await s.get_list_versions("AWEL")
    assert versions[0].status == "PUBLISHED" and versions[0].decided_by == "approver-x"
    dup = await client.post("/catalogue/awe/callback", content=body, headers=headers)
    assert dup.json()["message"] == "duplicate"


async def test_audit_events_are_cloudevents(settings, monkeypatch):
    settings.audit_manager_url = "http://audit"
    posted = []

    def handler(request: httpx.Request):
        posted.append((str(request.url), json.loads(request.content)))
        return httpx.Response(202)

    real = httpx.AsyncClient

    def client_factory(*a, **kw):
        kw["transport"] = httpx.MockTransport(handler)
        return real(*a, **kw)

    monkeypatch.setattr(integrations.httpx, "AsyncClient", client_factory)
    await publish_list("AUD", ("A",))
    await integrations.drain_background_tasks()
    types = [e["type"] for _, e in posted]
    assert "org.openg2p.master_data.list.version.published" in types
    url, event = posted[-1]
    assert url == "http://audit/v1/auditmanager/events"
    assert event["specversion"] == "1.0" and event["source"] == "/openg2p/master-data"
    assert event["data"]["actor"]["id"] in ("maker", "checker") and event["data"]["outcome"] == "success"
    assert event["data"]["resource"]["type"] == "master_data.list"


async def test_websub_publish_on_version_published(settings, monkeypatch):
    settings.websub_hub_url = "http://hub"
    posted = []

    def handler(request: httpx.Request):
        posted.append(dict(httpx.QueryParams(request.content.decode())))
        return httpx.Response(202)

    real = httpx.AsyncClient
    monkeypatch.setattr(
        integrations.httpx,
        "AsyncClient",
        lambda *a, **kw: real(*a, transport=httpx.MockTransport(handler), **kw),
    )
    await publish_list("WS", ("A",))
    await integrations.drain_background_tasks()
    modes = [(p["hub.mode"], p["hub.topic"]) for p in posted]
    assert ("publish", "openg2p.master-data.list.published") in modes
    content = json.loads(next(p for p in posted if p["hub.mode"] == "publish")["hub.content"])
    assert content["list_id"] == "WS" and content["version_no"] == 1


async def test_release_publisher_must_not_have_set_its_members():
    from openg2p_gen2_master_data.services.catalogue_common import Actor

    await publish_list("CROPR", ("TEFF",))
    creator, member_setter, publisher = Actor("u-creator"), Actor("u-setter"), Actor("u-publisher")
    await rel().create_release(CreateReleasePayload(release_code="R6"), creator)
    info, _ = await rel().set_release_members(
        SetReleaseMembersPayload(
            release_code="R6", members=[ReleaseMemberInput(list_code="CROPR", version_no=1)]
        ),
        member_setter,
    )
    assert info.created_by == "u-creator" and info.members_set_by == "u-setter"
    for maker in (creator, member_setter):
        with pytest.raises(CatalogueError, match="last set its members") as e:
            await rel().publish_release("R6", maker)
        assert e.value.code == "G2P-CAT-403"
    info, _ = await rel().publish_release("R6", publisher)
    assert info.status == "PUBLISHED" and info.published_by == "u-publisher"


async def test_maker_checker_compares_stable_ids_not_display_names(db):
    """Two different people may share a display name; one person may change theirs."""
    from openg2p_gen2_master_data.services.catalogue_common import Actor

    s = svc()
    maker = Actor("sub-1111", name="Abebe Kebede")
    await s.create_list(CreateListPayload(list_code="IDS", display="Ids"), maker)
    await s.upsert_draft_values("IDS", values("A"), maker)
    await s.submit_draft(SubmitDraftPayload(list_code="IDS"), maker)
    # The same person under another display name is still the maker.
    with pytest.raises(CatalogueError) as e:
        await s.approve_draft(DecideDraftPayload(list_code="IDS"), Actor("sub-1111", name="A. Kebede"))
    assert e.value.code == "G2P-CAT-403"
    # A different person with the same display name may approve.
    _, v = await s.approve_draft(DecideDraftPayload(list_code="IDS"), Actor("sub-2222", name="Abebe Kebede"))
    assert v.status == "PUBLISHED"
    assert (v.created_by, v.submitted_by, v.decided_by) == ("sub-1111", "sub-1111", "sub-2222")
    with db.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT actor, actor_name FROM g2p_catalogue_change_log WHERE subject_id = 'IDS' ORDER BY 1"
        )
        assert cur.fetchall() == [("sub-1111", "Abebe Kebede"), ("sub-2222", "Abebe Kebede")]


async def test_actor_from_request_uses_sub_over_http(client, db):
    """Over HTTP: maker and checker share a display name but not a sub."""
    from types import SimpleNamespace

    from iam_core.schemas import AuthPrincipal
    from openg2p_gen2_master_data.services.catalogue_common import actor_from_request

    req = SimpleNamespace(
        state=SimpleNamespace(auth=AuthPrincipal(credentials="t", name="Abebe", sub="u-1")), headers={}
    )
    actor = actor_from_request(req)
    assert (actor.id, actor.name, actor.token) == ("u-1", "Abebe", "t")
    # An IdP without sub: preferred_username from the (already validated) token.
    import base64

    claims = (
        base64.urlsafe_b64encode(json.dumps({"preferred_username": "abebe"}).encode()).decode().rstrip("=")
    )
    req.state.auth = AuthPrincipal(credentials=f"h.{claims}.s", name=None, sub=None)
    actor = actor_from_request(req)
    assert (actor.id, actor.name) == ("abebe", "abebe")

    def ok(resp):
        assert resp["response_header"]["response_status"] == "SUCCESS", resp["response_header"]
        return resp["response_body"]["response_payload"]

    ok(
        await client.call(
            "/catalogue/create_list", {"list_code": "HTTPIDS", "display": "X"}, user="u-1", name="Abebe"
        )
    )
    ok(
        await client.call(
            "/catalogue/upsert_draft_values",
            {"list_code": "HTTPIDS", "values": [{"value_code": "A", "display": "A"}]},
            user="u-1",
            name="Abebe",
        )
    )
    ok(await client.call("/catalogue/submit_draft", {"list_code": "HTTPIDS"}, user="u-1", name="Abebe"))
    published = ok(
        await client.call("/catalogue/approve_draft", {"list_code": "HTTPIDS"}, user="u-2", name="Abebe")
    )
    assert published["draft"]["status"] == "PUBLISHED" and published["draft"]["decided_by"] == "u-2"
    feed = ok(await client.call("/catalogue/get_changes", {"cursor": 0, "subject_id": "HTTPIDS"}))
    assert {(e["actor"], e["actor_name"]) for e in feed["events"]} == {("u-1", "Abebe"), ("u-2", "Abebe")}


async def test_display_names_are_returned_next_to_ids(client, db):
    """*_by hold stable ids; *_by_name the display names, written with them."""
    from openg2p_gen2_master_data.schemas.g2p_catalogue import (
        CreateGeoDraftPayload,
        DecideGeoDraftPayload,
        DraftLevelInput,
        DraftUnitInput,
        SubmitGeoDraftPayload,
    )
    from openg2p_gen2_master_data.services import G2PCatalogueGeoService
    from openg2p_gen2_master_data.services.catalogue_common import Actor

    abebe, sara, lily = Actor("u-1", name="Abebe"), Actor("u-2", name="Sara"), Actor("u-3", name="Lily")
    s = svc()
    # Lists: created by Abebe, edited by Lily, submitted by Abebe, approved by Sara.
    await s.create_list(CreateListPayload(list_code="NAMES", display="Names"), abebe)
    await s.upsert_draft_values("NAMES", values("A"), lily)
    await s.submit_draft(SubmitDraftPayload(list_code="NAMES"), abebe)
    _, v = await s.approve_draft(DecideDraftPayload(list_code="NAMES"), sara)
    assert (v.created_by, v.created_by_name, v.updated_by, v.updated_by_name) == (
        "u-1",
        "Abebe",
        "u-3",
        "Lily",
    )
    assert (v.submitted_by, v.submitted_by_name, v.decided_by, v.decided_by_name) == (
        "u-1",
        "Abebe",
        "u-2",
        "Sara",
    )
    # Over HTTP, and for a rejected / discarded draft too.
    await s.create_list_draft(CreateListDraftPayload(list_code="NAMES"), lily)
    await s.discard_draft("NAMES", sara)

    def ok(resp):
        assert resp["response_header"]["response_status"] == "SUCCESS", resp["response_header"]
        return resp["response_body"]["response_payload"]

    versions = ok(await client.call("/catalogue/get_list_versions", {"list_code": "NAMES"}))["versions"]
    by_no = {x["version_no"]: x for x in versions}
    assert by_no[1]["decided_by_name"] == "Sara" and by_no[1]["created_by_name"] == "Abebe"
    assert (by_no[2]["status"], by_no[2]["created_by_name"], by_no[2]["decided_by_name"]) == (
        "DISCARDED",
        "Lily",
        "Sara",
    )

    # Geography, including the change events added automatically at submit.
    g = G2PCatalogueGeoService.get_component()
    await g.create_geo_draft(CreateGeoDraftPayload(), abebe)
    await g.upsert_draft_levels([DraftLevelInput(level_id="l0", level_mnemonic="country")], abebe)
    await g.upsert_draft_units([DraftUnitInput(unit_id="XX", level_id="l0", name="Country")], abebe)
    await g.submit_geo_draft(SubmitGeoDraftPayload(), abebe)
    await g.approve_geo_draft(DecideGeoDraftPayload(), sara)
    await g.create_geo_draft(CreateGeoDraftPayload(), lily)
    await g.upsert_draft_units([DraftUnitInput(unit_id="YY", level_id="l0", name="Other")], lily)
    await g.submit_geo_draft(SubmitGeoDraftPayload(), lily)
    gv = await g.approve_geo_draft(DecideGeoDraftPayload(), sara)
    assert (gv.created_by_name, gv.submitted_by_name, gv.decided_by, gv.decided_by_name) == (
        "Lily",
        "Lily",
        "u-2",
        "Sara",
    )
    changes = await g.get_geo_changes(None, None, None, False)
    assert [(c.change_type, c.created_by, c.created_by_name) for c in changes] == [("CREATE", "u-3", "Lily")]

    # Releases.
    await rel().create_release(CreateReleasePayload(release_code="RN"), abebe)
    await rel().set_release_members(
        SetReleaseMembersPayload(
            release_code="RN", members=[ReleaseMemberInput(list_code="NAMES", version_no=1)]
        ),
        lily,
    )
    info, _ = await rel().publish_release("RN", sara)
    assert (info.created_by_name, info.members_set_by_name, info.published_by_name) == (
        "Abebe",
        "Lily",
        "Sara",
    )
    assert (info.created_by, info.members_set_by, info.published_by) == ("u-1", "u-3", "u-2")

    # A system actor has no display name: readers fall back to the id.
    assert Actor.system("awe").display_name is None


async def test_change_feed_newest():
    await publish_list("N1", ("X",))
    await publish_list("N2", ("Y",))
    feed = G2PCatalogueFeedService.get_component()
    everything, last, _ = await feed.get_changes(0, 1000)
    events, cursor, more = await feed.get_changes(0, 3, newest=True)
    assert [e.event_id for e in events] == [e.event_id for e in everything[-3:]]
    assert cursor == last and not more
