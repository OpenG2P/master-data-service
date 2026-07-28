#!/usr/bin/env python3
"""Seed the Master Data Service geo hierarchy from a country pack.

    python load_geo_pack.py --pack /openg2p-data/geo/packs/ETH

Why this lives in MDS
---------------------
MDS owns geography. Until now the only geo loader in the platform shipped with
the *registry* db-seed image, which meant master data was populated as a side
effect of installing a registry — anything else needing MDS geo depended on a
registry install having happened first. This moves that ownership where it
belongs, and MDS seeds its own data at its own install.

Idempotent by P-code
--------------------
The pack uses the P-code as `level_value_id`, so re-running upserts in place
rather than duplicating. That makes this safe as a post-install/post-upgrade
hook, and it makes a pack refresh (a new COD-AB release) a re-run rather than a
migration.

Boundaries
----------
Simplified GeoJSON is optionally uploaded to object storage and the resulting
URL recorded in `boundary_simplified_uri`. Geometry deliberately does not go
into Postgres rows: it is bulk binary that only ever gets served as files, and
inlining it would bloat every query that touches the table.
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


def seed(conn, levels, values, manifest, boundary_urls, args):
    version = manifest.get("upstream_last_modified") or manifest.get("fetched_on")
    level_name = {lv["level_id"]: lv["level_mnemonic"] for lv in levels}

    with conn.cursor() as cur:
        cur.execute("select column_name from information_schema.columns"
                    " where table_name='g2p_geo_level_values'")
        cols = {r[0] for r in cur.fetchall()}
        # The pcode/boundary columns arrive in migration 001. Without them this
        # still seeds a usable hierarchy rather than failing outright.
        extended = {"pcode", "boundary_simplified_uri", "version"} <= cols
        if not extended:
            print("[geo-pack] NOTE: pcode/boundary columns absent — apply migration "
                  "001_geo_pcode_boundaries.sql to store P-codes and boundary URIs")

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

        if extended:
            sql = """
                INSERT INTO g2p_geo_level_values
                  (level_value_id, level_id, level_value_mnemonic, parent_level_value_id,
                   pcode, pcode_source, display_name, boundary_simplified_uri, version)
                VALUES %s
                ON CONFLICT (level_value_id) DO UPDATE
                  SET level_id = EXCLUDED.level_id,
                      level_value_mnemonic = EXCLUDED.level_value_mnemonic,
                      parent_level_value_id = EXCLUDED.parent_level_value_id,
                      pcode = EXCLUDED.pcode,
                      pcode_source = EXCLUDED.pcode_source,
                      display_name = EXCLUDED.display_name,
                      boundary_simplified_uri = EXCLUDED.boundary_simplified_uri,
                      version = EXCLUDED.version
            """
            rows = [(
                v["level_value_id"], v["level_id"], v["level_value_mnemonic"],
                v["parent_level_value_id"], v.get("pcode"), v.get("pcode_source"),
                v.get("display_name"),
                boundary_urls.get(level_name.get(v["level_id"], "")),
                version,
            ) for v in values]
        else:
            sql = """
                INSERT INTO g2p_geo_level_values
                  (level_value_id, level_id, level_value_mnemonic, parent_level_value_id)
                VALUES %s
                ON CONFLICT (level_value_id) DO UPDATE
                  SET level_id = EXCLUDED.level_id,
                      level_value_mnemonic = EXCLUDED.level_value_mnemonic,
                      parent_level_value_id = EXCLUDED.parent_level_value_id
            """
            rows = [(v["level_value_id"], v["level_id"], v["level_value_mnemonic"],
                     v["parent_level_value_id"]) for v in values]

        psycopg2.extras.execute_values(cur, sql, rows, page_size=500)
    conn.commit()


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
    p.add_argument("--purge", action="store_true",
                   help="delete all geo rows before seeding")
    args = p.parse_args()

    levels, values, manifest = load_pack(args.pack)
    args.country = args.country or manifest.get("country", "XXX")

    print(f"[geo-pack] {manifest.get('source_title') or args.country}")
    print(f"[geo-pack] source={manifest.get('source')} license={manifest.get('license')}")
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

    boundary_urls = upload_boundaries(args.pack, manifest, args)
    seed(conn, levels, values, manifest, boundary_urls, args)

    with conn.cursor() as cur:
        cur.execute("select level_id, count(*) from g2p_geo_level_values"
                    " group by level_id order by level_id")
        for lid, n in cur.fetchall():
            print(f"[geo-pack]   {lid}  {n:>6} units")
    print("[geo-pack] done")


if __name__ == "__main__":
    main()
