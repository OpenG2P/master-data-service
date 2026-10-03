"""Geography versioning: lineage events, validation, crosswalk across versions, boundaries."""

import json

import psycopg2
import pytest
from catalogue_helpers import CHECKER, MAKER
from openg2p_gen2_master_data.schemas.g2p_catalogue import (
    CreateGeoDraftPayload,
    DecideGeoDraftPayload,
    DraftLevelInput,
    DraftUnitInput,
    RecordGeoChangePayload,
    SubmitGeoDraftPayload,
    VersionSelector,
)
from openg2p_gen2_master_data.services import G2PCatalogueGeoService
from openg2p_gen2_master_data.services.catalogue_common import CatalogueError

pytestmark = pytest.mark.asyncio(loop_scope="session")


def geo():
    return G2PCatalogueGeoService.get_component()


def unit(uid, level, name, parent=None):
    return DraftUnitInput(unit_id=uid, level_id=level, name=name, parent_unit_id=parent)


async def approve():
    await geo().submit_geo_draft(SubmitGeoDraftPayload(), MAKER)
    return await geo().approve_geo_draft(DecideGeoDraftPayload(), CHECKER)


async def make_v1():
    g = geo()
    await g.create_geo_draft(CreateGeoDraftPayload(change_note="v1", owner_org="CSA"), MAKER)
    await g.upsert_draft_levels(
        [
            DraftLevelInput(level_id="l0", level_mnemonic="country"),
            DraftLevelInput(level_id="l1", level_mnemonic="region", parent_level_id="l0"),
            DraftLevelInput(
                level_id="l2", level_mnemonic="district", parent_level_id="l1", display_i18n={"am": "ወረዳ"}
            ),
        ],
        MAKER,
    )
    await g.upsert_draft_units(
        [
            unit("XX", "l0", "Country"),
            unit("R1", "l1", "North", "XX"),
            unit("R2", "l1", "South", "XX"),
            unit("D1", "l2", "Alpha", "R1"),
            unit("D2", "l2", "Beta", "R1"),
            unit("D3", "l2", "Gamma", "R2"),
        ],
        MAKER,
    )
    return await approve()


def legacy_units(db):
    with db.cursor() as cur:
        cur.execute("SELECT level_value_id, level_value_mnemonic FROM g2p_geo_level_values ORDER BY 1")
        return dict(cur.fetchall())


async def test_split_merge_recode_lineage_and_crosswalk(db):
    g = geo()
    v1 = await make_v1()
    assert v1.version_no == 1 and v1.is_latest and v1.unit_count == 6
    assert legacy_units(db)["D1"] == "Alpha"

    # v2: D1 splits into D1A + D1B; D2 is renamed (lineage completed automatically).
    await g.create_geo_draft(CreateGeoDraftPayload(change_note="split"), MAKER)
    await g.upsert_draft_units(
        [unit("D1A", "l2", "Alpha East", "R1"), unit("D1B", "l2", "Alpha West", "R1")], MAKER
    )
    with pytest.raises(CatalogueError, match="must be retired"):
        await g.record_geo_change(
            RecordGeoChangePayload(change_type="SPLIT", from_units=["D1"], to_units=["D1A", "D1B"]), MAKER
        )
    await g.retire_draft_units(["D1"], False, MAKER)
    _, split = await g.record_geo_change(
        RecordGeoChangePayload(
            change_type="SPLIT", from_units=["D1"], to_units=["D1A", "D1B"], note="2026 split"
        ),
        MAKER,
    )
    with pytest.raises(CatalogueError, match="already end"):
        await g.record_geo_change(RecordGeoChangePayload(change_type="RETIRE", from_units=["D1"]), MAKER)
    with pytest.raises(CatalogueError, match="already exists"):
        await g.record_geo_change(RecordGeoChangePayload(change_type="CREATE", to_units=["D2"]), MAKER)
    await g.upsert_draft_units([unit("D2", "l2", "Beta Renamed", "R1")], MAKER)
    v2 = await approve()
    assert v2.version_no == 2
    changes = await g.get_geo_changes(1, 2, None, False)
    kinds = sorted((c.change_type, c.is_auto) for c in changes)
    assert kinds == [("RENAME", True), ("SPLIT", False)]
    assert all(c.effective_date is not None for c in changes)

    # Validity dates stamped at publish; legacy tables follow the current version.
    _, d1, _ = await g.get_geo_unit("D1", VersionSelector(version=2))
    assert d1.status == "RETIRED" and d1.valid_to is not None
    _, d1a, ancestors = await g.get_geo_unit("D1A", None)
    assert d1a.valid_from is not None and [a.unit_id for a in ancestors] == ["R1", "XX"]
    units = legacy_units(db)
    assert "D1" not in units and units["D2"] == "Beta Renamed" and "D1A" in units

    # v3: D1A + D3 merge into D4; D2 is recoded to D2X.
    await g.create_geo_draft(CreateGeoDraftPayload(), MAKER)
    await g.upsert_draft_units([unit("D4", "l2", "Delta", "R1"), unit("D2X", "l2", "Beta New", "R1")], MAKER)
    await g.retire_draft_units(["D1A", "D3", "D2"], False, MAKER)
    await g.upsert_draft_units([unit("R9", "l1", "West", "XX")], MAKER)
    with pytest.raises(CatalogueError, match="same level"):
        await g.record_geo_change(
            RecordGeoChangePayload(change_type="RECODE", from_units=["D2"], to_units=["R9"]), MAKER
        )
    await g.record_geo_change(
        RecordGeoChangePayload(change_type="MERGE", from_units=["D1A", "D3"], to_units=["D4"]), MAKER
    )
    await g.record_geo_change(
        RecordGeoChangePayload(change_type="RECODE", from_units=["D2"], to_units=["D2X"]), MAKER
    )
    v3 = await approve()
    assert v3.version_no == 3

    cw = await g.get_geo_crosswalk("D1", 1, None)
    assert cw["direction"] == "forward" and cw["to_version"] == 3
    assert sorted(u.unit_id for u in cw["units"]) == ["D1B", "D4"]
    assert [p.change_type for p in cw["path"]] == ["SPLIT", "MERGE"]
    cw = await g.get_geo_crosswalk("D2", 1, 3)
    assert [u.unit_id for u in cw["units"]] == ["D2X"]
    assert [p.change_type for p in cw["path"]] == ["RENAME", "RECODE"]
    cw = await g.get_geo_crosswalk("D3", 1, 3)
    assert [u.unit_id for u in cw["units"]] == ["D4"]
    cw = await g.get_geo_crosswalk("D4", 3, 1)
    assert cw["direction"] == "backward" and sorted(u.unit_id for u in cw["units"]) == ["D1", "D3"]
    cw = await g.get_geo_crosswalk("R1", 1, 3)
    assert cw["unchanged"] and [u.unit_id for u in cw["units"]] == ["R1"]


async def test_retire_without_successor_and_auto_create(db):
    g = geo()
    await make_v1()
    await g.create_geo_draft(CreateGeoDraftPayload(), MAKER)
    await g.retire_draft_units(["D3"], False, MAKER)
    await g.upsert_draft_units([unit("D9", "l2", "Nu", "R2")], MAKER)
    with pytest.raises(CatalogueError, match="descendant"):
        await g.retire_draft_units(["R2"], False, MAKER)
    await approve()
    changes = await g.get_geo_changes(None, None, None, False)
    assert sorted((c.change_type, tuple(c.from_units), tuple(c.to_units)) for c in changes) == [
        ("CREATE", (), ("D9",)),
        ("RETIRE", ("D3",), ()),
    ]
    cw = await g.get_geo_crosswalk("D3", 1, 2)
    assert cw["units"] == [] and cw["unmapped"] == ["D3"]
    cw = await g.get_geo_crosswalk("D9", 2, 1)
    assert cw["unmapped"] == ["D9"]


async def test_unit_validation_and_reads():
    g = geo()
    await make_v1()
    await g.create_geo_draft(CreateGeoDraftPayload(), MAKER)
    with pytest.raises(CatalogueError, match="same name"):
        await g.upsert_draft_units([unit("D5", "l2", "Alpha", "R1")], MAKER)
    with pytest.raises(CatalogueError, match="expected l1"):
        await g.upsert_draft_units([unit("D6", "l2", "Zeta", "XX")], MAKER)
    with pytest.raises(CatalogueError, match="no changes"):
        await g.submit_geo_draft(SubmitGeoDraftPayload(), MAKER)
    with pytest.raises(CatalogueError) as e:
        await g.approve_geo_draft(DecideGeoDraftPayload(), CHECKER)
    assert e.value.code == "G2P-CAT-409"
    version, levels = await g.get_geo_levels(None)
    assert [lv.level_mnemonic for lv in levels] == ["country", "region", "district"]
    assert levels[2].display_i18n == {"am": "ወረዳ"}
    _, units, total = await g.get_geo_units(None, level="district", parent_unit_id="R1")
    assert total == 2 and {u.unit_id for u in units} == {"D1", "D2"}
    _, draft_units, _ = await g.get_geo_units(VersionSelector(version="draft"), level="l2")
    assert len(draft_units) == 3


async def test_geo_maker_checker_and_immutability(db):
    g = geo()
    await make_v1()
    await g.create_geo_draft(CreateGeoDraftPayload(), MAKER)
    await g.upsert_draft_units([unit("D7", "l2", "Eta", "R2")], MAKER)
    await g.submit_geo_draft(SubmitGeoDraftPayload(), MAKER)
    with pytest.raises(CatalogueError) as e:
        await g.approve_geo_draft(DecideGeoDraftPayload(), MAKER)
    assert e.value.code == "G2P-CAT-403"
    for sql in (
        "UPDATE g2p_geo_version_units SET name = 'x' WHERE version_no = 1",
        "DELETE FROM g2p_geo_version_units WHERE version_no = 1",
        "UPDATE g2p_geo_versions SET change_note = 'x' WHERE version_no = 1",
        "INSERT INTO g2p_geo_changes (version_no, change_type, from_units, to_units, is_auto) "
        "VALUES (1, 'CREATE', '{}', '{X}', false)",
    ):
        with db.cursor() as cur:
            with pytest.raises(psycopg2.Error, match="G2P-CAT-IMMUTABLE"):
                cur.execute(sql)


@pytest.fixture()
def s3(settings):
    """A local S3 (moto) as the boundary store."""
    from moto.server import ThreadedMotoServer
    from openg2p_gen2_master_data.helpers.catalogue_integrations import BoundaryStore

    server = ThreadedMotoServer(port=0, verbose=False)
    server.start()
    host, port = server.get_host_and_port()
    # moto keeps one in-process backend for every server: start from an empty one.
    import urllib.request

    urllib.request.urlopen(
        urllib.request.Request(f"http://{host}:{port}/moto-api/reset", method="POST")
    ).close()
    settings.boundary_s3_endpoint = f"http://{host}:{port}"
    settings.boundary_s3_access_key = "test"
    settings.boundary_s3_secret_key = "test"
    settings.boundary_public_base_url = "https://maps.example.org"
    BoundaryStore.get_component()._s3 = None
    yield settings.boundary_s3_endpoint
    BoundaryStore.get_component()._s3 = None
    server.stop()


def fc(features):
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"pcode": pid},
                "geometry": {"type": "Point", "coordinates": xy},
            }
            for pid, xy in features
        ],
    }


async def test_boundaries_versioned_keys_and_auto_boundary_change(s3):
    g = geo()
    await g.create_geo_draft(CreateGeoDraftPayload(), MAKER)
    await g.upsert_draft_levels(
        [
            DraftLevelInput(level_id="l0", level_mnemonic="country"),
            DraftLevelInput(level_id="l1", level_mnemonic="region", parent_level_id="l0"),
        ],
        MAKER,
    )
    await g.upsert_draft_units(
        [unit("XX", "l0", "Country"), unit("R1", "l1", "North", "XX"), unit("R2", "l1", "South", "XX")], MAKER
    )
    up = await g.upload_draft_boundary("region", fc([("R1", [1, 1]), ("R2", [2, 2])]), MAKER)
    assert up["object_key"] == "geo/TST/v1/region.geojson" and up["features"] == 2
    await g.upload_draft_boundary("country", fc([("XX", [0, 0])]), MAKER)
    await approve()

    info = await g.get_geo_boundary(None, "region")
    assert info["object_key"] == "geo/TST/v1/region.geojson"
    assert info["url"] == "https://maps.example.org/openg2p-geo/geo/TST/v1/region.geojson"
    assert info["presigned_url"]
    body = json.loads(await g.read_boundary(None, "region"))
    assert len(body["features"]) == 2

    # v2: R2's geometry moves; country does not change and keeps its v1 object.
    await g.create_geo_draft(CreateGeoDraftPayload(), MAKER)
    up = await g.upload_draft_boundary("region", fc([("R1", [1, 1]), ("R2", [3, 3])]), MAKER)
    assert up["object_key"] == "geo/TST/v2/region.geojson"
    v2 = await approve()
    assert v2.boundary_objects == {
        "region": "geo/TST/v2/region.geojson",
        "country": "geo/TST/v1/country.geojson",
    }
    changes = await g.get_geo_changes(1, 2, None, False)
    assert [(c.change_type, c.from_units, c.is_auto) for c in changes] == [("BOUNDARY_CHANGE", ["R2"], True)]
    # The v1 object is untouched.
    old = json.loads(await g.read_boundary(VersionSelector(version=1), "region"))
    assert old["features"][1]["geometry"]["coordinates"] == [2, 2]
    # The next draft writes under its own version, never over a published object.
    await g.create_geo_draft(CreateGeoDraftPayload(), MAKER)
    up = await g.upload_draft_boundary("country", fc([("XX", [5, 5])]), MAKER)
    assert up["object_key"] == "geo/TST/v3/country.geojson"
    old = json.loads(await g.read_boundary(VersionSelector(version=2), "country"))
    assert old["features"][0]["geometry"]["coordinates"] == [0, 0]


async def test_geo_discard_keeps_number_and_boundary_keys(s3):
    g = geo()
    await g.create_geo_draft(CreateGeoDraftPayload(), MAKER)
    await g.upsert_draft_levels([DraftLevelInput(level_id="l0", level_mnemonic="country")], MAKER)
    await g.upsert_draft_units([unit("XX", "l0", "Country")], MAKER)
    await g.upload_draft_boundary("country", fc([("XX", [0, 0])]), MAKER)
    await approve()
    # Draft 2 uploads a boundary and is discarded.
    await g.create_geo_draft(CreateGeoDraftPayload(), MAKER)
    up = await g.upload_draft_boundary("country", fc([("XX", [9, 9])]), MAKER)
    assert up["object_key"] == "geo/TST/v2/country.geojson"
    assert await g.discard_geo_draft(MAKER) == 2
    # The next draft is 3 and writes v3 keys: draft 2's object is never overwritten.
    info = await g.create_geo_draft(CreateGeoDraftPayload(), MAKER)
    assert info.version_no == 3
    up = await g.upload_draft_boundary("country", fc([("XX", [5, 5])]), MAKER)
    assert up["object_key"] == "geo/TST/v3/country.geojson"
    v3 = await approve()
    assert v3.version_no == 3 and v3.boundary_objects == {"country": "geo/TST/v3/country.geojson"}
    versions = {v.version_no: v.status for v in await g.get_geo_versions()}
    assert versions == {1: "PUBLISHED", 2: "DISCARDED", 3: "PUBLISHED"}
    discarded = json.loads(await g.read_boundary(VersionSelector(version=2), "country"))
    assert discarded["features"][0]["geometry"]["coordinates"] == [9, 9]
    # Lineage skips the discarded version: v3's boundary change is measured against v1.
    changes = await g.get_geo_changes(1, 3, None, False)
    assert [(c.version_no, c.change_type, c.from_units) for c in changes] == [(3, "BOUNDARY_CHANGE", ["XX"])]
