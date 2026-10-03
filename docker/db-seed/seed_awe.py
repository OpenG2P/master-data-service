#!/usr/bin/env python3
"""Register Master Data's approval policies and callback secret in the shared AWE database.

Only needed when the catalogue runs with approval mode ``awe``. Same pattern as
the registry's db-seed (awe_meta_data/*.sql): rows are inserted straight into
the AWE database that commons-services deploys, idempotently.

Seeds, per policy key (lists, geography):
  * approval_policy  — active, forbid_self_approval (maker != checker in AWE too)
  * approval_stage   — one stage, one approval completes it (mode any-n, 1)
  * approver_rule    — users holding the client role AWE_APPROVER_ROLE on
                       AWE_APPROVER_CLIENT (default MASTER_DATA_APPROVER on master-data)
and the callback_secret row AWE signs its callbacks to Master Data with.

Environment:
  AWE_PGHOST, AWE_PGPORT, AWE_PGDATABASE, AWE_PGUSER, AWE_PGPASSWORD
  AWE_POLICY_KEY_LIST, AWE_POLICY_KEY_GEO
  AWE_APPROVER_ROLE, AWE_APPROVER_CLIENT
  AWE_CALLBACK_SECRET_ID, AWE_CALLBACK_CALLER_SERVICE (the callback URL), AWE_CALLBACK_HMAC_SECRET
"""

import json
import os
import sys
import uuid

import psycopg2

NAMESPACE = uuid.UUID("6f1d0c1e-5a7b-4c39-9d0e-3b8f2a6c4d10")


def _id(*parts):
    """Stable ids, so re-running updates nothing and inserts nothing new."""
    return str(uuid.uuid5(NAMESPACE, "/".join(parts)))


def main():
    env = os.environ
    if not env.get("AWE_PGHOST") or not env.get("AWE_PGDATABASE"):
        print("[awe-seed] AWE database not configured — skipping")
        return
    policies = [
        (env.get("AWE_POLICY_KEY_LIST", "master_data.list_version.v1"), "master_data.list_version",
         "Master Data: publish a code-list version"),
        (env.get("AWE_POLICY_KEY_GEO", "master_data.geo_version.v1"), "master_data.geo_version",
         "Master Data: publish a geography version"),
    ]
    role = env.get("AWE_APPROVER_ROLE", "MASTER_DATA_APPROVER")
    client = env.get("AWE_APPROVER_CLIENT", "master-data")
    conn = psycopg2.connect(
        host=env["AWE_PGHOST"], port=env.get("AWE_PGPORT", "5432"), dbname=env["AWE_PGDATABASE"],
        user=env.get("AWE_PGUSER"), password=env.get("AWE_PGPASSWORD"),
    )
    with conn, conn.cursor() as cur:
        for key, artifact, name in policies:
            pid, sid, rid = _id(key, "policy"), _id(key, "stage", "1"), _id(key, "rule", "1")
            cur.execute(
                """INSERT INTO approval_policy (id, policy_key, version, name, description, status, artifact_type,
                       created_by, forbid_self_approval, forbid_repeat_approvers, created_at, updated_at)
                   VALUES (%s, %s, 1, %s, %s, 'active', %s, 'master-data-seed', TRUE, FALSE, NOW(), NOW())
                   ON CONFLICT DO NOTHING""",
                (pid, key, name, "Seeded by the Master Data chart; edit the stages in AWE as needed.", artifact),
            )
            cur.execute(
                """INSERT INTO approval_stage (id, policy_id, stage_order, name, mode, mode_value, sla_hours,
                       parallel_group, skip_if, on_empty, on_breach, escalation_rules_json, created_at, updated_at)
                   SELECT %s, %s, 1, 'Master data approvers', 'any-n', 1, NULL, NULL, 'null', 'block', NULL,
                          'null', NOW(), NOW()
                    WHERE EXISTS (SELECT 1 FROM approval_policy WHERE id = %s)
                   ON CONFLICT DO NOTHING""",
                (sid, pid, pid),
            )
            cur.execute(
                """INSERT INTO approver_rule (id, stage_id, rule_type, rule_value, kind, required, created_at,
                       updated_at)
                   SELECT %s, %s, 'role', %s, 'approver', FALSE, NOW(), NOW()
                    WHERE EXISTS (SELECT 1 FROM approval_stage WHERE id = %s)
                   ON CONFLICT DO NOTHING""",
                (rid, sid, json.dumps({"role": role, "client": client}), sid),
            )
            print(f"[awe-seed] policy {key} ({artifact}) -> approvers: client role {client}/{role}")
        secret = env.get("AWE_CALLBACK_HMAC_SECRET")
        caller = env.get("AWE_CALLBACK_CALLER_SERVICE")
        if secret and caller:
            cur.execute(
                """INSERT INTO callback_secret (id, caller_service, secret_hash, status, rotated_at, created_at,
                       updated_at)
                   VALUES (%s, %s, %s, 'active', NOW(), NOW(), NOW())
                   ON CONFLICT (id) DO UPDATE SET caller_service = EXCLUDED.caller_service, updated_at = NOW()""",
                (env.get("AWE_CALLBACK_SECRET_ID", "master-data"), caller, secret),
            )
            print(f"[awe-seed] callback secret {env.get('AWE_CALLBACK_SECRET_ID', 'master-data')} -> {caller}")
        else:
            print("[awe-seed] AWE_CALLBACK_HMAC_SECRET / AWE_CALLBACK_CALLER_SERVICE unset — no callback secret",
                  file=sys.stderr)
    conn.close()


if __name__ == "__main__":
    main()
