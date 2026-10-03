"""Over HTTP: legacy endpoints keep their shape and show the current published state;
legacy writes land in drafts; the /catalogue envelope, errors and OpenAPI docs."""

import pytest
from catalogue_helpers import publish_list

pytestmark = pytest.mark.asyncio(loop_scope="session")


def ok(resp):
    assert resp["response_header"]["response_status"] == "SUCCESS", resp["response_header"]
    return resp["response_body"]["response_payload"]


def err(resp):
    assert resp["response_header"]["response_status"] == "ERROR"
    return resp["response_header"]["response_error_code"], resp["response_header"]["response_error_message"]


async def test_legacy_reads_show_current_published(client):
    await publish_list("GENDER", ("FEMALE", "MALE"))
    attrs = ok(await client.call("/attributes/get_all_attributes", {}))["attributes"]
    gender = next(a for a in attrs if a["attribute_id"] == "GENDER")
    assert gender["attribute_code"] == "GENDER" and gender["current_version_no"] == 1
    payload = ok(await client.call("/attributes/get_attribute_values", {"attribute_id": "GENDER"}))
    assert [v["value_code"] for v in payload["attribute_values"]] == ["FEMALE", "MALE"]
    assert payload["list_versions"] == {"GENDER": 1} and payload["total"] == 2


async def test_legacy_writes_go_to_drafts(client):
    await publish_list("WATER", ("PIPED", "WELL"))
    added = ok(
        await client.call(
            "/attributes/add_attribute_value",
            {"attribute_id": "WATER", "value_code": "RAIN", "value_display": "Rain", "sort_order": 9},
        )
    )
    assert added["value_code"] == "RAIN" and added["attribute_id"] == "WATER"
    # Published data is unchanged...
    legacy = ok(await client.call("/attributes/get_attribute_values", {"attribute_id": "WATER"}))
    assert [v["value_code"] for v in legacy["attribute_values"]] == ["PIPED", "WELL"]
    # ...the draft has it.
    draft = ok(await client.call("/catalogue/get_list_values", {"list_code": "WATER", "version": "draft"}))
    assert draft["version"]["status"] == "DRAFT" and draft["version"]["version_no"] == 2
    assert {v["value_code"] for v in draft["values"]} == {"PIPED", "WELL", "RAIN"}

    well_id = next(v["value_id"] for v in draft["values"] if v["value_code"] == "WELL")
    ok(
        await client.call(
            "/attributes/delete_attribute_value", {"value_id": well_id, "attribute_id": "WATER"}
        )
    )
    upd = ok(
        await client.call(
            "/attributes/update_attribute", {"attribute_id": "WATER", "attribute_display": "Water source"}
        )
    )
    assert upd["attribute_display"] == "Water source"
    diff = ok(await client.call("/catalogue/get_list_diff", {"list_code": "WATER", "to_version": "draft"}))
    assert [v["value_code"] for v in diff["retired"]] == ["WELL"]
    assert diff["metadata_changes"]["display"]["after"] == "Water source"

    ok(await client.call("/catalogue/submit_draft", {"list_code": "WATER"}, user="maker"))
    code, _ = err(await client.call("/catalogue/approve_draft", {"list_code": "WATER"}, user="maker"))
    assert code == "G2P-CAT-403"
    published = ok(
        await client.call(
            "/catalogue/approve_draft", {"list_code": "WATER", "decision_note": "ok"}, user="checker"
        )
    )
    assert published["draft"]["status"] == "PUBLISHED"
    legacy = ok(await client.call("/attributes/get_attribute_values", {"attribute_id": "WATER"}))
    assert sorted(v["value_code"] for v in legacy["attribute_values"]) == ["PIPED", "RAIN"]
    attrs = ok(await client.call("/attributes/get_all_attributes", {}))["attributes"]
    assert next(a for a in attrs if a["attribute_id"] == "WATER")["attribute_display"] == "Water source"


async def test_legacy_add_attribute_creates_unpublished_list(client):
    created = ok(
        await client.call("/attributes/add_attribute", {"attribute_code": "NEWL", "attribute_display": "New"})
    )
    assert created["current_version_no"] is None
    lists = ok(await client.call("/catalogue/get_lists", {}))["lists"]
    newl = next(x for x in lists if x["list_code"] == "NEWL")
    assert newl["open_draft_version_no"] == 1 and newl["current_version_no"] is None
    # Never published: deleting really deletes.
    ok(await client.call("/attributes/delete_attribute", {"attribute_id": created["attribute_id"]}))
    lists = ok(await client.call("/catalogue/get_lists", {}))["lists"]
    assert not any(x["list_code"] == "NEWL" for x in lists)


async def test_legacy_geo_writes_go_to_geo_draft(client):
    ok(await client.call("/catalogue/create_geo_draft", {"change_note": "v1"}))
    ok(
        await client.call(
            "/catalogue/upsert_draft_levels",
            {
                "levels": [
                    {"level_id": "l0", "level_mnemonic": "country"},
                    {"level_id": "l1", "level_mnemonic": "region", "parent_level_id": "l0"},
                ]
            },
        )
    )
    ok(
        await client.call(
            "/catalogue/upsert_draft_units",
            {
                "units": [
                    {"unit_id": "XX", "level_id": "l0", "name": "Country"},
                    {"unit_id": "R1", "level_id": "l1", "name": "North", "parent_unit_id": "XX"},
                ]
            },
        )
    )
    ok(await client.call("/catalogue/submit_geo_draft", {}))
    ok(await client.call("/catalogue/approve_geo_draft", {}, user="checker"))
    resp = await client.post(
        "/geo/get_geo_level_values",
        json={
            "request_header": {
                "sender_app_mnemonic": "t",
                "sender_app_url": "t",
                "request_id": "1",
                "request_timestamp": "2026-10-02T00:00:00",
            },
            "request_body": {"request_payload": {"level_id": "l1"}},
        },
        headers={"X-Test-User": "maker"},
    )
    regions = resp.json()["response_body"]["response_payload"]
    assert [r["level_value_id"] for r in regions] == ["R1"]

    added = ok(
        await client.call(
            "/geo/add_geo_level_value",
            {"level_id": "l1", "level_value_mnemonic": "South", "parent_level_value_id": "XX"},
        )
    )
    resp = await client.post(
        "/geo/get_all_geo_levels",
        json={
            "request_header": {
                "sender_app_mnemonic": "t",
                "sender_app_url": "t",
                "request_id": "1",
                "request_timestamp": "2026-10-02T00:00:00",
            },
            "request_body": {"request_payload": {}},
        },
        headers={"X-Test-User": "maker"},
    )
    assert len(resp.json()["response_body"]["response_payload"]) == 2
    units = ok(await client.call("/catalogue/get_geo_units", {"level": "region"}))
    assert [u["unit_id"] for u in units["units"]] == ["R1"] and units["version"]["version_no"] == 1
    draft = ok(await client.call("/catalogue/get_geo_units", {"level": "region", "version": "draft"}))
    assert {u["unit_id"] for u in draft["units"]} == {"R1", added["level_value_id"]}
    ok(await client.call("/geo/delete_geo_level_value", {"level_value_id": "R1"}))
    draft = ok(
        await client.call(
            "/catalogue/get_geo_units", {"level": "region", "version": "draft", "include_retired": True}
        )
    )
    assert {u["unit_id"]: u["status"] for u in draft["units"]}["R1"] == "RETIRED"


async def test_catalogue_envelope_errors_and_paging(client):
    code, msg = err(await client.call("/catalogue/get_list", {"list_code": "NOPE"}))
    assert code == "G2P-CAT-404" and "NOPE" in msg
    await publish_list("PAGED", tuple(f"V{i:02d}" for i in range(7)))
    resp = await client.call("/catalogue/get_list_values", {"list_code": "PAGED"}, page=(2, 3))
    payload = ok(resp)
    assert [v["value_code"] for v in payload["values"]] == ["V03", "V04", "V05"]
    assert payload["total"] == 7 and resp["response_body"]["pagination_response"] == {
        "number_of_items": 7,
        "number_of_pages": 3,
    }
    one = ok(
        await client.call(
            "/catalogue/get_list_value", {"list_code": "PAGED", "value_code": "V06", "version": 1}
        )
    )
    assert one["value"]["value_code"] == "V06" and one["version"]["is_latest"] is True
    cfg = ok(await client.call("/catalogue/get_catalogue_config", {}))
    assert cfg["approval_mode"] == "permission" and cfg["boundary_store_enabled"] is False
    feed = ok(await client.call("/catalogue/get_changes", {"cursor": 0, "limit": 2}))
    assert (
        len(feed["events"]) == 2
        and feed["has_more"]
        and feed["next_cursor"] == feed["events"][-1]["event_id"]
    )


async def test_openapi_documents_every_catalogue_endpoint(client):
    spec = (await client.get("/openapi.json")).json()
    paths = {p: v["post"] for p, v in spec["paths"].items() if p.startswith("/catalogue/")}
    assert len(paths) == 44  # 16 list + 19 geography + 6 release + 2 feed/config + AWE callback
    for path, op in paths.items():
        assert op.get("description"), path
        assert op.get("summary"), path
