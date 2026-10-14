#!/usr/bin/env python3
"""
Generate the Master Data Service OpenAPI JSON and write it to docs/openapi/.

Usage (from a venv with master-data-api installed: pip install -e master-data-api):
    python master-data-api/scripts/generate_openapi.py [output_dir]
Default output_dir: docs/openapi at the root of this repository.

The app is built as main.py builds it (catalogue, legacy, samples and the
public catalogue routes are all in the one app, so one spec covers them). The
settings are safe placeholders: nothing connects to a database, IAM, the Audit
Manager, WebSub, AWE or S3 (no start-up runs).
"""
import json
import os
import sys
import tempfile
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parents[2]
DEFAULT_OUT = REPO_DIR / "docs" / "openapi"
FILENAME = "openapi-master-data.json"

PLACEHOLDER_ENV = {
    "MASTER_DATA_API_DB_HOSTNAME": "localhost",
    "MASTER_DATA_API_DB_PORT": "1",
    "MASTER_DATA_API_DB_USERNAME": "openapi",
    "MASTER_DATA_API_DB_PASSWORD": "openapi",
    "MASTER_DATA_API_DB_DBNAME": "openapi",
    "MASTER_DATA_API_CATALOGUE_EFFECTIVE_REFRESH_SECONDS": "0",
    "MASTER_DATA_API_CATALOGUE_OUTBOX_RELAY_SECONDS": "0",
    "MASTER_DATA_API_AUDIT_MANAGER_URL": "",
    "MASTER_DATA_API_WEBSUB_HUB_URL": "",
    "MASTER_DATA_API_AWE_BASE_URL": "",
    "MASTER_DATA_API_BOUNDARY_S3_ENDPOINT": "",
    "MASTER_DATA_API_AUTH_PROVIDER_API_URL": "http://localhost:1",
    "MASTER_DATA_API_LOGGING_LEVEL": "ERROR",
    # /public routes are in the schema only while the public catalogue is on.
    "MASTER_DATA_API_PUBLIC_CATALOGUE_ENABLED": "true",
}

SERVERS = [
    {
        "url": "https://{host}",
        "description": "Master Data Service API. The anonymous /public/... routes can also be served on a separate public host.",
        "variables": {
            "host": {
                "default": "master-data.example.org",
                "description": "Host name of the Master Data Service",
            }
        },
    }
]


def main() -> None:
    out_dir = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_OUT
    with tempfile.TemporaryDirectory() as tmp:
        # Settings read ./.env: run from an empty directory so a local .env cannot leak in.
        os.chdir(tmp)
        os.environ.update(PLACEHOLDER_ENV)

        from openg2p_gen2_master_data.main import app

        schema = app.openapi()
    schema["servers"] = SERVERS
    out_path = out_dir / FILENAME
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(schema, f, indent=2)
        f.write("\n")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
