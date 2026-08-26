#!/usr/bin/env python3
"""Seed the Master Data Service geo hierarchy from a country pack.

    python load_geo_pack.py --pack /openg2p-data/packs/XKM

Why this lives in MDS
---------------------
MDS owns geography. Until now the only geo loader in the platform shipped with
the *registry* db-seed image, which meant master data was populated as a side
effect of installing a registry — anything else needing MDS geo depended on a
registry install having happened first. This moves that ownership where it
belongs, and MDS seeds its own data at its own install.

Idempotent on level_value_id
----------------------------
The pack uses a stable id as `level_value_id`, so re-running upserts in place
rather than duplicating. That makes this safe as a post-install/post-upgrade
hook, and it makes a pack refresh a re-run rather than a migration.

Pack-flavour agnostic
---------------------
This reads nothing but levels.json, values.json, manifest.json and
optionally pack codelists, so it cannot tell a real country pack from a
synthetic one — which is the point. Switching an environment between Ethiopia
and the fictitious Kamuntu is a `countryPack` value change, not a code change.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys

import psycopg2
import psycopg2.extras


def load_pack(pack_dir):
    def read(name):
        path = os.path.join(pack_dir, name)
        if not os.path.exists(path):
            raise SystemExit(f"pack is missing {name} — is {pack_dir} a country pack?")
        with open(path) as fh:
            return json.load(fh)

    return read("levels.json"), read("values.json"), read("manifest.json")


def upload_boundaries(pack_dir, manifest, args):
    """Push simplified GeoJSON to S3/MinIO; return {level_name: url}.

    Returns plain URLs built from --boundary-base-url when uploading is not
    configured, so a deployment that serves the pack some other way (a mounted
    volume, a CDN, Evidence baking them at build time) still gets usable URIs.
    """
    bdir = os.path.join(pack_dir, "boundaries")
    if not os.path.isdir(bdir):
        return {}
    files = sorted(f for f in os.listdir(bdir) if f.endswith(".geojson"))
    urls = {}

    if not args.s3_endpoint:
        for f in files:
            level = f[: -len(".geojson")]
            base = (args.boundary_base_url or "").rstrip("/")
            urls[level] = f"{base}/{args.country}/boundaries/{f}" if base else None
        if any(urls.values()):
            print(f"[geo-pack] recording {len(urls)} boundary URLs (no upload configured)")
        return urls

    try:
        import boto3
    except ImportError:
        print("[geo-pack] boto3 not installed — skipping upload, recording URLs only",
              file=sys.stderr)
        args.s3_endpoint = None
        return upload_boundaries(pack_dir, manifest, args)

    s3 = boto3.client(
        "s3",
        endpoint_url=args.s3_endpoint,
        aws_access_key_id=os.environ.get("S3_ACCESS_KEY"),
        aws_secret_access_key=os.environ.get("S3_SECRET_KEY"),
        region_name=os.environ.get("S3_REGION", "us-east-1"),
    )
    try:
        s3.head_bucket(Bucket=args.s3_bucket)
    except Exception:
        s3.create_bucket(Bucket=args.s3_bucket)
        print(f"[geo-pack] created bucket {args.s3_bucket}")

    for f in files:
        level = f[: -len(".geojson")]
        key = f"geo/{args.country}/boundaries/{f}"
        ctype = mimetypes.guess_type(f)[0] or "application/geo+json"
        with open(os.path.join(bdir, f), "rb") as fh:
            s3.put_object(Bucket=args.s3_bucket, Key=key, Body=fh, ContentType=ctype)
        base = (args.boundary_base_url or args.s3_endpoint).rstrip("/")
        urls[level] = f"{base}/{args.s3_bucket}/{key}"
        print(f"[geo-pack] uploaded {key}")
    return urls


def seed(conn, levels, values, manifest, args):
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO g2p_geo_levels (level_id, level_mnemonic, parent_level_id)
            VALUES %s
            ON CONFLICT (level_id) DO UPDATE
              SET level_mnemonic = EXCLUDED.level_mnemonic,
                  parent_level_id = EXCLUDED.parent_level_id
            """,
            [(lv["level_id"], lv["level_mnemonic"], lv["parent_level_id"]) for lv in levels],
        )

        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO g2p_geo_level_values
              (level_value_id, level_id, level_value_mnemonic, parent_level_value_id)
            VALUES %s
            ON CONFLICT (level_value_id) DO UPDATE
              SET level_id = EXCLUDED.level_id,
                  level_value_mnemonic = EXCLUDED.level_value_mnemonic,
                  parent_level_value_id = EXCLUDED.parent_level_value_id
            """,
            [
                (
                    v["level_value_id"],
                    v["level_id"],
                    v["level_value_mnemonic"],
                    v["parent_level_value_id"],
                )
                for v in values
            ],
            page_size=500,
        )
    conn.commit()


def read_codelists(pack_dir, domains):
    """Every code list in the pack: the core set, plus the domains asked for.

    Domain lists are tagged with their domain so a registry can seed only what it
    serves — a social registry has no use for crop types.
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
            raise SystemExit(f"--domains names '{domain}', which is not in this pack")
        for fn in sorted(f for f in os.listdir(d) if f.endswith(".json")):
            with open(os.path.join(d, fn)) as fh:
                out.append((domain, json.load(fh)))
    return out


def seed_codelists(conn, pack_dir, manifest, domains):
    """Upsert the pack's code lists, idempotent on the natural keys.

    Same shape as the geo seed: re-running refreshes in place rather than
    duplicating, so this is safe as a post-install/post-upgrade hook.
    """
    lists = read_codelists(pack_dir, domains)
    if not lists:
        print("[geo-pack] no codelists in this pack — nothing to seed")
        return

    attrs, vals = [], []
    for domain, doc in lists:
        attrs.append((doc["attribute_id"], doc.get("attribute_code"),
                      doc.get("attribute_display"), bool(doc.get("is_hierarchical"))))
        for v in doc.get("values", []):
            vals.append((
                v["value_id"], doc["attribute_id"], v.get("value_code"),
                v.get("value_display"), v.get("parent_value_id"), v.get("sort_order"),
            ))

    with conn.cursor() as cur:
        psycopg2.extras.execute_values(cur, """
            INSERT INTO g2p_attributes
              (attribute_id, attribute_code, attribute_display, is_hierarchical)
            VALUES %s
            ON CONFLICT (attribute_id) DO UPDATE
              SET attribute_code = EXCLUDED.attribute_code,
                  attribute_display = EXCLUDED.attribute_display,
                  is_hierarchical = EXCLUDED.is_hierarchical
        """, attrs)
        psycopg2.extras.execute_values(cur, """
            INSERT INTO g2p_attribute_values
              (value_id, attribute_id, value_code, value_display, parent_value_id,
               sort_order)
            VALUES %s
            ON CONFLICT (attribute_id, value_id) DO UPDATE
              SET value_code = EXCLUDED.value_code,
                  value_display = EXCLUDED.value_display,
                  parent_value_id = EXCLUDED.parent_value_id,
                  sort_order = EXCLUDED.sort_order
        """, vals, page_size=500)
    conn.commit()
    print(f"[geo-pack] codelists: {len(attrs)} attributes, {len(vals)} values")


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
                continue
            for fn in ("g2p_attributes.sql", "g2p_attribute_values.sql"):
                path = os.path.join(d, fn)
                if not os.path.exists(path):
                    continue
                with open(path) as fh:
                    cur.execute(fh.read())
                applied.append(f"{domain}/{fn}")
    conn.commit()
    if applied:
        print(f"[geo-pack] sql codelist fixtures: {', '.join(applied)}")
    else:
        print("[geo-pack] no SQL codelist fixtures found — skipping")



SAMPLE_INDIVIDUAL_COLS = [
    "individual_id", "household_id", "given_name", "fathers_name", "full_name",
    "gender", "relationship_to_head", "marital_status", "education_level",
    "employment_status", "disability_status", "birth_year", "age", "phone",
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
                else:
                    row.append(rec.get(c))
            out.append(tuple(row))
        return out

    inds = rows_for("individuals.json", SAMPLE_INDIVIDUAL_COLS)
    hhs = rows_for("households.json", SAMPLE_HOUSEHOLD_COLS)

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
    # What to load. Defaults to "geo" — byte-for-byte today's behaviour, so an
    # existing deployment upgrading this image sees no change at all. The rest of
    # the pack is opt-in.
    #
    # The script keeps its name for the same reason: the chart's Job invokes
    # load_geo_pack.py by path, and renaming it to load_country_pack.py would
    # break every deployed release.
    p.add_argument("--load", default=os.environ.get("PACK_LOAD", "geo"),
                   help="comma-separated: geo,codelists,samples (default: geo)")
    p.add_argument("--domains", default=os.environ.get("PACK_DOMAINS", ""),
                   help="comma-separated domain subtrees to load with codelists, "
                        "e.g. agriculture. Empty loads the core lists only.")
    p.add_argument("--purge", action="store_true",
                   help="delete all geo rows before seeding")
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

    conn = psycopg2.connect(
        dbname=args.db,
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
        user=os.environ.get("PGUSER", "postgres"),
        password=os.environ.get("PGPASSWORD", ""),
    )

    if args.purge:
        with conn.cursor() as cur:
            cur.execute("delete from g2p_geo_level_values")
            cur.execute("delete from g2p_geo_levels")
        conn.commit()
        print("[geo-pack] purged existing geo")

    wanted = {w.strip() for w in args.load.split(",") if w.strip()}
    unknown = wanted - {"geo", "codelists", "samples"}
    if unknown:
        raise SystemExit(f"--load: unknown section(s) {sorted(unknown)}")

    if "geo" in wanted:
        seed(conn, levels, values, manifest, args)
    else:
        print("[geo-pack] geo not requested — skipping")

    if "codelists" in wanted:
        domains = [d.strip() for d in args.domains.split(",") if d.strip()]
        seed_codelists(conn, args.pack, manifest, domains)
        seed_sql_codelists(conn, domains)

    if "samples" in wanted:
        seed_samples(conn, args.pack, manifest)

    with conn.cursor() as cur:
        cur.execute("select level_id, count(*) from g2p_geo_level_values"
                    " group by level_id order by level_id")
        for lid, n in cur.fetchall():
            print(f"[geo-pack]   {lid}  {n:>6} units")
    print("[geo-pack] done")


if __name__ == "__main__":
    main()
