#!/usr/bin/env python3
"""Load geo reference data into the Master Data Postgres.

Reads (from the openg2p-data repo cloned into the image):
- /openg2p-data/geo/geo_hierarchy.csv  -> g2p_geo_levels
- /openg2p-data/geo/{Country,Region,District,Ward,Village}.csv -> g2p_geo_level_values

The level-value CSVs carry (level_value_id, level_value_mnemonic,
parent_level_value_id) but NOT level_id — the loader injects it per file using the
LEVEL_VALUE_FILES map below (which mirrors geo_hierarchy.csv).

Inserts use ON CONFLICT DO NOTHING on the primary key, so re-running (e.g. on a
Helm post-upgrade hook) is idempotent.
"""

import csv
import os
import sys
from pathlib import Path

import psycopg2

OPENG2P_DATA_DIR = Path(os.environ.get("OPENG2P_DATA_DIR", "/openg2p-data"))
GEO_DIR = OPENG2P_DATA_DIR / "geo"

# (filename, level_id) — level_id matches geo_hierarchy.csv, loaded parent-first.
LEVEL_VALUE_FILES = [
    ("Country.csv", "l0"),
    ("Region.csv", "l1"),
    ("District.csv", "l2"),
    ("Ward.csv", "l3"),
    ("Village.csv", "l4"),
]


def env(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        print(f"[load-geo-data] Missing env var: {name}", file=sys.stderr)
        sys.exit(1)
    return value


def _read_csv_rows(path: Path) -> list:
    if not path.is_file():
        print(f"[load-geo-data] Missing file: {path}", file=sys.stderr)
        sys.exit(1)
    with path.open(newline="", encoding="utf-8") as f:
        out = []
        for row in csv.DictReader(f):
            out.append({k: (v if v != "" else None) for k, v in row.items()})
        return out


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


def insert_geo_level_values(cur, rows: list, level_id: str) -> int:
    for r in rows:
        r["level_id"] = level_id
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
                levels = _read_csv_rows(GEO_DIR / "geo_hierarchy.csv")
                n = insert_geo_levels(cur, levels)
                print(f"[load-geo-data] g2p_geo_levels: {n} rows")

                for fname, level_id in LEVEL_VALUE_FILES:
                    rows = _read_csv_rows(GEO_DIR / fname)
                    n = insert_geo_level_values(cur, rows, level_id)
                    print(f"[load-geo-data] g2p_geo_level_values <- {fname} ({level_id}): {n} rows")
    finally:
        conn.close()
    print("[load-geo-data] Completed.")


if __name__ == "__main__":
    main()
