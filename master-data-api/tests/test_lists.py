"""Code-list versioning: lifecycle, immutability, effective dates, diff, retire, typed attributes."""

import asyncio
from datetime import datetime, timedelta, timezone

import psycopg2
import pytest
from catalogue_helpers import CHECKER, MAKER, publish_list, submit_and_approve, svc, values
from openg2p_gen2_master_data.schemas.g2p_catalogue import (
    CreateListDraftPayload,
    CreateListPayload,
    DecideDraftPayload,
    DraftValueInput,
    SubmitDraftPayload,
    UpdateListPayload,
    VersionSelector,
)
from openg2p_gen2_master_data.services.catalogue_common import CatalogueError

pytestmark = pytest.mark.asyncio(loop_scope="session")


def legacy_codes(db, list_id):
    with db.cursor() as cur:
        cur.execute(
            "SELECT value_code FROM g2p_attribute_values WHERE attribute_id = %s ORDER BY sort_order",
            (list_id,),
        )
        return [r[0] for r in cur.fetchall()]


async def test_version_lifecycle_and_legacy_materialisation(db):
    s = svc()
    summary, draft = await s.create_list(
        CreateListPayload(list_code="CROP", display="Crop", owner_org="MoA"), MAKER
    )
    assert draft.version_no == 1 and draft.status == "DRAFT"
    assert summary.current_version_no is None and summary.open_draft_version_no == 1
    await s.upsert_draft_values("CROP", values("TEFF", "MAIZE"), MAKER)
    # Nothing is visible to legacy readers before approval.
    assert legacy_codes(db, "CROP") == []
    _, sub = await s.submit_draft(SubmitDraftPayload(list_code="CROP", change_note="first"), MAKER)
    assert sub.status == "SUBMITTED" and sub.submitted_by == "maker"
    with pytest.raises(CatalogueError) as e:
        await s.upsert_draft_values("CROP", values("WHEAT"), MAKER)
    assert e.value.code == "G2P-CAT-409"
    _, v1 = await s.approve_draft(DecideDraftPayload(list_code="CROP"), CHECKER)
    assert v1.status == "PUBLISHED" and v1.is_latest and v1.decided_by == "checker"
    assert legacy_codes(db, "CROP") == ["TEFF", "MAIZE"]

    # Version 2 starts as a copy of version 1.
    _, d2 = await s.create_list_draft(CreateListDraftPayload(list_code="CROP"), MAKER)
    assert d2.version_no == 2 and d2.base_version_no == 1
    await s.upsert_draft_values("CROP", values("WHEAT"), MAKER)
    assert legacy_codes(db, "CROP") == ["TEFF", "MAIZE"]  # still version 1
    v2 = await submit_and_approve("CROP")
    assert v2.version_no == 2 and v2.is_latest
    assert sorted(legacy_codes(db, "CROP")) == ["MAIZE", "TEFF", "WHEAT"]

    code, versions = await s.get_list_versions("CROP")
    assert [v.version_no for v in versions] == [2, 1]
    assert [v.is_latest for v in versions] == [True, False]
    # Version 1 is still readable as it was.
    _, ver, vals, total = await s.get_list_values("CROP", VersionSelector(version=1))
    assert ver.version_no == 1 and not ver.is_latest and total == 2
    with db.cursor() as cur:
        cur.execute("SELECT current_version_no FROM g2p_attributes WHERE attribute_id = 'CROP'")
        assert cur.fetchone()[0] == 2


async def test_submit_requires_changes_and_maker_checker():
    s = svc()
    await publish_list("GENDER", ("F", "M"))
    await s.create_list_draft(CreateListDraftPayload(list_code="GENDER"), MAKER)
    with pytest.raises(CatalogueError, match="no changes"):
        await s.submit_draft(SubmitDraftPayload(list_code="GENDER"), MAKER)
    await s.upsert_draft_values("GENDER", values("X"), MAKER)
    await s.submit_draft(SubmitDraftPayload(list_code="GENDER"), MAKER)
    with pytest.raises(CatalogueError) as e:
        await s.approve_draft(DecideDraftPayload(list_code="GENDER"), MAKER)
    assert e.value.code == "G2P-CAT-403"
    with pytest.raises(CatalogueError):
        await s.reject_draft(DecideDraftPayload(list_code="GENDER", decision_note="no"), MAKER)
    _, rejected = await s.reject_draft(
        DecideDraftPayload(list_code="GENDER", decision_note="not now"), CHECKER
    )
    assert rejected.status == "REJECTED"
    # Rework the rejected content in a new draft.
    _, d = await s.create_list_draft(CreateListDraftPayload(list_code="GENDER", copy_from_version=2), MAKER)
    assert d.version_no == 3 and d.base_version_no == 1
    _, _, vals, _ = await s.get_list_values("GENDER", VersionSelector(version="draft"))
    assert {v.value_code for v in vals} == {"F", "M", "X"}


async def test_published_versions_are_immutable_in_the_database(db):
    await publish_list("IMM", ("A", "B"))
    statements = [
        "UPDATE g2p_list_version_values SET display = 'x' WHERE list_id = 'IMM' AND version_no = 1",
        "DELETE FROM g2p_list_version_values WHERE list_id = 'IMM' AND version_no = 1",
        "INSERT INTO g2p_list_version_values (list_id, version_no, value_id, value_code, status) "
        "VALUES ('IMM', 1, 'Z', 'Z', 'ACTIVE')",
        "UPDATE g2p_list_versions SET change_note = 'x' WHERE list_id = 'IMM' AND version_no = 1",
        "DELETE FROM g2p_list_versions WHERE list_id = 'IMM' AND version_no = 1",
        # Deleting the list would cascade into its published versions.
        "DELETE FROM g2p_attributes WHERE attribute_id = 'IMM'",
        "UPDATE g2p_catalogue_change_log SET actor = 'x'",
        "DELETE FROM g2p_catalogue_change_log",
    ]
    for sql in statements:
        with db.cursor() as cur:
            with pytest.raises(psycopg2.Error, match="G2P-CAT-IMMUTABLE"):
                cur.execute(sql)
    # A draft is editable.
    await svc().create_list_draft(CreateListDraftPayload(list_code="IMM"), MAKER)
    with db.cursor() as cur:
        cur.execute(
            "UPDATE g2p_list_version_values SET display = 'x' WHERE list_id = 'IMM' AND version_no = 2"
        )
        assert cur.rowcount == 2


async def test_latest_as_of_and_future_effective_from(db):
    s = svc()
    t0 = datetime.now(timezone.utc)
    await publish_list("SEASON", ("MEHER",))
    await s.create_list_draft(CreateListDraftPayload(list_code="SEASON"), MAKER)
    await s.upsert_draft_values("SEASON", values("BELG"), MAKER)
    future = datetime.now(timezone.utc) + timedelta(days=90)
    v2 = await submit_and_approve("SEASON", effective_from=future)
    assert v2.status == "PUBLISHED" and not v2.is_latest
    # "latest" is still version 1; the future version is visible by number.
    _, latest, _, _ = await s.get_list_values("SEASON", None)
    assert latest.version_no == 1 and latest.is_latest
    _, by_no, vals, _ = await s.get_list_values("SEASON", VersionSelector(version=2))
    assert by_no.version_no == 2 and {v.value_code for v in vals} == {"MEHER", "BELG"}
    _, at, _, _ = await s.get_list_values("SEASON", VersionSelector(as_of=future + timedelta(days=1)))
    assert at.version_no == 2
    _, at, _, _ = await s.get_list_values("SEASON", VersionSelector(as_of=t0 + timedelta(seconds=30)))
    assert at.version_no == 1
    with pytest.raises(CatalogueError):
        await s.get_list_values("SEASON", VersionSelector(as_of=t0 - timedelta(days=1)))
    assert legacy_codes(db, "SEASON") == ["MEHER"]
    summary, _ = await s.get_list("SEASON", None)
    assert summary.current_version_no == 1 and summary.latest_published_version_no == 2
    # An effective date earlier than the previous version's is refused.
    await s.create_list_draft(CreateListDraftPayload(list_code="SEASON"), MAKER)
    with pytest.raises(CatalogueError, match="earlier"):
        await s.submit_draft(SubmitDraftPayload(list_code="SEASON", effective_from=t0), MAKER)


async def test_future_version_comes_into_effect(db):
    s = svc()
    await publish_list("SOON", ("A",))
    await s.create_list_draft(CreateListDraftPayload(list_code="SOON"), MAKER)
    await s.upsert_draft_values("SOON", values("B"), MAKER)
    await submit_and_approve("SOON", effective_from=datetime.now(timezone.utc) + timedelta(seconds=2))
    assert legacy_codes(db, "SOON") == ["A"]
    await asyncio.sleep(2.5)
    with db.cursor() as cur:
        cur.execute("SELECT g2p_catalogue_refresh_current()")
        assert cur.fetchone()[0] == 1
        cur.execute(
            "SELECT version_no FROM g2p_catalogue_change_log WHERE event_type = 'list.version.effective' "
            "AND subject_id = 'SOON'"
        )
        assert cur.fetchone()[0] == 2
    assert sorted(legacy_codes(db, "SOON")) == ["A", "B"]
    _, latest, _, _ = await s.get_list_values("SOON", None)
    assert latest.version_no == 2


async def test_diff_and_retire_semantics(db):
    s = svc()
    await publish_list("WATER", ("PIPED", "WELL", "RIVER"))
    await s.create_list_draft(CreateListDraftPayload(list_code="WATER"), MAKER)
    await s.upsert_draft_values(
        "WATER",
        [
            DraftValueInput(value_code="WELL", display="Protected well"),
            DraftValueInput(value_code="RAIN", display="Rain"),
        ],
        MAKER,
    )
    await s.upsert_draft_values("WATER", values("TEMP"), MAKER)
    _, _, retired, removed = await s.retire_draft_values("WATER", ["RIVER", "TEMP"], False, MAKER)
    assert retired == ["RIVER"] and removed == ["TEMP"]
    diff = await s.get_list_diff("WATER", None, "draft")
    assert diff["from_version"] == 1 and diff["to_version"] == 2
    assert [v.value_code for v in diff["added"]] == ["RAIN"]
    assert [c.value_code for c in diff["changed"]] == ["WELL"]
    assert diff["changed"][0].changes["display"] == {"before": "Well", "after": "Protected well"}
    assert [v.value_code for v in diff["retired"]] == ["RIVER"]
    await submit_and_approve("WATER")
    # Retired, not deleted: still resolves in v2 as RETIRED; gone from current legacy rows.
    _, ver, value = await s.get_list_value("WATER", "RIVER", None)
    assert ver.version_no == 2 and value.status == "RETIRED"
    _, _, active, _ = await s.get_list_values("WATER", None)
    assert "RIVER" not in {v.value_code for v in active}
    _, _, everything, _ = await s.get_list_values("WATER", None, include_retired=True)
    assert "RIVER" in {v.value_code for v in everything}
    assert "RIVER" not in legacy_codes(db, "WATER")
    # Re-adding a retired code re-activates it.
    await s.create_list_draft(CreateListDraftPayload(list_code="WATER"), MAKER)
    await s.upsert_draft_values("WATER", [DraftValueInput(value_code="RIVER")], MAKER)
    diff = await s.get_list_diff("WATER", None, "draft")
    assert [v.value_code for v in diff["reactivated"]] == ["RIVER"]


async def test_hierarchy_and_children_block_retire():
    s = svc()
    await s.create_list(CreateListPayload(list_code="LOC", display="Loc", is_hierarchical=True), MAKER)
    await s.upsert_draft_values(
        "LOC",
        [
            DraftValueInput(value_code="P", display="Parent"),
            DraftValueInput(value_code="C", display="Child", parent_code="P"),
        ],
        MAKER,
    )
    await submit_and_approve("LOC")
    await s.create_list_draft(CreateListDraftPayload(list_code="LOC"), MAKER)
    with pytest.raises(CatalogueError, match="child"):
        await s.retire_draft_values("LOC", ["P"], False, MAKER)
    _, _, retired, _ = await s.retire_draft_values("LOC", ["P"], True, MAKER)
    assert sorted(retired) == ["C", "P"]
    await s.upsert_draft_values(
        "LOC", [DraftValueInput(value_code="Q", display="Q", parent_code="ZZ")], MAKER
    )
    with pytest.raises(CatalogueError, match="not an active value"):
        await s.submit_draft(SubmitDraftPayload(list_code="LOC"), MAKER)


async def test_typed_attributes_and_list_refs():
    s = svc()
    await publish_list("CROP_COMMODITY", ("CROP_TEFF", "CROP_MAIZE"))
    schema = {
        "type": "object",
        "properties": {
            "crop": {"type": "string", "x-list-ref": "CROP_COMMODITY"},
            "days_to_maturity": {"type": "integer", "minimum": 1},
        },
        "required": ["crop"],
        "additionalProperties": False,
    }
    with pytest.raises(CatalogueError, match="not a valid JSON Schema"):
        await s.create_list(
            CreateListPayload(list_code="BAD", display="Bad", attribute_schema={"type": 5}), MAKER
        )
    await s.create_list(
        CreateListPayload(list_code="SEED_VARIETY", display="Variety", attribute_schema=schema), MAKER
    )
    ok = DraftValueInput(
        value_code="VAR_QUNCHO", display="Quncho", attributes={"crop": "CROP_TEFF", "days_to_maturity": 90}
    )
    await s.upsert_draft_values("SEED_VARIETY", [ok], MAKER)
    with pytest.raises(CatalogueError, match="required|crop"):
        await s.upsert_draft_values(
            "SEED_VARIETY", [DraftValueInput(value_code="V2", display="V2", attributes={})], MAKER
        )
    with pytest.raises(CatalogueError, match="minimum|less than"):
        await s.upsert_draft_values(
            "SEED_VARIETY",
            [
                DraftValueInput(
                    value_code="V3", display="V3", attributes={"crop": "CROP_TEFF", "days_to_maturity": 0}
                )
            ],
            MAKER,
        )
    with pytest.raises(CatalogueError, match="not values of list CROP_COMMODITY"):
        await s.upsert_draft_values(
            "SEED_VARIETY",
            [DraftValueInput(value_code="V4", display="V4", attributes={"crop": "CROP_COFFEE"})],
            MAKER,
        )
    # A code that exists only in the referenced list's open draft is refused, with a hint...
    await s.create_list_draft(CreateListDraftPayload(list_code="CROP_COMMODITY"), MAKER)
    await s.upsert_draft_values("CROP_COMMODITY", values("CROP_COFFEE"), MAKER)
    with pytest.raises(
        CatalogueError, match="only in the unpublished draft .version 2. of CROP_COMMODITY"
    ) as e:
        await s.upsert_draft_values(
            "SEED_VARIETY",
            [DraftValueInput(value_code="V4", display="V4", attributes={"crop": "CROP_COFFEE"})],
            MAKER,
        )
    assert e.value.code == "G2P-CAT-400" and "CROP_COFFEE" in e.value.message
    # ...and accepted once the referenced list is published first.
    await submit_and_approve("CROP_COMMODITY")
    await s.upsert_draft_values(
        "SEED_VARIETY",
        [DraftValueInput(value_code="V4", display="V4", attributes={"crop": "CROP_COFFEE"})],
        MAKER,
    )
    v = await submit_and_approve("SEED_VARIETY")
    assert v.version_no == 1
    summary, _ = await s.get_list("SEED_VARIETY", None)
    assert summary.attribute_schema_summary["list_refs"] == {"crop": "CROP_COMMODITY"}
    # Attribute filters on reads.
    _, _, vals, total = await s.get_list_values("SEED_VARIETY", None, attribute_filters={"crop": "CROP_TEFF"})
    assert total == 1 and vals[0].value_code == "VAR_QUNCHO"
    # A schema change goes through the draft and is checked on submit against existing values.
    await s.update_list(
        UpdateListPayload(
            list_code="SEED_VARIETY",
            attribute_schema={**schema, "required": ["crop", "days_to_maturity"]},
            owner_org="EIAR",
        ),
        MAKER,
    )
    summary, _ = await s.get_list("SEED_VARIETY", None)
    assert summary.owner_org == "EIAR"  # applied directly
    assert summary.attribute_schema["required"] == ["crop"]  # published version unchanged
    with pytest.raises(CatalogueError, match="days_to_maturity"):
        await s.submit_draft(SubmitDraftPayload(list_code="SEED_VARIETY"), MAKER)


async def test_discard_draft_and_new_list_numbering():
    s = svc()
    await publish_list("DISC", ("A",))
    await s.create_list_draft(CreateListDraftPayload(list_code="DISC"), MAKER)
    with pytest.raises(CatalogueError, match="already has an open draft"):
        await s.create_list_draft(CreateListDraftPayload(list_code="DISC"), MAKER)
    code, no = await s.discard_draft("DISC", MAKER)
    assert no == 2
    # Numbers are never reused: the discarded draft stays as a DISCARDED row.
    _, d = await s.create_list_draft(CreateListDraftPayload(list_code="DISC"), MAKER)
    assert d.version_no == 3
    _, versions = await s.get_list_versions("DISC")
    assert [(v.version_no, v.status) for v in versions] == [(3, "DRAFT"), (2, "DISCARDED"), (1, "PUBLISHED")]


async def test_list_refs_resolve_against_version_in_effect():
    """x-list-ref: the referenced list's version IN EFFECT (not its highest published one,
    never its draft) — or, for a future-effective draft, the version in effect at that date."""
    s = svc()
    await publish_list("CROP", ("TEFF", "MAIZE"))
    # CROP v2 (published, effective in 90 days) retires MAIZE and adds COFFEE.
    future = datetime.now(timezone.utc) + timedelta(days=90)
    await s.create_list_draft(CreateListDraftPayload(list_code="CROP"), MAKER)
    await s.upsert_draft_values("CROP", values("COFFEE"), MAKER)
    await s.retire_draft_values("CROP", ["MAIZE"], False, MAKER)
    v2 = await submit_and_approve("CROP", effective_from=future)
    assert v2.version_no == 2 and not v2.is_latest

    schema = {"type": "object", "properties": {"crop": {"type": "string", "x-list-ref": "CROP"}}}
    await s.create_list(
        CreateListPayload(list_code="VARIETY", display="Variety", attribute_schema=schema), MAKER
    )
    # Now: v1 is in effect. MAIZE is fine; COFFEE (only in the future v2) is not.
    await s.upsert_draft_values(
        "VARIETY", [DraftValueInput(value_code="BH661", display="BH661", attributes={"crop": "MAIZE"})], MAKER
    )
    with pytest.raises(
        CatalogueError, match=r"\['COFFEE'\] are not values of list CROP \(version 1, in effect now\)"
    ) as e:
        await s.upsert_draft_values(
            "VARIETY",
            [DraftValueInput(value_code="ARABICA", display="Arabica", attributes={"crop": "COFFEE"})],
            MAKER,
        )
    assert e.value.code == "G2P-CAT-400"
    await submit_and_approve("VARIETY")

    # A VARIETY draft that takes effect with (or after) CROP v2 resolves against v2.
    await s.create_list_draft(
        CreateListDraftPayload(list_code="VARIETY", effective_from=future + timedelta(days=1)), MAKER
    )
    await s.upsert_draft_values(
        "VARIETY",
        [DraftValueInput(value_code="ARABICA", display="Arabica", attributes={"crop": "COFFEE"})],
        MAKER,
    )
    # ...where MAIZE is retired, so the carried-over BH661 now fails on submit.
    with pytest.raises(
        CatalogueError, match=r"\['MAIZE'\] are not values of list CROP \(version 2, in effect at "
    ):
        await s.submit_draft(SubmitDraftPayload(list_code="VARIETY"), MAKER)
    await s.retire_draft_values("VARIETY", ["BH661"], False, MAKER)
    v = await submit_and_approve("VARIETY")
    assert v.version_no == 2 and v.status == "PUBLISHED" and not v.is_latest


async def test_list_refs_to_unpublished_list():
    s = svc()
    await s.create_list(CreateListPayload(list_code="NEWCROP", display="New crop"), MAKER)
    await s.upsert_draft_values("NEWCROP", values("SORGHUM"), MAKER)
    schema = {"type": "object", "properties": {"crop": {"type": "string", "x-list-ref": "NEWCROP"}}}
    await s.create_list(
        CreateListPayload(list_code="VAR2", display="Variety", attribute_schema=schema), MAKER
    )
    with pytest.raises(
        CatalogueError, match="referenced list NEWCROP has no published version in effect now"
    ):
        await s.upsert_draft_values(
            "VAR2", [DraftValueInput(value_code="V", display="V", attributes={"crop": "SORGHUM"})], MAKER
        )


async def test_version_numbers_are_never_reused(db):
    s = svc()
    await publish_list("NUM", ("A",))
    # A rejected and a discarded draft both keep their numbers.
    await s.create_list_draft(CreateListDraftPayload(list_code="NUM"), MAKER)
    await s.upsert_draft_values("NUM", values("B"), MAKER)
    await s.submit_draft(SubmitDraftPayload(list_code="NUM"), MAKER)
    await s.reject_draft(DecideDraftPayload(list_code="NUM", decision_note="no"), CHECKER)
    await s.create_list_draft(CreateListDraftPayload(list_code="NUM"), MAKER)
    await s.discard_draft("NUM", MAKER)
    _, d = await s.create_list_draft(CreateListDraftPayload(list_code="NUM"), MAKER)
    assert d.version_no == 4
    # Even a number only the change log remembers (a row deleted before tombstones existed).
    with db.cursor() as cur:
        cur.execute("DELETE FROM g2p_list_versions WHERE list_id = 'NUM' AND version_no = 4")
    _, d = await s.create_list_draft(CreateListDraftPayload(list_code="NUM"), MAKER)
    assert d.version_no == 5
    with db.cursor() as cur:
        cur.execute(
            "SELECT version_no, count(*) FROM g2p_catalogue_change_log "
            "WHERE subject_id = 'NUM' AND event_type = 'list.draft.created' GROUP BY 1 ORDER BY 1"
        )
        assert cur.fetchall() == [(1, 1), (2, 1), (3, 1), (4, 1), (5, 1)]
        cur.execute("SELECT g2p_catalogue_next_list_version('NUM')")
        assert cur.fetchone()[0] == 6


async def test_list_domain_create_update_and_fallback(db):
    """get_lists / get_list return the domain: stored (lower-case), set on create or update,
    or — for a pack list loaded before the column existed — derived from its first
    version's change note ("core" without a domain suffix); unknown stays None."""
    s = svc()
    await s.create_list(CreateListPayload(list_code="CROP_X", display="Crop", domain=" Agriculture "), MAKER)
    await publish_list("PLAIN")
    await publish_list("PACK_CORE")
    await publish_list("PACK_AGRI")
    with db.cursor() as cur:
        # As the loader wrote them before the domain column: only the change note tells.
        cur.execute("ALTER TABLE g2p_list_versions DISABLE TRIGGER trg_g2p_list_versions_guard")
        cur.execute(
            "UPDATE g2p_list_versions SET change_note = 'Initial load from country pack ETH (1.0)' "
            "WHERE list_id = 'PACK_CORE'"
        )
        cur.execute(
            "UPDATE g2p_list_versions SET change_note = 'Initial load from country pack ETH (1.0) (agriculture)' "
            "WHERE list_id = 'PACK_AGRI'"
        )
        cur.execute("ALTER TABLE g2p_list_versions ENABLE TRIGGER trg_g2p_list_versions_guard")
    lists = {x.list_id: x.domain for x in await s.get_lists()}
    assert lists == {"CROP_X": "agriculture", "PLAIN": None, "PACK_CORE": "core", "PACK_AGRI": "agriculture"}
    summary, _ = await s.update_list(UpdateListPayload(list_code="PLAIN", domain="Livestock"), MAKER)
    assert summary.domain == "livestock"
    summary, _ = await s.get_list("PACK_AGRI", None)
    assert summary.domain == "agriculture"
    summary, _ = await s.update_list(UpdateListPayload(list_code="PLAIN", domain=""), MAKER)
    assert summary.domain is None
