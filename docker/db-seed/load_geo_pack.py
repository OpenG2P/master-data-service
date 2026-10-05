#!/usr/bin/env python3
"""Seed the Master Data catalogue from a country pack.

    python load_geo_pack.py --pack /openg2p-data/packs/XKM

Why this lives in MDS
---------------------
MDS owns geography and the country's code lists, so it seeds its own data at
its own install rather than as a side effect of installing a registry.

Catalogue-aware: initial vs later loads
---------------------------------------
Master Data is a versioned catalogue: published versions are immutable, and
edits go through a draft that someone approves. The loader follows the same
rules instead of overwriting rows in place.

* Initial load of a subject (a list that does not exist yet; geography with
  no version yet): the pack is loaded as VERSION 1 and PUBLISHED directly
  (``--publish-initial``, default on), boundaries uploaded under the v1 keys.
  There is nothing published to protect yet.
* Later loads: each list (and the geography) is compared with its highest
  published version. If the pack differs, a DRAFT is created — values / units
  missing from the pack are RETIRED, never deleted — and left for someone to
  submit and approve in Master Data. ``--publish`` publishes those drafts at
  once instead (development only). A subject that already has an open draft
  is left alone. Identical content creates nothing, so re-running is a no-op.

Publishing (and the legacy-table refresh that goes with it) is done by the
database function the API uses too (g2p_catalogue_publish_list / _geo), and
every step is written to the catalogue change log. The loader does not call the
Audit Manager or WebSub itself: the change log is the outbox, and the API's
relay forwards these events like its own (so AUDIT_MANAGER_URL is not used).

Version numbers come from the same database functions as the API's
(g2p_catalogue_next_list_version / _geo_version) and are never reused, even
after a draft was discarded — so a new draft's boundary keys can never collide
with another version's.

Lineage events from changes.json are checked with the API's own rules
(catalogue_geo_rules.py, copied next to this script in the image) before
anything is written; an invalid event fails the geography load with a message
naming it. With --publish the lineage is then completed (automatic CREATE /
RETIRE / RENAME / REPARENT / BOUNDARY_CHANGE events) exactly as the API does on
submit.

Boundaries go to S3/MinIO under immutable, versioned keys
``geo/<country>/v<version>/<level>.geojson``; a level whose file did not change
keeps pointing at the earlier version's object. Without an S3 endpoint the
hierarchy still loads; only the map layer is missing.

Pack-flavour agnostic
---------------------
Reads levels.json, values.json, manifest.json, codelists/, domains/<d>/,
samples/ and optionally boundaries/*.geojson and changes.json (explicit
lineage events: [{"change_type", "from_units", "to_units", "note"}]). Labels
per locale (display_i18n / name_i18n), roles and P-codes are kept.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import sys

import psycopg2
import psycopg2.extras

ACTOR_DEFAULT = "country-pack-loader"
# The API's migration writes this; the loader needs the functions it creates
# (2: version allocation that never reuses numbers, outbox change log).
REQUIRED_SCHEMA_VERSION = 4  # 4: g2p_attributes.domain


def _geo_rules():
    """The API's change-event rules: next to this script in the image, in the repo otherwise."""
    try:
        import catalogue_geo_rules  # noqa: F401  (image: /seed/catalogue_geo_rules.py)
    except ImportError:
        here = os.path.dirname(os.path.abspath(__file__))
        sys.path.insert(
            0, os.path.join(here, "..", "..", "master-data-api", "src", "openg2p_gen2_master_data")
        )
        import catalogue_geo_rules  # noqa: F401
    return catalogue_geo_rules


def load_pack(pack_dir):
    def read(name):
        path = os.path.join(pack_dir, name)
        if not os.path.exists(path):
            raise SystemExit(f"pack is missing {name} — is {pack_dir} a country pack?")
        with open(path) as fh:
            return json.load(fh)

    return read("levels.json"), read("values.json"), read("manifest.json")


def _norm(value):
    """Empty label maps / role lists / strings compare equal to absent."""
    if value in ({}, [], ""):
        return None
    return value


def _jsonb(value):
    value = _norm(value)
    return psycopg2.extras.Json(value) if value is not None else None


# ---------------------------------------------------------------------------
# Change log + optional Audit Manager
# ---------------------------------------------------------------------------


class ChangeLog:
    """Writes the catalogue change log in the caller's transaction.

    Delivery to the Audit Manager / WebSub is the API's job: its outbox relay
    forwards every change-log row not yet forwarded, whoever wrote it.
    """

    def __init__(self, actor):
        self.actor = actor

    def log(self, cur, event_type, subject_type, subject_id, version_no, details):
        cur.execute(
            "SELECT g2p_catalogue_log(%s, %s, %s, %s, %s, %s)",
            (event_type, subject_type, subject_id, version_no, self.actor, psycopg2.extras.Json(details or {})),
        )
        return cur.fetchone()[0]


def require_catalogue_schema(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('public.g2p_catalogue_state') IS NOT NULL")
        if not cur.fetchone()[0]:
            raise SystemExit("[geo-pack] the Master Data catalogue schema is missing — start master-data-api "
                             "(its migration creates it) before seeding")
        cur.execute("SELECT int_value FROM g2p_catalogue_state WHERE key = 'schema_version'")
        row = cur.fetchone()
        if not row or (row[0] or 0) < REQUIRED_SCHEMA_VERSION:
            raise SystemExit(f"[geo-pack] catalogue schema version {row[0] if row else None} < "
                             f"{REQUIRED_SCHEMA_VERSION}; upgrade master-data-api first")


# ---------------------------------------------------------------------------
# Boundaries
# ---------------------------------------------------------------------------


def geometry_hash(geometry):
    # Same function as the API's (services/g2p_catalogue_geo_service.py).
    return hashlib.sha256(json.dumps(geometry, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]


def read_boundaries(pack_dir):
    """{level_mnemonic: {"path", "sha256", "bytes", "units": {pcode: geometry hash}}}."""
    bdir = os.path.join(pack_dir, "boundaries")
    if not os.path.isdir(bdir):
        return {}
    out = {}
    for f in sorted(x for x in os.listdir(bdir) if x.endswith(".geojson")):
        path = os.path.join(bdir, f)
        with open(path, "rb") as fh:
            raw = fh.read()
        units = {}
        try:
            for feat in json.loads(raw).get("features") or []:
                props = feat.get("properties") or {}
                uid = props.get("pcode") or props.get("unit_id") or props.get("level_value_id") or feat.get("id")
                if uid:
                    units[str(uid)] = geometry_hash(feat.get("geometry"))
        except ValueError:
            print(f"[geo-pack] WARNING: {f} is not valid JSON — uploading as-is", file=sys.stderr)
        out[f[: -len(".geojson")]] = {
            "path": path,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "bytes": len(raw),
            "units": units,
        }
    return out


class BoundaryUploader:
    """Puts boundary files into S3/MinIO. Disabled without --s3-endpoint."""

    def __init__(self, args):
        self.endpoint = args.s3_endpoint
        self.bucket = args.s3_bucket
        self.public_base = (args.boundary_base_url or "").rstrip("/")
        self._s3 = None
        if self.endpoint:
            try:
                import boto3
            except ImportError:
                print("[geo-pack] boto3 not installed — boundaries will not be uploaded", file=sys.stderr)
                self.endpoint = None
                return
            self._s3 = boto3.client(
                "s3",
                endpoint_url=self.endpoint,
                aws_access_key_id=os.environ.get("S3_ACCESS_KEY"),
                aws_secret_access_key=os.environ.get("S3_SECRET_KEY"),
                region_name=os.environ.get("S3_REGION", "us-east-1"),
            )
            try:
                self._s3.head_bucket(Bucket=self.bucket)
            except Exception:
                self._s3.create_bucket(Bucket=self.bucket)
                print(f"[geo-pack] created bucket {self.bucket}")

    @property
    def enabled(self):
        return self._s3 is not None

    def put(self, key, path):
        ctype = mimetypes.guess_type(path)[0] or "application/geo+json"
        with open(path, "rb") as fh:
            self._s3.put_object(Bucket=self.bucket, Key=key, Body=fh, ContentType=ctype)
        print(f"[geo-pack] uploaded {key}")


def boundary_key(country, version_no, level):
    return f"geo/{country}/v{version_no}/{level}.geojson"


def _key_used_by_other_version(cur, key, version_no):
    # The key carries a never-reused version number, so this cannot happen for
    # data written by this loader or the API; it guards against older data.
    cur.execute(
        "SELECT 1 FROM g2p_geo_versions g, jsonb_each_text(coalesce(g.boundary_objects, '{}'::jsonb)) o "
        "WHERE g.version_no <> %s AND o.value = %s LIMIT 1",
        (version_no, key),
    )
    return cur.fetchone() is not None


def place_boundaries(cur, uploader, boundaries, country, version_no, base_objects, base_sums):
    """Upload what changed for this version; return (objects, checksums, changed levels)."""
    objects = dict(base_objects or {})
    sums = dict(base_sums or {})
    changed = []
    for level, meta in boundaries.items():
        same_content = (sums.get(level) or {}).get("sha256") == meta["sha256"]
        has_object = bool(objects.get(level))
        if same_content and (has_object or not uploader.enabled):
            continue
        sums[level] = {"sha256": meta["sha256"], "bytes": meta["bytes"], "units": meta["units"]}
        if uploader.enabled:
            key = boundary_key(country, version_no, level)
            if _key_used_by_other_version(cur, key, version_no):
                raise SystemExit(f"[geo-pack] {key} belongs to another geography version — refusing to overwrite")
            uploader.put(key, meta["path"])
            objects[level] = key
        changed.append(level)
    if changed and not uploader.enabled:
        print(f"[geo-pack] boundaries for {changed} recorded by checksum only (no S3 endpoint configured)")
    return objects, sums, changed


# ---------------------------------------------------------------------------
# Geography
# ---------------------------------------------------------------------------


def desired_geo(levels, values):
    lv = {}
    for x in levels:
        lv[x["level_id"]] = {
            "level_mnemonic": x["level_mnemonic"],
            "parent_level_id": x.get("parent_level_id") or None,
            "display": x.get("display") or x.get("level_display") or x["level_mnemonic"],
            "display_i18n": _norm(x.get("display_i18n") or x.get("label_i18n")),
        }
    units = {}
    for v in values:
        units[v["level_value_id"]] = {
            "level_id": v["level_id"],
            "name": v["level_value_mnemonic"],
            "name_i18n": _norm(v.get("name_i18n") or v.get("display_i18n")),
            "parent_unit_id": v.get("parent_level_value_id") or None,
        }
    return lv, units


def _insert_levels(cur, version_no, levels):
    psycopg2.extras.execute_values(
        cur,
        """INSERT INTO g2p_geo_version_levels
             (version_no, level_id, level_mnemonic, parent_level_id, display, display_i18n)
           VALUES %s
           ON CONFLICT (version_no, level_id) DO UPDATE
             SET level_mnemonic = EXCLUDED.level_mnemonic, parent_level_id = EXCLUDED.parent_level_id,
                 display = EXCLUDED.display, display_i18n = EXCLUDED.display_i18n""",
        [
            (version_no, lid, x["level_mnemonic"], x["parent_level_id"], x["display"], _jsonb(x["display_i18n"]))
            for lid, x in levels.items()
        ],
    )


def _upsert_units(cur, version_no, units):
    if not units:
        return
    psycopg2.extras.execute_values(
        cur,
        """INSERT INTO g2p_geo_version_units
             (version_no, unit_id, level_id, name, name_i18n, parent_unit_id, status)
           VALUES %s
           ON CONFLICT (version_no, unit_id) DO UPDATE
             SET level_id = EXCLUDED.level_id, name = EXCLUDED.name, name_i18n = EXCLUDED.name_i18n,
                 parent_unit_id = EXCLUDED.parent_unit_id, status = 'ACTIVE'""",
        [
            (version_no, uid, u["level_id"], u["name"], _jsonb(u["name_i18n"]), u["parent_unit_id"], "ACTIVE")
            for uid, u in units.items()
        ],
        page_size=500,
    )


def _record_pack_changes(cur, pack_dir, version_no, actor, base_no, base_units):
    """Explicit lineage from the pack's changes.json, for the events that apply to
    this base (their from-units still active there); earlier events are skipped.

    Each event is checked with the API's rules (catalogue_geo_rules) against the
    base and the draft as loaded; an invalid one stops the load (SystemExit)
    before anything is committed.
    """
    path = os.path.join(pack_dir, "changes.json")
    if not os.path.exists(path):
        return 0
    with open(path) as fh:
        docs = json.load(fh)
    rules = _geo_rules()
    cur.execute(
        "SELECT unit_id, level_id, name, parent_unit_id, status FROM g2p_geo_version_units WHERE version_no = %s",
        (version_no,),
    )
    draft_units = {
        r[0]: {"level_id": r[1], "name": r[2], "parent_unit_id": r[3], "status": r[4]} for r in cur.fetchall()
    }
    terminal = []  # (change_id, change_type, from_units) recorded so far
    n = 0
    for i, c in enumerate(docs, start=1):
        froms = c.get("from_units") or []
        tos = c.get("to_units") or []
        if froms and not all((base_units.get(u) or {}).get("status") == "ACTIVE" for u in froms):
            continue
        if not froms and all((base_units.get(u) or {}).get("status") == "ACTIVE" for u in tos):
            continue
        change_type = c.get("change_type")
        try:
            froms, tos = rules.check_geo_change(
                change_type,
                froms,
                tos,
                base_version_no=base_no,
                base_units=base_units,
                draft_units=draft_units,
                other_terminal_events=terminal,
            )
        except rules.GeoChangeRuleError as exc:
            raise SystemExit(
                f"[geo-pack] changes.json event #{i} ({change_type} {c.get('from_units') or []} -> "
                f"{c.get('to_units') or []}) is invalid: {exc.message}. Nothing was loaded for geography; "
                "fix changes.json (or the units) and load again."
            ) from None
        cur.execute(
            """INSERT INTO g2p_geo_changes (version_no, change_type, from_units, to_units, note, is_auto,
                                            created_by, created_at)
               VALUES (%s, %s, %s, %s, %s, false, %s, now()) RETURNING change_id""",
            (version_no, change_type, froms, tos, c.get("note"), actor),
        )
        change_id = cur.fetchone()[0]
        if change_type in rules.TERMINAL:
            terminal.append((change_id, change_type, froms))
        n += 1
    return n


def load_geo(conn, pack_dir, levels, values, manifest, args, uploader, log):
    country = args.country
    want_levels, want_units = desired_geo(levels, values)
    boundaries = read_boundaries(pack_dir)
    pack_label = f"country pack {country} ({manifest.get('version') or manifest.get('fetched_on') or '-'})"

    with conn.cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(hashtext('g2p_geo_draft'))")
        cur.execute("SELECT max(version_no) FROM g2p_geo_versions WHERE status = 'PUBLISHED'")
        base_no = cur.fetchone()[0]
        cur.execute("SELECT version_no, status FROM g2p_geo_versions WHERE status IN ('DRAFT', 'SUBMITTED')")
        open_row = cur.fetchone()

        if open_row:
            print(f"[geo-pack] geography: version {open_row[0]} is open ({open_row[1]}); not touching it")
            conn.rollback()
            return

        if base_no is None:
            # ---- initial load: the first published geography version --------------
            # Version 1 on a fresh install; the next unused number if earlier drafts
            # were discarded or rejected (numbers are never reused).
            cur.execute("SELECT g2p_catalogue_next_geo_version()")
            first = cur.fetchone()[0]
            cur.execute(
                """INSERT INTO g2p_geo_versions (version_no, status, country, owner_org, change_note,
                       boundary_objects, boundary_checksums, created_by, created_at, updated_by, updated_at)
                   VALUES (%s, 'DRAFT', %s, %s, %s, '{}'::jsonb, '{}'::jsonb, %s, now(), %s, now())""",
                (first, country, args.owner_org, f"Initial load from {pack_label}", args.actor, args.actor),
            )
            _insert_levels(cur, first, want_levels)
            _upsert_units(cur, first, want_units)
            objects, sums, _ = place_boundaries(cur, uploader, boundaries, country, first, {}, {})
            cur.execute(
                "UPDATE g2p_geo_versions SET boundary_objects = %s, boundary_checksums = %s WHERE version_no = %s",
                (psycopg2.extras.Json(objects), psycopg2.extras.Json(sums), first),
            )
            log.log(cur, "geo.draft.created", "geo", "geography", first,
                    {"source": pack_label, "units": len(want_units), "levels": len(want_levels)})
            if args.publish_initial:
                cur.execute("SELECT g2p_catalogue_publish_geo(%s, %s, NULL, %s, true)",
                            (first, args.actor, pack_label))
                log.log(cur, "geo.version.published", "geo", "geography", first,
                        {"source": pack_label, "boundary_objects": objects, "initial": True})
                print(f"[geo-pack] geography: version {first} published ({len(want_units)} units)")
            else:
                print(f"[geo-pack] geography: version {first} left as DRAFT ({len(want_units)} units)")
            conn.commit()
            return

        # ---- later load: compare with the highest published version -------------
        cur.execute(
            "SELECT level_id, level_mnemonic, parent_level_id, display, display_i18n "
            "FROM g2p_geo_version_levels WHERE version_no = %s",
            (base_no,),
        )
        have_levels = {
            r[0]: {"level_mnemonic": r[1], "parent_level_id": r[2], "display": r[3] or r[1],
                   "display_i18n": _norm(r[4])}
            for r in cur.fetchall()
        }
        cur.execute(
            "SELECT unit_id, level_id, name, name_i18n, parent_unit_id, status "
            "FROM g2p_geo_version_units WHERE version_no = %s",
            (base_no,),
        )
        have_units = {
            r[0]: {"level_id": r[1], "name": r[2], "name_i18n": _norm(r[3]), "parent_unit_id": r[4],
                   "status": r[5]}
            for r in cur.fetchall()
        }
        cur.execute(
            "SELECT boundary_objects, boundary_checksums, country FROM g2p_geo_versions WHERE version_no = %s",
            (base_no,),
        )
        base_objects, base_sums, base_country = cur.fetchone()
        country = base_country or country

        level_changes = {lid: x for lid, x in want_levels.items() if have_levels.get(lid) != x}
        unit_changes = {}
        for uid, u in want_units.items():
            h = have_units.get(uid)
            if h is None or h["status"] != "ACTIVE" or {k: h[k] for k in u} != u:
                unit_changes[uid] = u
        retire = sorted(uid for uid, h in have_units.items() if h["status"] == "ACTIVE" and uid not in want_units)
        dropped_levels = sorted(set(have_levels) - set(want_levels))
        boundary_dirty = [
            lvl for lvl, meta in boundaries.items()
            if ((base_sums or {}).get(lvl) or {}).get("sha256") != meta["sha256"]
            or (uploader.enabled and not (base_objects or {}).get(lvl))
        ]
        has_pack_changes = os.path.exists(os.path.join(pack_dir, "changes.json"))
        if dropped_levels:
            print(f"[geo-pack] WARNING: levels {dropped_levels} are not in the pack; levels are kept")

        if not (level_changes or unit_changes or retire or boundary_dirty):
            print(f"[geo-pack] geography: pack matches published version {base_no} — nothing to do")
            conn.rollback()
            return

        cur.execute("SELECT g2p_catalogue_next_geo_version()")
        new_no = cur.fetchone()[0]
        cur.execute(
            """INSERT INTO g2p_geo_versions (version_no, status, base_version_no, country, owner_org, change_note,
                   boundary_objects, boundary_checksums, created_by, created_at, updated_by, updated_at)
               SELECT %s, 'DRAFT', version_no, coalesce(country, %s), owner_org, %s, boundary_objects,
                      boundary_checksums, %s, now(), %s, now()
                 FROM g2p_geo_versions WHERE version_no = %s""",
            (new_no, country, f"Update from {pack_label}", args.actor, args.actor, base_no),
        )
        cur.execute(
            """INSERT INTO g2p_geo_version_levels
                 (version_no, level_id, level_mnemonic, parent_level_id, display, display_i18n)
               SELECT %s, level_id, level_mnemonic, parent_level_id, display, display_i18n
                 FROM g2p_geo_version_levels WHERE version_no = %s""",
            (new_no, base_no),
        )
        cur.execute(
            """INSERT INTO g2p_geo_version_units
                 (version_no, unit_id, level_id, name, name_i18n, parent_unit_id, status, valid_from, valid_to)
               SELECT %s, unit_id, level_id, name, name_i18n, parent_unit_id, status, valid_from, valid_to
                 FROM g2p_geo_version_units WHERE version_no = %s""",
            (new_no, base_no),
        )
        if level_changes:
            _insert_levels(cur, new_no, level_changes)
        _upsert_units(cur, new_no, unit_changes)
        if retire:
            cur.execute(
                "UPDATE g2p_geo_version_units SET status = 'RETIRED' WHERE version_no = %s AND unit_id = ANY(%s)",
                (new_no, retire),
            )
        # Lineage first (validated; may stop the load), boundaries after, so an
        # invalid changes.json uploads nothing.
        n_events = (
            _record_pack_changes(cur, pack_dir, new_no, args.actor, base_no, have_units) if has_pack_changes else 0
        )
        objects, sums, changed_levels = place_boundaries(
            cur, uploader, boundaries, country, new_no, base_objects, base_sums
        )
        cur.execute(
            "UPDATE g2p_geo_versions SET boundary_objects = %s, boundary_checksums = %s WHERE version_no = %s",
            (psycopg2.extras.Json(objects), psycopg2.extras.Json(sums), new_no),
        )
        summary = {
            "source": pack_label,
            "base_version_no": base_no,
            "levels_changed": sorted(level_changes),
            "units_added_or_changed": len(unit_changes),
            "units_retired": len(retire),
            "boundaries_changed": changed_levels,
            "pack_change_events": n_events,
        }
        log.log(cur, "geo.draft.created", "geo", "geography", new_no, summary)
        if args.publish:
            # Same lineage completion as the API's submit (explicit events above
            # were already validated with the API's rules).
            cur.execute("SELECT g2p_catalogue_geo_autolineage(%s, %s)", (new_no, args.actor))
            _auto_boundary_events(cur, new_no, base_sums, sums, args.actor)
            cur.execute("SELECT g2p_catalogue_publish_geo(%s, %s, NULL, %s, true)", (new_no, args.actor, pack_label))
            log.log(cur, "geo.version.published", "geo", "geography", new_no, {**summary, "auto_publish": True})
            print(f"[geo-pack] geography: version {new_no} published (--publish): {summary}")
        else:
            print(f"[geo-pack] geography: draft version {new_no} created for approval: {summary}")
        conn.commit()


def _auto_boundary_events(cur, version_no, before, after, actor):
    # A rename or a move says nothing about geometry; every other event already covers it.
    cur.execute(
        "SELECT from_units, to_units FROM g2p_geo_changes "
        "WHERE version_no = %s AND change_type NOT IN ('RENAME', 'REPARENT')",
        (version_no,),
    )
    covered = set()
    for f, t in cur.fetchall():
        covered.update(f or [])
        covered.update(t or [])
    for level, meta in (after or {}).items():
        old = ((before or {}).get(level) or {})
        if old.get("sha256") == meta.get("sha256"):
            continue
        changed = sorted(
            u for u, h in (meta.get("units") or {}).items()
            if u in (old.get("units") or {}) and old["units"][u] != h and u not in covered
        )
        if changed:
            cur.execute(
                """INSERT INTO g2p_geo_changes (version_no, change_type, from_units, to_units, note, is_auto,
                                                created_by, created_at)
                   VALUES (%s, 'BOUNDARY_CHANGE', %s, %s, %s, true, %s, now())""",
                (version_no, changed, changed, f"auto: {level} boundary changed", actor),
            )


# ---------------------------------------------------------------------------
# Code lists
# ---------------------------------------------------------------------------

def read_codelists(pack_dir, domains):
    """Every code list in the pack: the core set, plus the domains asked for.

    Domain lists are tagged with their domain so a registry can seed only what it
    serves — a social registry has no use for crop types. A requested domain the
    pack does not carry is skipped with a warning, not a failure: the chart asks
    for agriculture by default, and a pack without it should still load.
    """
    out = []
    core = os.path.join(pack_dir, "codelists")
    if os.path.isdir(core):
        for fn in sorted(f for f in os.listdir(core) if f.endswith(".json")):
            with open(os.path.join(core, fn)) as fh:
                out.append((None, json.load(fh)))
    for domain in domains:
        d = os.path.join(pack_dir, "domains", domain)
        if not os.path.isdir(d):
            pack = os.path.basename(os.path.normpath(pack_dir))
            print(f"[geo-pack] WARNING: domain '{domain}' not in pack {pack} — skipped")
            continue
        for fn in sorted(f for f in os.listdir(d) if f.endswith(".json")):
            with open(os.path.join(d, fn)) as fh:
                out.append((domain, json.load(fh)))
    return out



_VALUE_COLS = ("value_code", "display", "display_i18n", "parent_value_code", "sort_order", "attributes", "roles")
_META_COLS = ("list_code", "display", "display_i18n", "is_hierarchical", "attribute_schema")


def desired_list(doc):
    """(metadata, {value_id: value}) of one pack list, in catalogue shape."""
    meta = {
        "list_code": doc.get("attribute_code") or doc["attribute_id"],
        "display": doc.get("attribute_display"),
        "display_i18n": _norm(doc.get("attribute_display_i18n") or doc.get("display_i18n")),
        "is_hierarchical": bool(doc.get("is_hierarchical")),
        "attribute_schema": _norm(doc.get("attribute_schema")),
    }
    code_of = {v["value_id"]: (v.get("value_code") or v["value_id"]) for v in doc.get("values", [])}
    values = {}
    for v in doc.get("values", []):
        values[v["value_id"]] = {
            "value_code": v.get("value_code") or v["value_id"],
            "display": v.get("value_display"),
            "display_i18n": _norm(v.get("display_i18n")),
            "parent_value_code": code_of.get(v.get("parent_value_id")) if v.get("parent_value_id") else None,
            "sort_order": v.get("sort_order"),
            "attributes": _norm(v.get("attributes")),
            "roles": _norm(v.get("roles")),
        }
    return meta, values


def _upsert_values(cur, list_id, version_no, values):
    if not values:
        return
    psycopg2.extras.execute_values(
        cur,
        """INSERT INTO g2p_list_version_values
             (list_id, version_no, value_id, value_code, display, display_i18n, parent_value_code, sort_order,
              attributes, roles, status)
           VALUES %s
           ON CONFLICT (list_id, version_no, value_id) DO UPDATE
             SET value_code = EXCLUDED.value_code, display = EXCLUDED.display,
                 display_i18n = EXCLUDED.display_i18n, parent_value_code = EXCLUDED.parent_value_code,
                 sort_order = EXCLUDED.sort_order, attributes = EXCLUDED.attributes, roles = EXCLUDED.roles,
                 status = 'ACTIVE'""",
        [
            (list_id, version_no, vid, v["value_code"], v["display"], _jsonb(v["display_i18n"]),
             v["parent_value_code"], v["sort_order"], _jsonb(v["attributes"]), _jsonb(v["roles"]), "ACTIVE")
            for vid, v in values.items()
        ],
        page_size=500,
    )


def load_list(cur, doc, domain, args, log, pack_label):
    """Returns one of: created, published, draft, unchanged, skipped."""
    list_id = doc["attribute_id"]
    meta, values = desired_list(doc)
    cur.execute("SELECT attribute_id, description, owner_org, domain FROM g2p_attributes "
                "WHERE attribute_id = %s FOR UPDATE", (list_id,))
    row = cur.fetchone()
    note_suffix = f" ({domain})" if domain else ""
    # The list's domain for filtering in the UI: "core" for the pack's codelists/,
    # else the domains/<d>/ it came from. Administrative (g2p_attributes only),
    # never part of a version.
    list_domain = (domain or "core").strip().lower()

    if row is None:
        # ---- initial load of this list: version 1 ---------------------------------
        cur.execute(
            """INSERT INTO g2p_attributes (attribute_id, attribute_code, attribute_display, is_hierarchical,
                   display_i18n, attribute_schema, description, owner_org, domain, current_version_no)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NULL)""",
            (list_id, meta["list_code"], meta["display"], meta["is_hierarchical"], _jsonb(meta["display_i18n"]),
             _jsonb(meta["attribute_schema"]), doc.get("description"), doc.get("owner_org") or args.owner_org,
             list_domain),
        )
        # 1, unless a list with this id existed before and used numbers (never reused).
        cur.execute("SELECT g2p_catalogue_next_list_version(%s)", (list_id,))
        first = cur.fetchone()[0]
        cur.execute(
            """INSERT INTO g2p_list_versions (list_id, version_no, status, list_code, display, display_i18n,
                   is_hierarchical, attribute_schema, change_note, created_by, created_at, updated_by, updated_at)
               VALUES (%s, %s, 'DRAFT', %s, %s, %s, %s, %s, %s, %s, now(), %s, now())""",
            (list_id, first, meta["list_code"], meta["display"], _jsonb(meta["display_i18n"]),
             meta["is_hierarchical"], _jsonb(meta["attribute_schema"]),
             f"Initial load from {pack_label}{note_suffix}", args.actor, args.actor),
        )
        _upsert_values(cur, list_id, first, values)
        log.log(cur, "list.created", "list", list_id, None, {"list_code": meta["list_code"], "source": pack_label})
        log.log(cur, "list.draft.created", "list", list_id, first, {"values": len(values), "source": pack_label})
        if args.publish_initial:
            cur.execute("SELECT g2p_catalogue_publish_list(%s, %s, %s, NULL, %s, true)",
                        (list_id, first, args.actor, pack_label))
            log.log(cur, "list.version.published", "list", list_id, first,
                    {"list_code": meta["list_code"], "initial": True, "source": pack_label})
            return "created"
        return "draft"

    # Administrative fields the pack may carry are applied directly (not versioned).
    if doc.get("description") and doc.get("description") != row[1]:
        cur.execute("UPDATE g2p_attributes SET description = %s WHERE attribute_id = %s", (doc["description"], list_id))
    if doc.get("owner_org") and doc.get("owner_org") != row[2]:
        cur.execute("UPDATE g2p_attributes SET owner_org = %s WHERE attribute_id = %s", (doc["owner_org"], list_id))
    # Fill the domain of a list loaded before the column existed; one already set
    # (by an earlier load or by a maker) is kept.
    if not (row[3] or "").strip():
        cur.execute("UPDATE g2p_attributes SET domain = %s WHERE attribute_id = %s", (list_domain, list_id))

    cur.execute(
        "SELECT version_no, status FROM g2p_list_versions WHERE list_id = %s AND status IN ('DRAFT', 'SUBMITTED')",
        (list_id,),
    )
    open_row = cur.fetchone()
    if open_row:
        print(f"[geo-pack]   {list_id}: version {open_row[0]} is open ({open_row[1]}); not touching it")
        return "skipped"
    cur.execute("SELECT max(version_no) FROM g2p_list_versions WHERE list_id = %s AND status = 'PUBLISHED'",
                (list_id,))
    base_no = cur.fetchone()[0]
    if base_no is None:
        print(f"[geo-pack]   {list_id}: exists but has no published version; not touching it")
        return "skipped"

    # ---- later load: compare with the highest published version -----------------
    cur.execute(
        f"SELECT {', '.join(_META_COLS)} FROM g2p_list_versions WHERE list_id = %s AND version_no = %s",
        (list_id, base_no),
    )
    have_meta = dict(zip(_META_COLS, cur.fetchone()))
    have_meta = {k: (_norm(v) if k != "is_hierarchical" else bool(v)) for k, v in have_meta.items()}
    cur.execute(
        f"SELECT value_id, status, {', '.join(_VALUE_COLS)} FROM g2p_list_version_values "
        "WHERE list_id = %s AND version_no = %s",
        (list_id, base_no),
    )
    have = {}
    for r in cur.fetchall():
        have[r[0]] = {"status": r[1], **{k: _norm(v) for k, v in zip(_VALUE_COLS, r[2:])}}
    want_meta = {k: (_norm(v) if k != "is_hierarchical" else bool(v)) for k, v in meta.items()}
    meta_changed = {k for k in _META_COLS if want_meta[k] != have_meta[k]}
    changed = {
        vid: v for vid, v in values.items()
        if vid not in have or have[vid]["status"] != "ACTIVE"
        or any(_norm(v[k]) != have[vid][k] for k in _VALUE_COLS)
    }
    retire = sorted(vid for vid, h in have.items() if h["status"] == "ACTIVE" and vid not in values)
    if not (meta_changed or changed or retire):
        return "unchanged"

    cur.execute("SELECT g2p_catalogue_next_list_version(%s)", (list_id,))
    new_no = cur.fetchone()[0]
    cur.execute(
        """INSERT INTO g2p_list_versions (list_id, version_no, status, base_version_no, list_code, display,
               display_i18n, is_hierarchical, attribute_schema, change_note, created_by, created_at, updated_by,
               updated_at)
           VALUES (%s, %s, 'DRAFT', %s, %s, %s, %s, %s, %s, %s, %s, now(), %s, now())""",
        (list_id, new_no, base_no, meta["list_code"], meta["display"], _jsonb(meta["display_i18n"]),
         meta["is_hierarchical"], _jsonb(meta["attribute_schema"]), f"Update from {pack_label}{note_suffix}",
         args.actor, args.actor),
    )
    cur.execute(
        """INSERT INTO g2p_list_version_values (list_id, version_no, value_id, value_code, display, display_i18n,
               parent_value_code, sort_order, attributes, roles, status)
           SELECT list_id, %s, value_id, value_code, display, display_i18n, parent_value_code, sort_order,
                  attributes, roles, status
             FROM g2p_list_version_values WHERE list_id = %s AND version_no = %s""",
        (new_no, list_id, base_no),
    )
    _upsert_values(cur, list_id, new_no, changed)
    if retire:
        cur.execute(
            "UPDATE g2p_list_version_values SET status = 'RETIRED' "
            "WHERE list_id = %s AND version_no = %s AND value_id = ANY(%s)",
            (list_id, new_no, retire),
        )
    summary = {
        "source": pack_label,
        "base_version_no": base_no,
        "metadata_changed": sorted(meta_changed),
        "values_added_or_changed": sorted(changed)[:200],
        "values_retired": retire[:200],
    }
    log.log(cur, "list.draft.created", "list", list_id, new_no, summary)
    if args.publish:
        cur.execute("SELECT g2p_catalogue_publish_list(%s, %s, %s, NULL, %s, true)",
                    (list_id, new_no, args.actor, pack_label))
        log.log(cur, "list.version.published", "list", list_id, new_no, {**summary, "auto_publish": True})
        return "published"
    return "draft"


def load_codelists(conn, pack_dir, manifest, domains, args, log):
    lists = read_codelists(pack_dir, domains)
    if not lists:
        print("[geo-pack] no codelists in this pack — nothing to seed")
        return
    pack_label = f"country pack {args.country} ({manifest.get('version') or manifest.get('fetched_on') or '-'})"
    tally = {}
    with conn.cursor() as cur:
        for domain, doc in lists:
            outcome = load_list(cur, doc, domain, args, log, pack_label)
            tally.setdefault(outcome, []).append(doc["attribute_id"])
    conn.commit()
    for outcome in ("created", "published", "draft", "unchanged", "skipped"):
        ids = tally.get(outcome) or []
        if ids:
            label = {
                "created": "published as version 1",
                "published": "new version published (--publish)",
                "draft": "draft created for approval",
                "unchanged": "unchanged",
                "skipped": "skipped (open draft / unpublished)",
            }[outcome]
            shown = ", ".join(ids[:8]) + (f" … (+{len(ids) - 8})" if len(ids) > 8 else "")
            print(f"[geo-pack] codelists {label}: {len(ids)} — {shown}")


def version_legacy_lists(conn, actor):
    """Version anything the SQL fixtures put straight into the legacy tables, then
    re-materialise every published list so the legacy rows equal the published
    versions again (a fixture can only ever ADD rows, but it must not be able to
    resurrect a value the catalogue retired)."""
    with conn.cursor() as cur:
        cur.execute("SELECT g2p_catalogue_bootstrap_v1(%s)", (actor,))
        summary = cur.fetchone()[0]
        cur.execute(
            "SELECT count(g2p_catalogue_materialise_list(attribute_id)) FROM g2p_attributes "
            "WHERE current_version_no IS NOT NULL"
        )
    conn.commit()
    if summary and summary.get("lists"):
        print(f"[geo-pack] SQL fixture lists versioned as version 1: {summary['lists']}")


def seed_sql_codelists(conn, domains):
    """Fill lists the pack does not define, from remaining scripts/seed-data SQL.

    Pack JSON is loaded first. SQL uses ON CONFLICT DO NOTHING so it only
    inserts lists the pack omitted (e.g. social PRIMARY_LIVELIHOOD).
    """
    root = os.environ.get("CODELISTS_SQL_DIR", "/seed/codelists")
    if not os.path.isdir(root):
        print("[geo-pack] no SQL codelist fixtures found — skipping")
        return
    wanted = [d for d in domains if d]
    applied = []
    with conn.cursor() as cur:
        for domain in wanted:
            d = os.path.join(root, domain)
            if not os.path.isdir(d):
                print(f"[geo-pack] no SQL codelist fixtures for domain '{domain}' — skipped")
                continue
            cur.execute("SELECT attribute_id FROM g2p_attributes")
            before = [r[0] for r in cur.fetchall()]
            for fn in ("g2p_attributes.sql", "g2p_attribute_values.sql"):
                path = os.path.join(d, fn)
                if not os.path.exists(path):
                    continue
                with open(path) as fh:
                    cur.execute(fh.read())
                applied.append(f"{domain}/{fn}")
            # Lists this domain's fixtures just added belong to that domain.
            cur.execute(
                "UPDATE g2p_attributes SET domain = %s "
                "WHERE coalesce(domain, '') = '' AND NOT (attribute_id = ANY(%s))",
                (domain.strip().lower(), before),
            )
    conn.commit()
    if applied:
        print(f"[geo-pack] sql codelist fixtures: {', '.join(applied)}")
    else:
        print("[geo-pack] no SQL codelist fixtures found — skipping")



def _clean_id(value):
    """Normalise a foundational ID to its digits-and-letters form.

    Packs write national IDs in a human-readable grouped form ("4028 6914
    8701"). That string is copied verbatim into every downstream system --
    registries store it as `foundational_id`, and the mock identity system
    stores it as `individualId` -- and eSignet then matches it EXACTLY. So an
    operator who types the ID the way it is printed on a card, without the
    grouping, gets "invalid_individual_id" and no indication why.

    Stripping whitespace once here, at the point the pack is read, is what
    keeps the registry and the ID system agreeing on the same string.
    """
    if not isinstance(value, str):
        return value
    return "".join(value.split()) or None


SAMPLE_INDIVIDUAL_COLS = [
    "individual_id", "household_id", "given_name", "fathers_name", "full_name",
    "gender", "relationship_to_head", "marital_status", "education_level",
    "employment_status", "disability_status", "birth_date", "birth_year", "age", "phone",
    "national_id", "geo_pcode", "address_parts", "latitude", "longitude",
    "country", "version",
]
SAMPLE_HOUSEHOLD_COLS = [
    "household_id", "head_individual_id", "headship_type", "size_total",
    "dwelling_type", "tenure_status", "water_source_type", "sanitation_type",
    "lighting_source", "cooking_fuel_type", "geo_pcode", "address_parts",
    "latitude", "longitude", "country", "version",
]


def seed_samples(conn, pack_dir, manifest):
    """Upsert the pack's sample people.

    Sample data is the one demo data that has to be country-coherent — a
    reviewer reads the names — so it belongs beside the geography it references,
    in the one place the country is declared. Registries copy these and add their
    own fields, which is how one set of people populates a social registry and a
    farmer registry as the same people.

    Only the columns the model declares are taken. A pack may carry extra keys
    for a registry that wants them; silently widening this table to match would
    make the pack's shape and the table's shape the same thing, and then adding a
    key to a pack would be a schema migration.
    """
    d = os.path.join(pack_dir, "samples")
    if not os.path.isdir(d):
        print("[geo-pack] no samples/ in this pack — nothing to seed")
        return
    country = manifest.get("country")
    version = (manifest.get("version") or manifest.get("upstream_last_modified")
               or manifest.get("fetched_on"))

    def rows_for(fname, cols):
        path = os.path.join(d, fname)
        if not os.path.exists(path):
            return []
        with open(path) as fh:
            docs = json.load(fh)
        out = []
        for rec in docs:
            row = []
            for c in cols:
                if c == "country":
                    row.append(country)
                elif c == "version":
                    row.append(version)
                elif c == "address_parts":
                    row.append(json.dumps(rec.get("address_parts") or {}))
                elif c == "national_id":
                    row.append(_clean_id(rec.get(c)))
                else:
                    row.append(rec.get(c))
            out.append(tuple(row))
        return out

    inds = rows_for("individuals.json", SAMPLE_INDIVIDUAL_COLS)
    hhs = rows_for("households.json", SAMPLE_HOUSEHOLD_COLS)

    # The API creates these tables with SQLAlchemy's create_all, which creates a
    # MISSING table and never adds a column to one that already exists. So on any
    # environment seeded before birth_date was introduced the column is simply
    # absent, and the insert below fails on a column list that looks correct.
    #
    # Adding it here rather than in a migration keeps the seed job self-sufficient
    # and idempotent: IF NOT EXISTS makes the second run a no-op.
    with conn.cursor() as cur:
        cur.execute("ALTER TABLE g2p_sample_individuals "
                    "ADD COLUMN IF NOT EXISTS birth_date date")
    conn.commit()

    # Households first: an individual references one, and seeding the other way
    # round leaves a window where the reference dangles.
    with conn.cursor() as cur:
        if hhs:
            psycopg2.extras.execute_values(cur, f"""
                INSERT INTO g2p_sample_households ({", ".join(SAMPLE_HOUSEHOLD_COLS)})
                VALUES %s
                ON CONFLICT (household_id) DO UPDATE SET
                  {", ".join(f"{c} = EXCLUDED.{c}" for c in SAMPLE_HOUSEHOLD_COLS[1:])}
            """, hhs)
        if inds:
            psycopg2.extras.execute_values(cur, f"""
                INSERT INTO g2p_sample_individuals ({", ".join(SAMPLE_INDIVIDUAL_COLS)})
                VALUES %s
                ON CONFLICT (individual_id) DO UPDATE SET
                  {", ".join(f"{c} = EXCLUDED.{c}" for c in SAMPLE_INDIVIDUAL_COLS[1:])}
            """, inds)
    conn.commit()

    # A sample sitting on a P-code this pack does not contain would load fine and
    # then fail to join to anything, so check rather than assume.
    with conn.cursor() as cur:
        cur.execute("""
            select count(*) from g2p_sample_individuals s
             where s.geo_pcode is not null
               and not exists (select 1 from g2p_geo_level_values v
                                where v.level_value_id = s.geo_pcode)
        """)
        orphan = cur.fetchone()[0]
    print(f"[geo-pack] samples: {len(hhs)} households, {len(inds)} individuals")
    if orphan:
        print(f"[geo-pack]   WARNING: {orphan} sample individual(s) sit on a P-code "
              f"not present in g2p_geo_level_values — load geo too, or check the pack")



def _env_flag(name, default):
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--pack", required=True, help="country pack directory")
    p.add_argument("--country", default=None,
                   help="country code for object-storage paths (defaults to the "
                        "pack manifest)")
    p.add_argument("--db", default=os.environ.get("MDS_DB", "master_data"))
    p.add_argument("--s3-endpoint", default=os.environ.get("S3_ENDPOINT"),
                   help="e.g. http://commons-minio:9000; omit to skip uploading")
    p.add_argument("--s3-bucket", default=os.environ.get("S3_BUCKET", "openg2p-geo"))
    p.add_argument("--boundary-base-url", default=os.environ.get("BOUNDARY_BASE_URL"),
                   help="public base URL boundaries are served from")
    # What to load. The script keeps its name: the chart's Job invokes
    # load_geo_pack.py by path.
    p.add_argument("--load", default=os.environ.get("PACK_LOAD", "geo"),
                   help="comma-separated: geo,codelists,samples (default: geo)")
    p.add_argument("--domains", default=os.environ.get("PACK_DOMAINS", ""),
                   help="comma-separated domain subtrees to load with codelists, "
                        "e.g. agriculture. Empty loads the core lists only; a "
                        "domain the pack lacks is skipped with a warning.")
    p.add_argument("--publish-initial", dest="publish_initial", action="store_true",
                   default=_env_flag("PACK_PUBLISH_INITIAL", True),
                   help="publish version 1 of a list / the geography directly on its first "
                        "load (default on)")
    p.add_argument("--no-publish-initial", dest="publish_initial", action="store_false",
                   help="leave even the first load as a draft for approval")
    p.add_argument("--publish", action="store_true", default=_env_flag("PACK_AUTO_PUBLISH", False),
                   help="DEVELOPMENT ONLY: publish the drafts a later load creates, without approval")
    p.add_argument("--actor", default=os.environ.get("PACK_ACTOR", ACTOR_DEFAULT),
                   help="who the change log records as the author")
    p.add_argument("--owner-org", default=os.environ.get("PACK_OWNER_ORG") or None,
                   help="owner (department) recorded on lists and geography created by this load")
    p.add_argument("--purge", action="store_true",
                   help="DEPRECATED, now a no-op on catalogue data: published versions are "
                        "immutable. Re-materialises the legacy geo tables from the current "
                        "published version instead.")
    args = p.parse_args()

    levels, values, manifest = load_pack(args.pack)
    args.country = args.country or manifest.get("country", "XXX")

    print(f"[geo-pack] {manifest.get('source_title') or args.country}")
    print(f"[geo-pack] source={manifest.get('source')} license={manifest.get('license')}")
    if manifest.get("synthetic"):
        print("[geo-pack] this is a SYNTHETIC pack — the country is fictitious")
    if manifest.get("license_note"):
        print(f"[geo-pack] {manifest['license_note']}")
    print(f"[geo-pack] levels={manifest.get('levels')} units={len(values)}")
    if args.publish:
        print("[geo-pack] --publish: drafts created by this run are PUBLISHED without approval")

    conn = psycopg2.connect(
        dbname=args.db,
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
        user=os.environ.get("PGUSER", "postgres"),
        password=os.environ.get("PGPASSWORD", ""),
    )
    require_catalogue_schema(conn)
    log = ChangeLog(args.actor)

    # Anything still unversioned (pre-catalogue data the API has not migrated yet).
    with conn.cursor() as cur:
        cur.execute("SELECT g2p_catalogue_bootstrap_v1(%s)", ("migration",))
    conn.commit()

    if args.purge:
        with conn.cursor() as cur:
            cur.execute("SELECT g2p_catalogue_materialise_geo()")
        conn.commit()
        print("[geo-pack] --purge is deprecated: published geography is immutable; legacy geo tables "
              "re-materialised from the current published version")

    wanted = {w.strip() for w in args.load.split(",") if w.strip()}
    unknown = wanted - {"geo", "codelists", "samples"}
    if unknown:
        raise SystemExit(f"--load: unknown section(s) {sorted(unknown)}")

    if "geo" in wanted:
        uploader = BoundaryUploader(args)
        load_geo(conn, args.pack, levels, values, manifest, args, uploader, log)
    else:
        print("[geo-pack] geo not requested — skipping")

    if "codelists" in wanted:
        domains = [d.strip() for d in args.domains.split(",") if d.strip()]
        load_codelists(conn, args.pack, manifest, domains, args, log)
        seed_sql_codelists(conn, domains)
        version_legacy_lists(conn, args.actor)

    if "samples" in wanted:
        seed_samples(conn, args.pack, manifest)

    with conn.cursor() as cur:
        cur.execute("SELECT int_value FROM g2p_catalogue_state WHERE key = 'geo.current_version_no'")
        row = cur.fetchone()
        print(f"[geo-pack] geography version in effect: {row[0] if row else '-'}")
        cur.execute("select level_id, count(*) from g2p_geo_level_values"
                    " group by level_id order by level_id")
        for lid, n in cur.fetchall():
            print(f"[geo-pack]   {lid}  {n:>6} units")
    print("[geo-pack] done")


if __name__ == "__main__":
    main()
