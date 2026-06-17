#!/bin/sh
set -e

# ──────────────────────────────────────────────────────────────
# OpenG2P Master Data DB Seed Entrypoint
#
# Master-data database:
#   PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD
#   LOAD_GEO_DATA    — "true" to load geo data from openg2p-data (default: "true")
#   OPENG2P_DATA_DIR — cloned shared reference data (default: /openg2p-data)
# ──────────────────────────────────────────────────────────────

PGPORT="${PGPORT:-5432}"
LOAD_GEO_DATA="${LOAD_GEO_DATA:-true}"

echo "============================================="
echo " OpenG2P Master Data DB Seed"
echo " Master Data DB : ${PGDATABASE}@${PGHOST}:${PGPORT}"
echo " Geo data       : ${LOAD_GEO_DATA}"
echo "============================================="

if [ "$LOAD_GEO_DATA" = "true" ]; then
  echo "[db-seed] Loading geo data from openg2p-data ..."
  python3 /seed/load_geo_data.py
else
  echo "[db-seed] Skipping geo data (LOAD_GEO_DATA=${LOAD_GEO_DATA})."
fi

echo "[db-seed] Done."
