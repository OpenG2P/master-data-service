#!/usr/bin/env python3
"""Load geo reference data into the Master Data Postgres.

Reads a single flat, human-readable CSV from the openg2p-data repo (cloned into
the image):
- /openg2p-data/geo/geo.csv  (columns: country,region,district,ward,village)

The CSV has NO ids — one row per village with its parent names denormalized. This
loader derives the hierarchy and stable slug-path ids (e.g.
"kamuntu/kilima/karamu/uzima/billyu") and populates:
- g2p_geo_levels        (l0..l4 = country..village, with parent links)
- g2p_geo_level_values  (one row per distinct node, keyed by its path id)

Names are not unique (villages/wards repeat), so the unique key is the path id, not
the mnemonic. Inserts use ON CONFLICT DO NOTHING on the primary key, so re-running
(e.g. on a Helm post-upgrade hook) is idempotent.
"""

import csv
import os
import sys
from pathlib import Path

import psycopg2

OPENG2P_DATA_DIR = Path(os.environ.get("OPENG2P_DATA_DIR", "/openg2p-data"))
GEO_FILE = OPENG2P_DATA_DIR / "geo" / "geo.csv"

# Ordered geo levels, matching the columns of geo.csv (root -> leaf).
GEO_LEVELS = ["country", "region", "district", "ward", "village"]


def env(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        print(f"[load-geo-data] Missing env var: {name}", file=sys.stderr)
        sys.exit(1)
    return value


def _slug(name: str) -> str:
    return name.strip().lower().replace(" ", "_")


def _path_id(names: list) -> str:
    return "/".join(_slug(n) for n in names)


def _read_geo():
    """Parse geo.csv -> (level_rows, value_rows).

    level_rows: [{level_id, level_mnemonic, parent_level_id}]  (l0..l4)
    value_rows: [{level_value_id, level_id, level_value_mnemonic,
                  parent_level_value_id}]  (distinct nodes, parent-first)
    """
    if not GEO_FILE.is_file():
        print(f"[load-geo-data] Missing file: {GEO_FILE}", file=sys.stderr)
        sys.exit(1)

    level_rows = [
        {
            "level_id": f"l{depth}",
            "level_mnemonic": level_name,
            "parent_level_id": f"l{depth - 1}" if depth > 0 else None,
        }
        for depth, level_name in enumerate(GEO_LEVELS)
    ]

    # Insertion order preserves parent-first ordering per row; dedupe by path id.
    values: dict = {}
    with GEO_FILE.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            names = [row[level] for level in GEO_LEVELS]
            parent_id = None
            for depth, level_name in enumerate(GEO_LEVELS):
                node_id = _path_id(names[: depth + 1])
                if node_id not in values:
                    values[node_id] = {
                        "level_value_id": node_id,
                        "level_id": f"l{depth}",
                        "level_value_mnemonic": names[depth],
                        "parent_level_value_id": parent_id,
                    }
                parent_id = node_id

    return level_rows, list(values.values())


def insert_geo_levels(cur, rows: list) -> int:
    for r in rows:
        cur.execute(
            """
            INSERT INTO g2p_geo_levels (level_id, level_mnemonic, parent_level_id)
            VALUES (%(level_id)s, %(level_mnemonic)s, %(parent_level_id)s)
            ON CONFLICT (level_id) DO NOTHING
            """,
            r,
        )
    return len(rows)


def insert_geo_level_values(cur, rows: list) -> int:
    for r in rows:
        cur.execute(
            """
            INSERT INTO g2p_geo_level_values
                (level_value_id, level_id, level_value_mnemonic, parent_level_value_id)
            VALUES
                (%(level_value_id)s, %(level_id)s, %(level_value_mnemonic)s, %(parent_level_value_id)s)
            ON CONFLICT (level_value_id) DO NOTHING
            """,
            r,
        )
    return len(rows)


def main() -> None:
    levels, values = _read_geo()

    conn = psycopg2.connect(
        host=env("PGHOST"),
        port=os.environ.get("PGPORT", "5432"),
        dbname=env("PGDATABASE"),
        user=env("PGUSER"),
        password=env("PGPASSWORD"),
    )
    try:
        with conn:
            with conn.cursor() as cur:
                n = insert_geo_levels(cur, levels)
                print(f"[load-geo-data] g2p_geo_levels: {n} rows")
                n = insert_geo_level_values(cur, values)
                print(f"[load-geo-data] g2p_geo_level_values: {n} rows")
    finally:
        conn.close()
    print("[load-geo-data] Completed.")


if __name__ == "__main__":
    main()
