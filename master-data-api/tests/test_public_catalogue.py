"""The anonymous, read-only public catalogue (/public/...).

Opt-in: off by default (404), private by default per dataset and geography,
PUBLISHED versions only. Plus: DCAT / SKOS JSON-LD, downloads, rate limit, and
that nothing outside /public lost its authentication.
"""

import csv
import io
import json
from datetime import datetime, timedelta, timezone

import pytest
from catalogue_helpers import CHECKER, MAKER, publish_list, submit_and_approve, svc, values
from conftest import APP
from openg2p_gen2_master_data.controllers.g2p_public_catalogue_controller import LIMITER
from openg2p_gen2_master_data.schemas.g2p_catalogue import (
    CreateListPayload,
    CreateReleasePayload,
    ReleaseMemberInput,
    SetReleaseMembersPayload,
    UpdateGeoSettingsPayload,
    UpdateListPayload,
)
from openg2p_gen2_master_data.services import G2PCatalogueGeoService, G2PCatalogueReleaseService
import test_geo
from test_geo import fc, make_v1

pytestmark = pytest.mark.asyncio(loop_scope="session")

BASE = "https://catalogue.example.gov"
# The local S3 (moto) boundary store fixture of the geography tests.
s3 = test_geo.s3


@pytest.fixture()
def public(settings):
    settings.public_catalogue_enabled = True
    settings.public_base_url = BASE
    settings.public_catalogue_rate_limit_per_minute = 0
    LIMITER.reset()
    yield settings
    LIMITER.reset()


async def make_public(code, visibility="public", **extra):
    await svc().update_list(UpdateListPayload(list_code=code, visibility=visibility, **extra), MAKER)


async def geo_public(visibility="public", **extra):
    await G2PCatalogueGeoService.get_component().update_geo_settings(
        UpdateGeoSettingsPayload(visibility=visibility, **extra), MAKER
    )


# ---------------------------------------------------------------------------
# Off by default, private by default
# ---------------------------------------------------------------------------


async def test_disabled_by_default_every_public_route_is_404(client, settings):
    assert settings.public_catalogue_enabled is False
    await publish_list("CROP")
    await make_public("CROP")
    for path in (
        "/public/catalog",
        "/public/datasets",
        "/public/datasets/CROP",
        "/public/datasets/CROP/entries",
        "/public/datasets/CROP/download.csv",
        "/public/datasets/CROP/skos",
        "/public/geography",
        "/public/releases",
    ):
        r = await client.get(path)
        assert r.status_code == 404, path


async def test_visibility_defaults_to_private_and_is_settable(client, public):
    await publish_list("CROP")
    lists = (await client.call("/catalogue/get_lists", {}))["response_body"]["response_payload"]["lists"]
    assert lists[0]["visibility"] == "private"
    assert (await client.get("/public/datasets")).json() == {"datasets": []}
    assert (await client.get("/public/datasets/CROP")).status_code == 404
    assert (await client.get("/public/datasets/CROP/entries")).status_code == 404

    out = await client.call(
        "/catalogue/update_list",
        {
            "list_code": "CROP",
            "visibility": "public",
            "licence_uri": "https://creativecommons.org/licenses/by/4.0/",
            "licence_label": "CC BY 4.0",
        },
    )
    summary = out["response_body"]["response_payload"]["list"]
    assert (summary["visibility"], summary["licence_label"]) == ("public", "CC BY 4.0")
    # Visibility is administrative: no draft was opened for it.
    assert out["response_body"]["response_payload"]["draft"] is None

    out = await client.call(
        "/catalogue/create_list", {"list_code": "PUB", "display": "Pub", "visibility": "public"}
    )
    assert out["response_body"]["response_payload"]["list"]["visibility"] == "public"
    # A public list that was never published is not shown.
    codes = [d["code"] for d in (await client.get("/public/datasets")).json()["datasets"]]
    assert codes == ["CROP"]
    assert (await client.get("/public/datasets/PUB")).status_code == 404

    await make_public("CROP", "private")
    assert (await client.get("/public/datasets/CROP")).status_code == 404


# ---------------------------------------------------------------------------
# Datasets, entries, versions
# ---------------------------------------------------------------------------


async def test_published_versions_only_never_drafts(client, public):
    await svc().create_list(
        CreateListPayload(
            list_code="CROP", display="Crop", description="Crops", owner_org="MoA", domain="agriculture"
        ),
        MAKER,
    )
    await svc().upsert_draft_values("CROP", values("MAIZE", "TEFF") + [], MAKER)
    await submit_and_approve("CROP")
    await make_public(
        "CROP", licence_label="CC BY 4.0", licence_uri="https://creativecommons.org/licenses/by/4.0/"
    )
    # v2 is an open draft with a new value; v3 does not exist.
    await svc().upsert_draft_values("CROP", values("SORGHUM"), MAKER)

    ds = (await client.get("/public/datasets/CROP")).json()
    assert ds["code"] == "CROP" and ds["version"] == 1 and ds["theme"] == "agriculture"
    assert ds["publisher"] == "MoA" and ds["licence"]["label"] == "CC BY 4.0"
    assert [v["version"] for v in ds["versions"]] == [1]
    assert ds["links"]["csv"] == f"{BASE}/public/datasets/CROP/download.csv?version=1"
    for key in ("created_by", "decided_by", "submitted_by"):
        assert key not in json.dumps(ds)

    entries = (await client.get("/public/datasets/CROP/entries")).json()
    assert [e["code"] for e in entries["entries"]] == ["MAIZE", "TEFF"]
    assert (await client.get("/public/datasets/CROP/entries?version=2")).status_code == 404
    assert (await client.get("/public/datasets/CROP/entries?version=draft")).status_code == 400
    assert (await client.get("/public/datasets/CROP/entries/SORGHUM")).status_code == 404

    # Submitted is still not public; rejected neither.
    from openg2p_gen2_master_data.schemas.g2p_catalogue import DecideDraftPayload, SubmitDraftPayload

    await svc().submit_draft(SubmitDraftPayload(list_code="CROP"), MAKER)
    assert (await client.get("/public/datasets/CROP/entries?version=2")).status_code == 404
    await svc().reject_draft(DecideDraftPayload(list_code="CROP", decision_note="no"), CHECKER)
    assert (await client.get("/public/datasets/CROP/entries?version=2")).status_code == 404

    # v3 published with a future effective date: latest is still v1; v3 by number and as_of.
    future = datetime.now(timezone.utc) + timedelta(days=30)
    await svc().upsert_draft_values("CROP", values("BARLEY"), MAKER)
    v3 = await submit_and_approve("CROP", effective_from=future)
    assert v3.version_no == 3
    assert (await client.get("/public/datasets/CROP")).json()["version"] == 1
    latest = (await client.get("/public/datasets/CROP/entries?version=latest")).json()
    assert latest["version"] == 1
    by_no = (await client.get("/public/datasets/CROP/entries?version=3")).json()
    assert {e["code"] for e in by_no["entries"]} == {"MAIZE", "TEFF", "BARLEY"}
    as_of = (future + timedelta(days=1)).isoformat()
    r = await client.get("/public/datasets/CROP/entries", params={"as_of": as_of})
    assert r.json()["version"] == 3
    past = (datetime.now(timezone.utc) - timedelta(days=3650)).isoformat()
    assert (await client.get("/public/datasets/CROP/entries", params={"as_of": past})).status_code == 404

    one = (await client.get("/public/datasets/CROP/entries/TEFF")).json()
    assert one["entry"]["label"] == "Teff" and one["version"] == 1


async def test_entries_paging_parent_filter_and_etag(client, public):
    await publish_list("LOC", codes=(), hierarchical=True)
    from openg2p_gen2_master_data.schemas.g2p_catalogue import CreateListDraftPayload, DraftValueInput

    await svc().create_list_draft(CreateListDraftPayload(list_code="LOC"), MAKER)
    await svc().upsert_draft_values(
        "LOC",
        [
            DraftValueInput(value_code="P", display="Parent", sort_order=0, display_i18n={"am": "ወላጅ"}),
            DraftValueInput(value_code="C1", display="Child 1", parent_code="P", sort_order=1),
            DraftValueInput(value_code="C2", display="Child 2", parent_code="P", sort_order=2),
        ],
        MAKER,
    )
    await submit_and_approve("LOC")
    await make_public("LOC")
    r = await client.get("/public/datasets/LOC/entries", params={"page": 2, "page_size": 2})
    body = r.json()
    assert (body["total"], [e["code"] for e in body["entries"]]) == (3, ["C2"])
    kids = (await client.get("/public/datasets/LOC/entries", params={"parent_code": "P"})).json()
    assert [e["code"] for e in kids["entries"]] == ["C1", "C2"]
    top = (await client.get("/public/datasets/LOC/entries", params={"parent_code": ""})).json()
    assert [e["code"] for e in top["entries"]] == ["P"]
    assert (await client.get("/public/datasets/LOC/entries", params={"page_size": 0})).status_code == 400

    assert r.headers["access-control-allow-origin"] == "*"
    assert r.headers["cache-control"].startswith("public")
    assert r.headers["last-modified"]
    etag = r.headers["etag"]
    again = await client.get(
        "/public/datasets/LOC/entries", params={"page": 2, "page_size": 2}, headers={"If-None-Match": etag}
    )
    assert again.status_code == 304 and again.content == b""


# ---------------------------------------------------------------------------
# Downloads
# ---------------------------------------------------------------------------


async def test_csv_and_json_downloads(client, public):
    from openg2p_gen2_master_data.schemas.g2p_catalogue import CreateListDraftPayload, DraftValueInput

    await publish_list("GENDER", codes=("F", "M"))
    await make_public("GENDER")
    await svc().create_list_draft(CreateListDraftPayload(list_code="GENDER"), MAKER)
    await svc().upsert_draft_values(
        "GENDER", [DraftValueInput(value_code="F", display="Female", display_i18n={"fr": "Femme"})], MAKER
    )
    await submit_and_approve("GENDER")

    r = await client.get("/public/datasets/GENDER/download.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert 'filename="GENDER-v2.csv"' in r.headers["content-disposition"]
    rows = list(csv.DictReader(io.StringIO(r.text)))
    assert [(x["code"], x["label"], x["label_fr"]) for x in rows] == [
        ("F", "Female", "Femme"),
        ("M", "M", ""),
    ]

    r = await client.get("/public/datasets/GENDER/download.json?version=1")
    body = r.json()
    assert (body["dataset"], body["version"]) == ("GENDER", 1)
    assert [e["code"] for e in body["entries"]] == ["F", "M"]
    assert body["entries"][0]["label"] == "F"


async def test_geography_private_then_public_with_downloads(client, public, s3):
    g = G2PCatalogueGeoService.get_component()
    await make_v1()
    # A draft (v2) is open and has a boundary; never public.
    from openg2p_gen2_master_data.schemas.g2p_catalogue import CreateGeoDraftPayload

    for path in ("/public/geography", "/public/geography/levels", "/public/geography/units"):
        assert (await client.get(path)).status_code == 404, path
    await geo_public(
        licence_label="CC BY-IGO", licence_uri="https://creativecommons.org/licenses/by/3.0/igo/"
    )
    settings = (await client.call("/catalogue/get_geo_settings", {}))["response_body"]["response_payload"]
    assert settings["settings"]["visibility"] == "public"

    await g.create_geo_draft(CreateGeoDraftPayload(), MAKER)
    await g.upload_draft_boundary("region", fc([("R1", [1, 1]), ("R2", [2, 2])]), MAKER)

    geo = (await client.get("/public/geography")).json()
    assert geo["version"] == 1 and geo["licence"]["label"] == "CC BY-IGO"
    assert [v["version"] for v in geo["versions"]] == [1]
    assert [lv["level"] for lv in geo["levels"]] == ["country", "region", "district"]
    assert {lv["level"]: lv["unit_count"] for lv in geo["levels"]} == {
        "country": 1,
        "region": 2,
        "district": 3,
    }
    # v1 has no boundary objects; the draft's upload is not reachable.
    assert all("geojson" not in lv["links"] for lv in geo["levels"])
    assert (await client.get("/public/geography/levels/region/boundaries.geojson")).status_code == 404
    assert (
        await client.get("/public/geography/levels/region/boundaries.geojson?version=2")
    ).status_code == 404

    units = (await client.get("/public/geography/units", params={"level": "district", "parent": "R1"})).json()
    assert [u["unit_id"] for u in units["units"]] == ["D1", "D2"]
    r = await client.get("/public/geography/levels/district/units.csv")
    rows = list(csv.DictReader(io.StringIO(r.text)))
    assert [(x["unit_id"], x["name"], x["parent_unit_id"]) for x in rows] == [
        ("D1", "Alpha", "R1"),
        ("D2", "Beta", "R1"),
        ("D3", "Gamma", "R2"),
    ]

    # Publish v2: its region boundary is now public and streamed from the store.
    from test_geo import approve

    await approve()
    geo = (await client.get("/public/geography")).json()
    region = next(lv for lv in geo["levels"] if lv["level"] == "region")
    assert region["links"]["geojson"] == f"{BASE}/public/geography/levels/region/boundaries.geojson?version=2"
    r = await client.get("/public/geography/levels/region/boundaries.geojson")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/geo+json")
    assert [f["properties"]["pcode"] for f in r.json()["features"]] == ["R1", "R2"]
    again = await client.get(
        "/public/geography/levels/region/boundaries.geojson", headers={"If-None-Match": r.headers["etag"]}
    )
    assert again.status_code == 304

    await geo_public("private")
    assert (await client.get("/public/geography/levels/region/boundaries.geojson")).status_code == 404


# ---------------------------------------------------------------------------
# Releases
# ---------------------------------------------------------------------------


async def test_releases_show_public_members_only(client, public):
    rel = G2PCatalogueReleaseService.get_component()
    await publish_list("CROP")
    await publish_list("SECRET")
    await make_public("CROP")
    await make_v1()
    await rel.create_release(CreateReleasePayload(release_code="2027.1", title="Season"), MAKER)
    await rel.set_release_members(
        SetReleaseMembersPayload(
            release_code="2027.1",
            members=[
                ReleaseMemberInput(list_code="CROP", version_no=1),
                ReleaseMemberInput(list_code="SECRET", version_no=1),
            ],
            geo_version_no=1,
        ),
        MAKER,
    )
    # A draft release is never public.
    assert (await client.get("/public/releases")).json() == {"releases": []}
    assert (await client.get("/public/releases/2027.1")).status_code == 404
    await rel.publish_release("2027.1", CHECKER)
    # Secret-only release: not listed at all.
    await rel.create_release(CreateReleasePayload(release_code="hidden"), MAKER)
    await rel.set_release_members(
        SetReleaseMembersPayload(
            release_code="hidden", members=[ReleaseMemberInput(list_code="SECRET", version_no=1)]
        ),
        MAKER,
    )
    await rel.publish_release("hidden", CHECKER)

    out = (await client.get("/public/releases")).json()["releases"]
    assert [r["code"] for r in out] == ["2027.1"]
    assert [m["dataset"] for m in out[0]["members"]] == ["CROP"]
    assert out[0]["geography_version"] is None  # geography is private
    assert (await client.get("/public/releases/hidden")).status_code == 404

    await geo_public()
    one = (await client.get("/public/releases/2027.1")).json()
    assert one["geography_version"] == 1 and "SECRET" not in json.dumps(one)


# ---------------------------------------------------------------------------
# DCAT and SKOS
# ---------------------------------------------------------------------------


async def test_dcat_catalog_jsonld(client, public, settings):
    settings.public_catalogue_publisher = "Ministry of Agriculture"
    await publish_list("CROP")
    await publish_list("GENDER")
    await publish_list("SECRET")
    await make_public(
        "CROP", licence_uri="https://creativecommons.org/licenses/by/4.0/", licence_label="CC BY 4.0"
    )
    await svc().update_list(UpdateListPayload(list_code="CROP", domain="agriculture", owner_org="MoA"), MAKER)
    await make_public("GENDER")
    await make_v1()  # geography private

    r = await client.get("/public/catalog")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/ld+json")
    doc = r.json()
    ctx = doc["@context"]
    assert ctx["dcat"] == "http://www.w3.org/ns/dcat#" and ctx["dct"] == "http://purl.org/dc/terms/"
    assert doc["@type"] == "dcat:Catalog" and doc["@id"] == f"{BASE}/public/catalog"
    assert doc["dct:publisher"]["foaf:name"] == "Ministry of Agriculture"
    datasets = [d for d in doc["dcat:dataset"] if d["@type"] == "dcat:Dataset"]
    assert len(datasets) == 2  # the public ones; SECRET and the private geography are absent
    assert "SECRET" not in json.dumps(doc)
    crop = next(d for d in datasets if d["dct:identifier"] == "CROP")
    assert crop["@id"] == f"{BASE}/public/datasets/CROP"
    assert crop["dct:license"]["@id"] == "https://creativecommons.org/licenses/by/4.0/"
    assert crop["dct:publisher"]["foaf:name"] == "MoA"
    assert crop["dcat:version"] == "1" and crop["owl:versionInfo"] == "1"
    assert crop["dcat:theme"]["@id"].endswith("#themes-agriculture")
    assert crop["dct:modified"]["@type"] == "xsd:dateTime"
    dists = {
        d["dcat:mediaType"]["@id"].rsplit("/", 2)[-2] + "/" + d["dcat:mediaType"]["@id"].rsplit("/", 1)[-1]: d
        for d in crop["dcat:distribution"]
    }
    assert set(dists) == {"text/csv", "application/json", "application/ld+json"}
    for d in crop["dcat:distribution"]:
        assert d["@type"] == "dcat:Distribution"
        assert d["dcat:downloadURL"]["@id"].startswith(f"{BASE}/public/datasets/CROP/")
        assert d["dct:format"]["@id"].startswith(
            "http://publications.europa.eu/resource/authority/file-type/"
        )
    assert doc["dcat:themeTaxonomy"]["skos:hasTopConcept"][0]["skos:prefLabel"] == "agriculture"

    # Every downloadURL in the catalogue works.
    for d in crop["dcat:distribution"]:
        path = d["dcat:downloadURL"]["@id"][len(BASE) :]
        assert (await client.get(path)).status_code == 200, path

    await geo_public(licence_label="CC0-1.0")
    doc = (await client.get("/public/catalog")).json()
    ids = [d["dct:identifier"] for d in doc["dcat:dataset"]]
    assert sorted(ids) == ["CROP", "GENDER", "geography"]
    geo = next(d for d in doc["dcat:dataset"] if d["dct:identifier"] == "geography")
    assert len(geo["dcat:distribution"]) == 3  # a units CSV per level, no boundaries in v1
    assert geo["dct:license"] == {"@type": "dct:LicenseDocument", "rdfs:label": "CC0-1.0"}


async def test_dcat_and_skos_parse_as_rdf_when_rdflib_is_available(client, public):
    rdflib = pytest.importorskip("rdflib")
    await publish_list("CROP")
    await make_public("CROP")
    g = rdflib.Graph().parse(data=(await client.get("/public/catalog")).text, format="json-ld")
    DCAT = rdflib.Namespace("http://www.w3.org/ns/dcat#")
    assert len(list(g.subjects(rdflib.RDF.type, DCAT.Dataset))) == 1
    assert len(list(g.objects(None, DCAT.downloadURL))) == 3
    skos = rdflib.Graph().parse(data=(await client.get("/public/datasets/CROP/skos")).text, format="json-ld")
    SKOS = rdflib.Namespace("http://www.w3.org/2004/02/skos/core#")
    assert len(list(skos.subjects(rdflib.RDF.type, SKOS.Concept))) == 3
    assert len(list(skos.subjects(rdflib.RDF.type, SKOS.ConceptScheme))) == 1


async def test_skos_concept_scheme(client, public):
    from openg2p_gen2_master_data.schemas.g2p_catalogue import CreateListDraftPayload, DraftValueInput

    await publish_list("LOC", codes=(), hierarchical=True)
    await svc().create_list_draft(CreateListDraftPayload(list_code="LOC"), MAKER)
    await svc().upsert_draft_values(
        "LOC",
        [
            DraftValueInput(
                value_code="P", display="Parent", sort_order=0, display_i18n={"am": "ወላጅ", "en": "Parent EN"}
            ),
            DraftValueInput(value_code="C/1", display="Child", parent_code="P", sort_order=1),
        ],
        MAKER,
    )
    await submit_and_approve("LOC")
    await make_public("LOC", licence_uri="https://creativecommons.org/publicdomain/zero/1.0/")

    r = await client.get("/public/datasets/LOC/skos")
    assert r.headers["content-type"].startswith("application/ld+json")
    doc = r.json()
    assert doc["@context"]["skos"] == "http://www.w3.org/2004/02/skos/core#"
    graph = doc["@graph"]
    scheme = next(n for n in graph if n["@type"] == "skos:ConceptScheme")
    concepts = {n["skos:notation"]: n for n in graph if n["@type"] == "skos:Concept"}
    assert scheme["@id"] == f"{BASE}/public/datasets/LOC/skos" and scheme["owl:versionInfo"] == "2"
    assert scheme["dct:license"]["@id"] == "https://creativecommons.org/publicdomain/zero/1.0/"
    assert set(concepts) == {"P", "C/1"}
    p, c = concepts["P"], concepts["C/1"]
    # display_i18n wins for its language; the plain display is not duplicated as "en".
    assert sorted((x["@language"], x["@value"]) for x in p["skos:prefLabel"]) == [
        ("am", "ወላጅ"),
        ("en", "Parent EN"),
    ]
    assert c["skos:prefLabel"] == [{"@value": "Child", "@language": "en"}]
    assert c["@id"] == f"{BASE}/public/datasets/LOC/entries/C%2F1"
    assert c["skos:broader"] == {"@id": p["@id"]}
    assert p["skos:topConceptOf"] == {"@id": scheme["@id"]}
    assert scheme["skos:hasTopConcept"] == [{"@id": p["@id"]}]
    assert c["skos:inScheme"] == {"@id": scheme["@id"]}
    # The concept IRI dereferences.
    assert (await client.get("/public/datasets/LOC/entries/C%2F1")).status_code == 200
    assert (await client.get("/public/datasets/LOC/skos?version=1")).json()["@graph"][0][
        "owl:versionInfo"
    ] == "1"


# ---------------------------------------------------------------------------
# Rate limit, base URL, authentication of everything else
# ---------------------------------------------------------------------------


async def test_rate_limit_per_client_ip(client, public):
    public.public_catalogue_rate_limit_per_minute = 3
    a = {"X-Forwarded-For": "203.0.113.7"}
    b = {"X-Forwarded-For": "198.51.100.9"}
    codes = [(await client.get("/public/datasets", headers=a)).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]
    r = await client.get("/public/datasets", headers=a)
    assert r.status_code == 429 and int(r.headers["retry-after"]) >= 1
    # Another client is not affected; a spoofed left-most entry does not help.
    assert (await client.get("/public/datasets", headers=b)).status_code == 200
    spoof = {"X-Forwarded-For": "10.0.0.1, 203.0.113.7"}
    assert (await client.get("/public/datasets", headers=spoof)).status_code == 429


async def test_base_url_from_request_when_not_configured(client, public):
    public.public_base_url = ""
    doc = (
        await client.get(
            "/public/catalog", headers={"X-Forwarded-Proto": "https", "X-Forwarded-Host": "cat.example.org"}
        )
    ).json()
    assert doc["@id"] == "https://cat.example.org/public/catalog"


async def test_catalogue_config_reports_public_catalogue(client, public):
    cfg = (await client.call("/catalogue/get_catalogue_config", {}))["response_body"]["response_payload"]
    assert cfg["public_catalogue_enabled"] is True and cfg["public_base_url"] == BASE


async def test_geo_settings_need_geo_edit_and_are_logged(client, db):
    from iam_core.user_auth.decorators import get_required_permissions

    routes = {r.path: r.endpoint for r in all_routes()}
    assert get_required_permissions(routes["/catalogue/update_geo_settings"]) == {"geo:edit"}
    assert get_required_permissions(routes["/catalogue/get_geo_settings"]) == set()
    out = await client.call(
        "/catalogue/update_geo_settings", {"visibility": "public", "licence_label": " CC0 "}
    )
    assert out["response_body"]["response_payload"]["settings"] == {
        "visibility": "public",
        "licence_uri": None,
        "licence_label": "CC0",
    }
    with db.cursor() as cur:
        cur.execute(
            "SELECT event_type, details FROM g2p_catalogue_change_log WHERE event_type = 'geo.settings.updated'"
        )
        ((event, details),) = cur.fetchall()
    assert details == {"visibility": "public", "licence_label": "CC0"}


def all_routes(routes=None):
    """Leaf routes of the app (included routers are nested in recent FastAPI)."""
    for r in APP.routes if routes is None else routes:
        inner = getattr(r, "original_router", None) or (
            r if hasattr(r, "routes") and not hasattr(r, "endpoint") else None
        )
        if inner is not None:
            yield from all_routes(inner.routes)
        elif getattr(r, "endpoint", None) is not None:
            yield r


# Routes that are anonymous on purpose, outside /public.
_ANONYMOUS = {"/ping", "/openapi.json", "/docs", "/redoc", "/docs/oauth2-redirect", "/catalogue/awe/callback"}


def test_every_non_public_route_requires_a_token_and_no_public_route_does():
    from iam_core.user_auth.decorators import endpoint_requires_token

    checked = public = 0
    for route in all_routes():
        path, endpoint = getattr(route, "path", ""), getattr(route, "endpoint", None)
        if endpoint is None or path in _ANONYMOUS:
            continue
        if path.startswith("/public/") or path == "/public":
            assert not endpoint_requires_token(endpoint), path
            assert getattr(route, "methods", None) == {"GET"}, path
            public += 1
        else:
            assert endpoint_requires_token(endpoint), path
            checked += 1
    assert checked > 50 and public == 15


async def test_non_public_routes_answer_401_without_a_token(public):
    """The real iam-core token middleware in front of the app: anonymous calls to
    the authenticated API are refused, /public is served."""
    import httpx
    from iam_core.user_auth.middleware import ValidateAndRefreshTokenMiddleware

    await publish_list("CROP")
    await make_public("CROP")
    guarded = ValidateAndRefreshTokenMiddleware(APP)

    async def app(scope, receive, send):
        scope.setdefault("app", APP)  # what Starlette sets before user middleware runs
        await guarded(scope, receive, send)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://mds") as c:
        from conftest import envelope

        for path in ("/catalogue/get_lists", "/catalogue/get_list_values", "/samples/get_individuals"):
            r = await c.post(path, json=envelope({"list_code": "CROP"}))
            assert r.status_code == 401, (path, r.status_code, r.text)
        r = await c.get("/attributes/get_all_attributes")
        assert r.status_code in (401, 405), r.status_code
        assert (await c.get("/public/datasets/CROP/entries")).status_code == 200


async def test_audit_skips_anonymous_public_successes_and_records_failures(public):
    """The per-call audit middleware: anonymous 200 / 304 on /public are not
    audited; anonymous failures (404, 429) are."""
    import httpx
    from openg2p_gen2_master_data.audit_middleware import AuditMiddleware

    await publish_list("CROP")
    await make_public("CROP")
    audit = AuditMiddleware(APP, audit_manager_url="http://audit.invalid", enabled=True)
    events = []

    async def emit(event):
        events.append(event)

    audit._emit = emit

    async def app(scope, receive, send):
        scope.setdefault("app", APP)
        await audit(scope, receive, send)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://mds") as c:
        r = await c.get("/public/datasets/CROP")
        assert r.status_code == 200
        assert (
            await c.get("/public/datasets/CROP", headers={"If-None-Match": r.headers["etag"]})
        ).status_code == 304
        import asyncio

        await asyncio.sleep(0)
        assert events == []
        assert (await c.get("/public/datasets/NOPE")).status_code == 404
        public.public_catalogue_rate_limit_per_minute = 1
        LIMITER.reset()
        await c.get("/public/datasets", headers={"X-Forwarded-For": "192.0.2.1"})
        assert (await c.get("/public/datasets", headers={"X-Forwarded-For": "192.0.2.1"})).status_code == 429
        await asyncio.sleep(0.05)
    assert [e["data"]["outcome"] if "data" in e else e for e in events] == ["failure", "failure"]
