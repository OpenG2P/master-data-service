"""Migration of pre-catalogue data to version 1, and the country-pack loader.

Both run the real entry points in a subprocess (``main.py migrate`` and
``docker/db-seed/load_geo_pack.py``), the way the container and the Job do.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import psycopg2
import pytest
from conftest import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER, pg_connect

REPO = Path(__file__).resolve().parents[2]
LOADER = REPO / "docker" / "db-seed" / "load_geo_pack.py"
PACKS = Path(os.environ.get("OPENG2P_PACKS", REPO.parent / "openg2p-data" / "packs"))
MIGRATION_DB = DB_NAME + "_migration"


def _env(dbname, **extra):
    env = dict(os.environ)
    env.update(
        {
            "MASTER_DATA_API_DB_DBNAME": dbname,
            "PGHOST": DB_HOST,
            "PGPORT": str(DB_PORT),
            "PGUSER": DB_USER,
            "PGPASSWORD": DB_PASSWORD,
            "CODELISTS_SQL_DIR": str(REPO / "scripts" / "seed-data" / "codelists"),
            "AUDIT_MANAGER_URL": "",
        }
    )
    env.update(extra)
    return env


def run_loader(pack, *args, dbname=DB_NAME, **env):
    proc = subprocess.run(
        [sys.executable, str(LOADER), "--pack", str(pack), "--db", dbname, *args],
        env=_env(dbname, **env),
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return proc.stdout


def q(sql, params=None, dbname=DB_NAME):
    conn = pg_connect(dbname)
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------


def test_migration_turns_existing_data_into_version_1():
    admin = pg_connect("postgres")
    admin.autocommit = True
    with admin.cursor() as cur:
        cur.execute(f'DROP DATABASE IF EXISTS "{MIGRATION_DB}"')
        cur.execute(f'CREATE DATABASE "{MIGRATION_DB}"')
    admin.close()
    # A pre-catalogue deployment: the old tables, with data.
    conn = pg_connect(MIGRATION_DB)
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE g2p_attributes (attribute_id varchar PRIMARY KEY, attribute_code varchar,
                                         attribute_display varchar, is_hierarchical boolean);
            CREATE TABLE g2p_attribute_values (value_id varchar, attribute_id varchar, value_code varchar,
                value_display varchar, parent_value_id varchar, sort_order integer,
                PRIMARY KEY (value_id, attribute_id));
            CREATE TABLE g2p_geo_levels (level_id varchar PRIMARY KEY, level_mnemonic varchar NOT NULL,
                                         parent_level_id varchar);
            CREATE TABLE g2p_geo_level_values (level_value_id varchar PRIMARY KEY, level_id varchar NOT NULL,
                level_value_mnemonic varchar NOT NULL, parent_level_value_id varchar);
            INSERT INTO g2p_attributes VALUES ('GENDER', 'GENDER', 'Gender', false),
                                              ('LOC', 'LOC', 'Location', true);
            INSERT INTO g2p_attribute_values VALUES ('F', 'GENDER', 'FEMALE', 'Female', NULL, 1),
                                                    ('M', 'GENDER', 'MALE', 'Male', NULL, 2),
                                                    ('P', 'LOC', 'P', 'Parent', NULL, 1),
                                                    ('C', 'LOC', 'C', 'Child', 'P', 2);
            INSERT INTO g2p_geo_levels VALUES ('l0', 'country', NULL), ('l1', 'region', 'l0');
            INSERT INTO g2p_geo_level_values VALUES ('XX', 'l0', 'Country', NULL), ('XX01', 'l1', 'North', 'XX'),
                                                    ('XX02', 'l1', 'South', 'NULL');
            """
        )
    conn.commit()
    conn.close()
    cmd = [sys.executable, "-m", "openg2p_gen2_master_data.main", "migrate"]
    for _ in range(2):  # idempotent
        proc = subprocess.run(cmd, env=_env(MIGRATION_DB), capture_output=True, text=True, timeout=300)
        assert proc.returncode == 0, proc.stderr[-3000:]

    rows = q(
        "SELECT list_id, version_no, status, effective_from::date FROM g2p_list_versions ORDER BY 1",
        dbname=MIGRATION_DB,
    )
    assert [(r[0], r[1], r[2]) for r in rows] == [("GENDER", 1, "PUBLISHED"), ("LOC", 1, "PUBLISHED")]
    assert str(rows[0][3]) == "1970-01-01"
    assert q(
        "SELECT value_code, parent_value_code FROM g2p_list_version_values WHERE list_id = 'LOC' ORDER BY 1",
        dbname=MIGRATION_DB,
    ) == [("C", "P"), ("P", None)]
    assert q(
        "SELECT attribute_id, current_version_no FROM g2p_attributes ORDER BY 1", dbname=MIGRATION_DB
    ) == [("GENDER", 1), ("LOC", 1)]
    assert q("SELECT version_no, status FROM g2p_geo_versions", dbname=MIGRATION_DB) == [(1, "PUBLISHED")]
    assert q("SELECT unit_id, parent_unit_id FROM g2p_geo_version_units ORDER BY 1", dbname=MIGRATION_DB) == [
        ("XX", None),
        ("XX01", "XX"),
        ("XX02", None),
    ]
    # Legacy rows untouched.
    assert q("SELECT count(*) FROM g2p_attribute_values", dbname=MIGRATION_DB) == [(4,)]
    assert q("SELECT count(*) FROM g2p_geo_level_values", dbname=MIGRATION_DB) == [(3,)]
    assert q(
        "SELECT event_type, count(*) FROM g2p_catalogue_change_log GROUP BY 1 ORDER BY 1", dbname=MIGRATION_DB
    ) == [("geo.version.migrated", 1), ("list.version.migrated", 2)]
    from openg2p_gen2_master_data.catalogue_sql import CATALOGUE_SCHEMA_VERSION

    assert q(
        "SELECT int_value FROM g2p_catalogue_state WHERE key = 'schema_version'", dbname=MIGRATION_DB
    ) == [(CATALOGUE_SCHEMA_VERSION,)]


def test_migration_backfills_display_names_and_keeps_published_rows_frozen():
    """Upgrading a catalogue that predates the *_by_name columns: names come from the change log."""
    dbname = DB_NAME + "_names"
    admin = pg_connect("postgres")
    admin.autocommit = True
    with admin.cursor() as cur:
        cur.execute(f'DROP DATABASE IF EXISTS "{dbname}"')
        cur.execute(f'CREATE DATABASE "{dbname}"')
    admin.close()
    cmd = [sys.executable, "-m", "openg2p_gen2_master_data.main", "migrate"]
    proc = subprocess.run(cmd, env=_env(dbname), capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stderr[-3000:]
    conn = pg_connect(dbname)
    with conn.cursor() as cur:
        # The previous schema: no name columns.
        for table, cols in (
            ("g2p_list_versions", ("created_by", "updated_by", "submitted_by", "decided_by")),
            ("g2p_geo_versions", ("created_by", "updated_by", "submitted_by", "decided_by")),
            ("g2p_catalogue_releases", ("created_by", "members_set_by", "published_by")),
            ("g2p_geo_changes", ("created_by",)),
        ):
            for c in cols:
                cur.execute(f"ALTER TABLE {table} DROP COLUMN {c}_name")
        cur.execute(
            """
            INSERT INTO g2p_attributes (attribute_id, attribute_code, attribute_display) VALUES ('L', 'L', 'L');
            INSERT INTO g2p_list_versions (list_id, version_no, status, created_by, updated_by, submitted_by,
                                           decided_by, effective_from)
            VALUES ('L', 1, 'PUBLISHED', 'u-1', 'u-1', 'u-1', 'u-2', now());
            INSERT INTO g2p_catalogue_releases (release_code, status, created_by, members_set_by, published_by)
            VALUES ('R', 'PUBLISHED', 'u-1', 'u-1', 'old-name-not-an-id');
            INSERT INTO g2p_catalogue_change_log (event_type, subject_type, subject_id, actor, actor_name, at)
            VALUES ('list.created', 'list', 'L', 'u-1', 'Abebe (old)', now()),
                   ('list.draft.submitted', 'list', 'L', 'u-1', 'Abebe', now()),
                   ('list.draft.approved', 'list', 'L', 'u-2', 'Sara', now()),
                   ('list.version.effective', 'list', 'L', 'system', NULL, now());
            """
        )
    conn.commit()
    conn.close()
    for _ in range(2):  # idempotent
        proc = subprocess.run(cmd, env=_env(dbname), capture_output=True, text=True, timeout=300)
        assert proc.returncode == 0, proc.stderr[-3000:]
    assert q(
        "SELECT created_by_name, updated_by_name, submitted_by_name, decided_by_name FROM g2p_list_versions",
        dbname=dbname,
    ) == [("Abebe", "Abebe", "Abebe", "Sara")]
    # An id with no named event stays NULL (readers show the id).
    assert q(
        "SELECT created_by_name, members_set_by_name, published_by_name FROM g2p_catalogue_releases",
        dbname=dbname,
    ) == [("Abebe", "Abebe", None)]
    # The guards are back on.
    conn = pg_connect(dbname)
    try:
        with conn.cursor() as cur, pytest.raises(psycopg2.Error, match="G2P-CAT-IMMUTABLE"):
            cur.execute("UPDATE g2p_list_versions SET decided_by_name = 'x'")
        conn.rollback()
        with conn.cursor() as cur, pytest.raises(psycopg2.Error, match="G2P-CAT-IMMUTABLE"):
            cur.execute("UPDATE g2p_catalogue_releases SET published_by_name = 'x'")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not (PACKS / "ETH").is_dir(), reason="openg2p-data packs not checked out")
def test_loader_eth_pack_initial_then_idempotent():
    out = run_loader(PACKS / "ETH", "--load", "geo,codelists,samples", "--domains", "agriculture")
    assert "geography: version 1 published (1271 units)" in out
    assert q("SELECT status, count(*) FROM g2p_list_versions GROUP BY 1") == [("PUBLISHED", 60)]
    assert q("SELECT count(*) FROM g2p_geo_level_values") == [(1271,)]
    assert q("SELECT count(*) FROM g2p_attribute_values") == [(332,)]
    assert q(
        "SELECT roles FROM g2p_list_version_values WHERE list_id = 'GENDER' AND value_code = 'FEMALE'"
    ) == [(["female"],)]
    assert q("SELECT country, effective_from IS NOT NULL FROM g2p_geo_versions") == [("ETH", True)]
    out = run_loader(PACKS / "ETH", "--load", "geo,codelists", "--domains", "agriculture")
    assert "pack matches published version 1" in out and "codelists unchanged: 60" in out
    assert q("SELECT count(*) FROM g2p_list_versions") == [(60,)]
    assert q("SELECT count(*) FROM g2p_geo_versions") == [(1,)]


def _mini_pack(tmp_path):
    pack = tmp_path / "TST"
    (pack / "codelists").mkdir(parents=True)
    (pack / "boundaries").mkdir()
    (pack / "manifest.json").write_text(
        json.dumps({"country": "TST", "version": "1", "levels": ["country", "region"]})
    )
    (pack / "levels.json").write_text(
        json.dumps(
            [
                {"level_id": "l0", "level_mnemonic": "country", "parent_level_id": None},
                {"level_id": "l1", "level_mnemonic": "region", "parent_level_id": "l0"},
            ]
        )
    )
    units = [
        {
            "level_value_id": "TS",
            "level_id": "l0",
            "level_value_mnemonic": "Testland",
            "parent_level_value_id": None,
        },
        {
            "level_value_id": "TS01",
            "level_id": "l1",
            "level_value_mnemonic": "North",
            "parent_level_value_id": "TS",
            "display_i18n": {"am": "ሰሜን"},
        },
        {
            "level_value_id": "TS02",
            "level_id": "l1",
            "level_value_mnemonic": "South",
            "parent_level_value_id": "TS",
        },
    ]
    (pack / "values.json").write_text(json.dumps(units, ensure_ascii=False))
    gender = {
        "attribute_id": "GENDER",
        "attribute_code": "GENDER",
        "attribute_display": "Gender",
        "is_hierarchical": False,
        "values": [
            {
                "value_id": "F",
                "value_code": "F",
                "value_display": "Female",
                "sort_order": 1,
                "roles": ["female"],
                "display_i18n": {"am": "ሴት"},
            },
            {
                "value_id": "M",
                "value_code": "M",
                "value_display": "Male",
                "sort_order": 2,
                "display_i18n": {},
            },
            {"value_id": "X", "value_code": "X", "value_display": "Other", "sort_order": 3},
        ],
    }
    (pack / "codelists" / "gender.json").write_text(json.dumps(gender, ensure_ascii=False))

    def boundary(level, feats):
        (pack / "boundaries" / f"{level}.geojson").write_text(
            json.dumps(
                {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "properties": {"pcode": p},
                            "geometry": {"type": "Point", "coordinates": c},
                        }
                        for p, c in feats
                    ],
                }
            )
        )

    boundary("country", [("TS", [0, 0])])
    boundary("region", [("TS01", [1, 1]), ("TS02", [2, 2])])
    return pack, boundary


@pytest.fixture()
def moto_s3():
    from moto.server import ThreadedMotoServer

    server = ThreadedMotoServer(port=0, verbose=False)
    server.start()
    host, port = server.get_host_and_port()
    # moto keeps one in-process backend for every server: start from an empty one.
    import urllib.request

    urllib.request.urlopen(
        urllib.request.Request(f"http://{host}:{port}/moto-api/reset", method="POST")
    ).close()
    yield f"http://{host}:{port}"
    server.stop()


def _keys(endpoint):
    import boto3

    s3 = boto3.client(
        "s3", endpoint_url=endpoint, aws_access_key_id="t", aws_secret_access_key="t", region_name="us-east-1"
    )
    return sorted(o["Key"] for o in s3.list_objects_v2(Bucket="openg2p-geo").get("Contents", []))


def test_loader_later_load_creates_drafts_and_never_overwrites(tmp_path, moto_s3):
    pack, boundary = _mini_pack(tmp_path)
    s3 = {"S3_ENDPOINT": moto_s3, "S3_ACCESS_KEY": "t", "S3_SECRET_KEY": "t"}
    out = run_loader(pack, "--load", "geo,codelists", **s3)
    assert "geography: version 1 published (3 units)" in out
    assert _keys(moto_s3) == ["geo/TST/v1/country.geojson", "geo/TST/v1/region.geojson"]
    assert q("SELECT name_i18n FROM g2p_geo_version_units WHERE unit_id = 'TS01'") == [({"am": "ሰሜን"},)]
    assert q("SELECT display_i18n, roles FROM g2p_list_version_values WHERE value_id = 'F'") == [
        ({"am": "ሴት"}, ["female"])
    ]

    # The country changes: TS02 is gone, TS03 is new, TS01 renamed, a region boundary moved;
    # a gender value is relabelled and one removed.
    units = json.loads((pack / "values.json").read_text())
    units = [u for u in units if u["level_value_id"] != "TS02"]
    units[1]["level_value_mnemonic"] = "North Renamed"
    units.append(
        {
            "level_value_id": "TS03",
            "level_id": "l1",
            "level_value_mnemonic": "East",
            "parent_level_value_id": "TS",
        }
    )
    (pack / "values.json").write_text(json.dumps(units, ensure_ascii=False))
    boundary("region", [("TS01", [1, 5]), ("TS03", [3, 3])])
    gender = json.loads((pack / "codelists" / "gender.json").read_text())
    gender["values"] = [v for v in gender["values"] if v["value_id"] != "X"]
    gender["values"][1]["value_display"] = "Man"
    (pack / "codelists" / "gender.json").write_text(json.dumps(gender, ensure_ascii=False))

    out = run_loader(pack, "--load", "geo,codelists", **s3)
    assert "draft version 2 created for approval" in out and "codelists draft created for approval: 1" in out
    # Drafts only: published data and the legacy tables are untouched.
    assert q("SELECT version_no, status FROM g2p_geo_versions ORDER BY 1") == [(1, "PUBLISHED"), (2, "DRAFT")]
    assert q("SELECT version_no, status FROM g2p_list_versions ORDER BY 1") == [
        (1, "PUBLISHED"),
        (2, "DRAFT"),
    ]
    assert q("SELECT level_value_mnemonic FROM g2p_geo_level_values WHERE level_value_id = 'TS01'") == [
        ("North",)
    ]
    assert q("SELECT count(*) FROM g2p_attribute_values WHERE attribute_id = 'GENDER'") == [(3,)]
    assert q("SELECT unit_id, status FROM g2p_geo_version_units WHERE version_no = 2 ORDER BY 1") == [
        ("TS", "ACTIVE"),
        ("TS01", "ACTIVE"),
        ("TS02", "RETIRED"),
        ("TS03", "ACTIVE"),
    ]
    assert q(
        "SELECT value_id, status, display FROM g2p_list_version_values WHERE version_no = 2 ORDER BY 1"
    ) == [("F", "ACTIVE", "Female"), ("M", "ACTIVE", "Man"), ("X", "RETIRED", "Other")]
    assert q("SELECT boundary_objects FROM g2p_geo_versions WHERE version_no = 2") == [
        ({"country": "geo/TST/v1/country.geojson", "region": "geo/TST/v2/region.geojson"},)
    ]
    assert "geo/TST/v2/region.geojson" in _keys(moto_s3)

    # An open draft is left alone.
    out = run_loader(pack, "--load", "geo,codelists", **s3)
    assert "version 2 is open (DRAFT); not touching it" in out
    assert q("SELECT count(*) FROM g2p_geo_versions") == [(2,)]

    # Development: --publish publishes the drafts a load creates. The open drafts
    # are discarded first (as discard_draft does): their numbers stay taken.
    conn = pg_connect()
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("UPDATE g2p_geo_versions SET status = 'DISCARDED' WHERE status = 'DRAFT'")
        cur.execute("UPDATE g2p_list_versions SET status = 'DISCARDED' WHERE status = 'DRAFT'")
    conn.close()
    out = run_loader(pack, "--load", "geo,codelists", "--publish", **s3)
    assert "version 3 published (--publish)" in out
    assert q("SELECT version_no, status FROM g2p_geo_versions ORDER BY 1") == [
        (1, "PUBLISHED"),
        (2, "DISCARDED"),
        (3, "PUBLISHED"),
    ]
    assert q("SELECT version_no, status FROM g2p_list_versions ORDER BY 1") == [
        (1, "PUBLISHED"),
        (2, "DISCARDED"),
        (3, "PUBLISHED"),
    ]
    # The new version's boundary lands under its own key, not over the discarded draft's.
    assert {"geo/TST/v2/region.geojson", "geo/TST/v3/region.geojson"} <= set(_keys(moto_s3))
    assert q("SELECT level_value_mnemonic FROM g2p_geo_level_values WHERE level_value_id = 'TS01'") == [
        ("North Renamed",)
    ]
    assert q("SELECT count(*) FROM g2p_geo_level_values WHERE level_value_id = 'TS02'") == [(0,)]
    assert sorted(q("SELECT value_code FROM g2p_attribute_values WHERE attribute_id = 'GENDER'")) == [
        ("F",),
        ("M",),
    ]
    events = q(
        "SELECT change_type, from_units, to_units FROM g2p_geo_changes WHERE version_no = 3 ORDER BY 1, 2"
    )
    assert ("RENAME", ["TS01"], ["TS01"]) in events and ("RETIRE", ["TS02"], []) in events
    assert ("CREATE", [], ["TS03"]) in events and ("BOUNDARY_CHANGE", ["TS01"], ["TS01"]) in events
    # v1's objects were never overwritten.
    assert q("SELECT boundary_objects->>'region' FROM g2p_geo_versions WHERE version_no = 1") == [
        ("geo/TST/v1/region.geojson",)
    ]


def test_loader_skips_a_requested_domain_the_pack_does_not_carry(tmp_path):
    """The chart asks for agriculture by default; a pack without it still loads
    its core lists, with a warning, instead of failing the seed Job."""
    pack, _ = _mini_pack(tmp_path)
    out = run_loader(pack, "--load", "codelists", "--domains", "agriculture")
    assert "domain 'agriculture' not in pack TST — skipped" in out
    assert q("SELECT count(*) FROM g2p_list_version_values WHERE value_id IN ('F', 'M', 'X')") == [(3,)]
    shutil.rmtree(pack)


def test_loader_needs_the_catalogue_schema(tmp_path):
    pack, _ = _mini_pack(tmp_path)
    admin = pg_connect("postgres")
    admin.autocommit = True
    with admin.cursor() as cur:
        cur.execute(f'DROP DATABASE IF EXISTS "{DB_NAME}_empty"')
        cur.execute(f'CREATE DATABASE "{DB_NAME}_empty"')
    admin.close()
    proc = subprocess.run(
        [sys.executable, str(LOADER), "--pack", str(pack), "--db", f"{DB_NAME}_empty"],
        env=_env(f"{DB_NAME}_empty"),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode != 0 and "catalogue schema is missing" in (proc.stdout + proc.stderr)
    shutil.rmtree(pack)


def test_loader_validates_pack_change_events_before_publishing(tmp_path):
    """changes.json goes through the API's own rules (catalogue_geo_rules); an invalid
    event fails the load — with --publish nothing is published — and a valid one is kept."""
    pack, _ = _mini_pack(tmp_path)
    run_loader(pack, "--load", "geo")
    # TS02 is split into TS03 + TS04.
    units = [u for u in json.loads((pack / "values.json").read_text()) if u["level_value_id"] != "TS02"]
    for uid, name in (("TS03", "South-East"), ("TS04", "South-West")):
        units.append(
            {
                "level_value_id": uid,
                "level_id": "l1",
                "level_value_mnemonic": name,
                "parent_level_value_id": "TS",
            }
        )
    (pack / "values.json").write_text(json.dumps(units, ensure_ascii=False))
    # Invalid: a SPLIT needs at least two parts.
    (pack / "changes.json").write_text(
        json.dumps([{"change_type": "SPLIT", "from_units": ["TS02"], "to_units": ["TS03"], "note": "split"}])
    )
    proc = subprocess.run(
        [sys.executable, str(LOADER), "--pack", str(pack), "--db", DB_NAME, "--load", "geo", "--publish"],
        env=_env(DB_NAME),
        capture_output=True,
        text=True,
        timeout=300,
    )
    out = proc.stdout + proc.stderr
    assert proc.returncode != 0
    assert "changes.json event #1 (SPLIT ['TS02'] -> ['TS03']) is invalid" in out
    assert "needs at least two to-units" in out
    # Nothing was written: still only version 1, legacy tables untouched.
    assert q("SELECT version_no, status FROM g2p_geo_versions ORDER BY 1") == [(1, "PUBLISHED")]
    assert q("SELECT count(*) FROM g2p_geo_level_values WHERE level_value_id = 'TS02'") == [(1,)]

    # Fixed: the explicit SPLIT is recorded and published; lineage completion adds nothing
    # for the units it covers.
    (pack / "changes.json").write_text(
        json.dumps(
            [{"change_type": "SPLIT", "from_units": ["TS02"], "to_units": ["TS03", "TS04"], "note": "split"}]
        )
    )
    out = run_loader(pack, "--load", "geo", "--publish")
    assert "version 2 published (--publish)" in out
    assert q(
        "SELECT change_type, from_units, to_units, is_auto FROM g2p_geo_changes WHERE version_no = 2 ORDER BY 1"
    ) == [("SPLIT", ["TS02"], ["TS03", "TS04"], False)]
    # The loader's events wait in the outbox for the API's relay.
    assert q(
        "SELECT count(*) FROM g2p_catalogue_change_log WHERE event_type = 'geo.version.published' "
        "AND forwarded_at IS NULL"
    ) == [(2,)]


def test_loader_sets_list_domain_and_fills_it_when_empty(tmp_path):
    """Core lists get domain 'core', domain lists their domain; a re-run fills an
    empty domain (lists loaded before the column existed) and keeps one already set.
    No new version is created for it: the domain is administrative."""
    pack, _ = _mini_pack(tmp_path)
    agri = pack / "domains" / "agriculture"
    agri.mkdir(parents=True)
    crop = {
        "attribute_id": "CROP",
        "attribute_code": "CROP",
        "attribute_display": "Crop",
        "values": [{"value_id": "MAIZE", "value_code": "MAIZE", "value_display": "Maize", "sort_order": 1}],
    }
    (agri / "crop.json").write_text(json.dumps(crop))
    run_loader(pack, "--load", "codelists", "--domains", "agriculture")
    assert q("SELECT attribute_id, domain FROM g2p_attributes ORDER BY 1") == [
        ("CROP", "agriculture"),
        ("GENDER", "core"),
    ]
    conn = pg_connect()
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("UPDATE g2p_attributes SET domain = NULL WHERE attribute_id = 'CROP'")
        cur.execute("UPDATE g2p_attributes SET domain = 'social' WHERE attribute_id = 'GENDER'")
    conn.close()
    out = run_loader(pack, "--load", "codelists", "--domains", "agriculture")
    assert "codelists unchanged: 2" in out
    assert q("SELECT attribute_id, domain FROM g2p_attributes ORDER BY 1") == [
        ("CROP", "agriculture"),
        ("GENDER", "social"),
    ]
    assert q("SELECT count(*) FROM g2p_list_versions") == [(2,)]
    shutil.rmtree(pack)


def test_loader_sets_geography_licence_from_manifest_and_keeps_an_admins(tmp_path):
    """The manifest's licence fills geo.licence_* (URI derived for a known label) when
    none is set; one set by an administrator is kept. Visibility stays private."""
    pack, _ = _mini_pack(tmp_path)
    manifest = json.loads((pack / "manifest.json").read_text())
    manifest["license"] = "Creative Commons Attribution for Intergovernmental Organisations (CC BY-IGO)"
    (pack / "manifest.json").write_text(json.dumps(manifest))
    run_loader(pack, "--load", "geo")
    state = dict(
        q(
            "SELECT key, text_value FROM g2p_catalogue_state WHERE key LIKE 'geo.%%' AND text_value IS NOT NULL"
        )
    )
    assert state["geo.licence_uri"] == "https://creativecommons.org/licenses/by/3.0/igo/"
    assert state["geo.licence_label"].endswith("(CC BY-IGO)")
    assert "geo.visibility" not in state

    conn = pg_connect()
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("UPDATE g2p_catalogue_state SET text_value = 'CC0' WHERE key = 'geo.licence_label'")
    conn.close()
    out = run_loader(pack, "--load", "geo")
    assert "geography licence already set — kept" in out
    assert q("SELECT text_value FROM g2p_catalogue_state WHERE key = 'geo.licence_label'") == [("CC0",)]
