"""/samples reads: the country pack's sample people and households, over HTTP."""

import pytest

ASYNC = pytest.mark.asyncio(loop_scope="session")


def _load(db):
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO g2p_sample_households (household_id, head_individual_id, size_total, geo_pcode, "
            "country) VALUES ('HH1', 'P1', 2, 'ET0412', 'ETH'), ('HH2', 'P3', 1, 'ET0101', 'ETH')"
        )
        cur.execute(
            "INSERT INTO g2p_sample_individuals (individual_id, household_id, given_name, full_name, gender, "
            "age, birth_date, national_id, geo_pcode, address_parts, country) VALUES "
            "('P1', 'HH1', 'Almaz', 'Almaz Bekele', 'FEMALE', 34, '1992-03-05', 'N1', 'ET0412', "
            " '{\"kebele\": \"01\"}', 'ETH'),"
            "('P2', 'HH1', 'Bekele', 'Bekele Tadesse', 'MALE', 12, NULL, NULL, 'ET0412', NULL, 'ETH'),"
            "('P3', 'HH2', 'Chaltu', 'Chaltu Abdi', 'FEMALE', 51, NULL, 'N3', 'ET0101', NULL, 'ETH')"
        )


@ASYNC
async def test_individuals_paged_and_filtered(client, db):
    _load(db)
    body = await client.call("/samples/get_individuals", {}, page=(1, 2))
    assert body["response_header"]["response_status"] == "SUCCESS"
    payload = body["response_body"]["response_payload"]
    assert payload["total"] == 3
    assert [p["individual_id"] for p in payload["individuals"]] == ["P1", "P2"]
    assert payload["individuals"][0]["birth_date"] == "1992-03-05"
    assert payload["individuals"][0]["address_parts"] == {"kebele": "01"}
    assert body["response_body"]["pagination_response"] == {"number_of_items": 3, "number_of_pages": 2}

    page2 = await client.call("/samples/get_individuals", {}, page=(2, 2))
    assert [p["individual_id"] for p in page2["response_body"]["response_payload"]["individuals"]] == ["P3"]

    household = await client.call("/samples/get_individuals", {"household_id": "HH1"})
    assert [p["individual_id"] for p in household["response_body"]["response_payload"]["individuals"]] == [
        "P1",
        "P2",
    ]
    place = await client.call("/samples/get_individuals", {"geo_pcode": "ET0101"})
    assert place["response_body"]["response_payload"]["total"] == 1


@ASYNC
async def test_households(client, db):
    _load(db)
    body = await client.call("/samples/get_households", {"country": "ETH"})
    payload = body["response_body"]["response_payload"]
    assert [h["household_id"] for h in payload["households"]] == ["HH1", "HH2"]
    assert payload["households"][0]["head_individual_id"] == "P1"


@ASYNC
async def test_empty_without_samples(client):
    body = await client.call("/samples/get_individuals", {})
    assert body["response_body"]["response_payload"] == {"individuals": [], "total": 0}


def test_samples_are_csrf_exempt_reads():
    from openg2p_gen2_master_data.main import MASTER_DATA_CSRF_EXCLUDED_PATHS

    assert "/samples/get_individuals" in MASTER_DATA_CSRF_EXCLUDED_PATHS
    assert "/samples/get_households" in MASTER_DATA_CSRF_EXCLUDED_PATHS


def test_samples_require_an_authenticated_caller():
    from iam_core.user_auth.decorators import get_required_permissions
    from openg2p_gen2_master_data.controllers import G2PSampleController

    assert get_required_permissions(G2PSampleController.get_individuals) == set()
    assert get_required_permissions(G2PSampleController.get_households) == set()
