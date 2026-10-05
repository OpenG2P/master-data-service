"""Idempotent SQL for the catalogue, run by ``migrate_database`` on every start.

Everything here is ``CREATE OR REPLACE`` / ``IF NOT EXISTS`` / ``DROP ... IF
EXISTS`` + ``CREATE``, so re-running is a no-op.

Why the core operations live in the database as functions
---------------------------------------------------------
Publishing a version (flip the status, stamp the effective date, refresh the
legacy tables) and migrating pre-catalogue data to version 1 are needed by two
callers: this API and the country-pack loader (``docker/db-seed``), which is a
separate image talking psycopg2. One implementation in PL/pgSQL keeps them from
drifting, and makes each step atomic with the caller's transaction.

The functions do not write the change log (callers do, so the actor and details
are theirs), with two exceptions where the database itself is the cause:
``g2p_catalogue_bootstrap_v1`` (migration) and ``g2p_catalogue_refresh_current``
(a future-effective version coming into effect).

Version numbers are never reused
--------------------------------
``g2p_catalogue_next_list_version`` / ``g2p_catalogue_next_geo_version``
allocate the next number for the API and the loader alike: one more than the
highest number ever used for that subject, counting both the version rows
(a discarded draft is kept as a DISCARDED row, not deleted) and the change log
(which also remembers numbers used before tombstones existed, and numbers of a
never-published list that was deleted and re-created with the same id). So the
change log, the Audit Manager trail and boundary object keys
(``geo/<country>/v<n>/...``) of one version can never be confused with
another's. Callers serialise allocation: the list row is locked FOR UPDATE, the
geography takes the ``g2p_geo_draft`` advisory lock.

Outbox
------
Every change-log row is an outbox entry: ``forwarded_at`` is NULL until the
event has been delivered to the Audit Manager (and, for version
published/effective events, to WebSub), or there was nowhere to deliver it.
The API's relay (services/catalogue_outbox.py) forwards pending rows, so events
written by the database itself (``*.version.effective``, ``*.version.migrated``)
and by the country-pack loader reach the same destinations as the API's own.
``forwarded_at`` is the only column of the change log that may ever change.

Legacy read cache
-----------------
``g2p_catalogue_state['legacy.generation']`` is bumped every time the legacy
tables are re-materialised. Each API worker polls it and drops its in-memory
read cache when it moves (see services/catalogue_outbox.py).

Immutability
------------
Triggers make a PUBLISHED version read-only: its version row cannot be updated
or deleted, and rows cannot be inserted into, changed in or deleted from it. The
same holds for a PUBLISHED release and its members. The change log is
append-only. Errors raised by these triggers start with ``G2P-CAT-IMMUTABLE``.
The one exception is the migration itself, once: when the ``*_by_name``
columns are added it fills them for existing rows (see ``_add_name_columns``).
"""

# Bumped whenever the catalogue schema changes (3: *_by_name columns;
# 4: g2p_attributes.domain). The
# geo-seed Job waits for g2p_catalogue_state['schema_version'] >= this (its
# CATALOGUE_SCHEMA_VERSION value in the Helm chart must match).
CATALOGUE_SCHEMA_VERSION = 4

_ALTER_LEGACY = [
    "ALTER TABLE g2p_attributes ADD COLUMN IF NOT EXISTS description text",
    "ALTER TABLE g2p_attributes ADD COLUMN IF NOT EXISTS display_i18n jsonb",
    "ALTER TABLE g2p_attributes ADD COLUMN IF NOT EXISTS attribute_schema jsonb",
    "ALTER TABLE g2p_attributes ADD COLUMN IF NOT EXISTS owner_org varchar",
    "ALTER TABLE g2p_attributes ADD COLUMN IF NOT EXISTS current_version_no integer",
    "ALTER TABLE g2p_attributes ADD COLUMN IF NOT EXISTS domain varchar",
]


def _add_name_columns(table: str, trigger: str, columns: tuple) -> str:
    """Add ``<col>_name`` next to each ``<col>`` (a user id) and backfill it once.

    New rows get the display name written together with the id, by the API (see
    services/*). For rows written before the column existed, the name is the
    latest ``actor_name`` the change log holds for that id; ids with no named
    event (system actors, or values that predate stable ids) stay NULL and
    readers fall back to the id.

    The backfill is the only time a PUBLISHED row is ever updated: the guard
    trigger is disabled for it and re-enabled right after, inside the
    migration's single transaction (ALTER TABLE ... DISABLE TRIGGER is
    transactional and takes an ACCESS EXCLUSIVE lock, so no other session ever
    sees the table unguarded), and it runs only when the columns are first
    added. Only the new name columns are written.
    """
    first = f"{columns[0]}_name"
    adds = "\n    ".join(f"ALTER TABLE {table} ADD COLUMN {c}_name varchar;" for c in columns)
    sets = ",\n           ".join(
        f"""{c}_name = coalesce({c}_name, (SELECT l.actor_name FROM g2p_catalogue_change_log l
                     WHERE l.actor = t.{c} AND l.actor_name IS NOT NULL
                     ORDER BY l.event_id DESC LIMIT 1))"""
        for c in columns
    )
    where = " OR ".join(f"({c} IS NOT NULL AND {c}_name IS NULL)" for c in columns)
    return f"""
DO $$
BEGIN
  LOCK TABLE {table} IN ACCESS EXCLUSIVE MODE;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                  WHERE table_name = '{table}' AND column_name = '{first}') THEN
    {adds}
    ALTER TABLE {table} DISABLE TRIGGER {trigger};
    UPDATE {table} t
       SET {sets}
     WHERE {where};
    ALTER TABLE {table} ENABLE TRIGGER {trigger};
  END IF;
END $$
"""


# Columns added to catalogue tables after their first release (create_all never
# adds a column to an existing table). Run after the guards and triggers.
_ALTER_CATALOGUE = [
    "ALTER TABLE g2p_catalogue_change_log ADD COLUMN IF NOT EXISTS actor_name varchar",
    "ALTER TABLE g2p_catalogue_releases ADD COLUMN IF NOT EXISTS members_set_by varchar",
    "ALTER TABLE g2p_catalogue_releases ADD COLUMN IF NOT EXISTS members_set_at timestamptz",
    # The outbox marker. When the column is first added to an existing log, the
    # history is marked forwarded: it was already sent (best effort) by the
    # pre-outbox code, and replaying it would duplicate the audit trail.
    """
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                  WHERE table_name = 'g2p_catalogue_change_log' AND column_name = 'forwarded_at') THEN
    ALTER TABLE g2p_catalogue_change_log ADD COLUMN forwarded_at timestamptz;
    UPDATE g2p_catalogue_change_log SET forwarded_at = at;
  END IF;
END $$
""",
    """CREATE INDEX IF NOT EXISTS ix_g2p_catalogue_change_log_pending
         ON g2p_catalogue_change_log (event_id) WHERE forwarded_at IS NULL""",
    *(
        _add_name_columns(table, trigger, columns)
        for table, trigger, columns in (
            (
                "g2p_list_versions",
                "trg_g2p_list_versions_guard",
                ("created_by", "updated_by", "submitted_by", "decided_by"),
            ),
            (
                "g2p_geo_versions",
                "trg_g2p_geo_versions_guard",
                ("created_by", "updated_by", "submitted_by", "decided_by"),
            ),
            (
                "g2p_catalogue_releases",
                "trg_g2p_catalogue_releases_guard",
                ("created_by", "members_set_by", "published_by"),
            ),
            ("g2p_geo_changes", "trg_g2p_geo_changes_guard", ("created_by",)),
        )
    ),
]

_INDEXES = [
    # At most one open (DRAFT or SUBMITTED) version per list, and one for geography.
    """CREATE UNIQUE INDEX IF NOT EXISTS uq_g2p_list_versions_open
         ON g2p_list_versions (list_id) WHERE status IN ('DRAFT', 'SUBMITTED')""",
    """CREATE UNIQUE INDEX IF NOT EXISTS uq_g2p_geo_versions_open
         ON g2p_geo_versions ((true)) WHERE status IN ('DRAFT', 'SUBMITTED')""",
    """CREATE INDEX IF NOT EXISTS ix_g2p_list_version_values_lookup
         ON g2p_list_version_values (list_id, version_no, value_code)""",
    """CREATE INDEX IF NOT EXISTS ix_g2p_geo_version_units_level
         ON g2p_geo_version_units (version_no, level_id, parent_unit_id)""",
    """CREATE INDEX IF NOT EXISTS ix_g2p_geo_changes_from
         ON g2p_geo_changes USING gin (from_units)""",
    """CREATE INDEX IF NOT EXISTS ix_g2p_geo_changes_to
         ON g2p_geo_changes USING gin (to_units)""",
]

_GUARDS = [
    # ---- parent rows: a PUBLISHED version / release is frozen ---------------
    """
CREATE OR REPLACE FUNCTION g2p_catalogue_guard_published_parent() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.status = 'PUBLISHED' THEN
    RAISE EXCEPTION 'G2P-CAT-IMMUTABLE: % row is PUBLISHED and cannot be %d',
      TG_TABLE_NAME, lower(TG_OP)
      USING ERRCODE = 'restrict_violation';
  END IF;
  IF TG_OP = 'DELETE' THEN
    RETURN OLD;
  END IF;
  RETURN NEW;
END $$
""",
    # ---- list values ---------------------------------------------------------
    """
CREATE OR REPLACE FUNCTION g2p_catalogue_guard_list_values() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE st varchar;
BEGIN
  IF TG_OP IN ('UPDATE', 'DELETE') THEN
    SELECT status INTO st FROM g2p_list_versions
     WHERE list_id = OLD.list_id AND version_no = OLD.version_no;
    IF st = 'PUBLISHED' THEN
      RAISE EXCEPTION 'G2P-CAT-IMMUTABLE: version % of list % is PUBLISHED and cannot be changed',
        OLD.version_no, OLD.list_id USING ERRCODE = 'restrict_violation';
    END IF;
  END IF;
  IF TG_OP IN ('INSERT', 'UPDATE') THEN
    SELECT status INTO st FROM g2p_list_versions
     WHERE list_id = NEW.list_id AND version_no = NEW.version_no;
    IF st = 'PUBLISHED' THEN
      RAISE EXCEPTION 'G2P-CAT-IMMUTABLE: version % of list % is PUBLISHED and cannot be changed',
        NEW.version_no, NEW.list_id USING ERRCODE = 'restrict_violation';
    END IF;
  END IF;
  IF TG_OP = 'DELETE' THEN
    RETURN OLD;
  END IF;
  RETURN NEW;
END $$
""",
    # ---- geography levels / units / changes -----------------------------------
    """
CREATE OR REPLACE FUNCTION g2p_catalogue_guard_geo_children() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE st varchar;
BEGIN
  IF TG_OP IN ('UPDATE', 'DELETE') THEN
    SELECT status INTO st FROM g2p_geo_versions WHERE version_no = OLD.version_no;
    IF st = 'PUBLISHED' THEN
      RAISE EXCEPTION 'G2P-CAT-IMMUTABLE: geography version % is PUBLISHED and cannot be changed (%)',
        OLD.version_no, TG_TABLE_NAME USING ERRCODE = 'restrict_violation';
    END IF;
  END IF;
  IF TG_OP IN ('INSERT', 'UPDATE') THEN
    SELECT status INTO st FROM g2p_geo_versions WHERE version_no = NEW.version_no;
    IF st = 'PUBLISHED' THEN
      RAISE EXCEPTION 'G2P-CAT-IMMUTABLE: geography version % is PUBLISHED and cannot be changed (%)',
        NEW.version_no, TG_TABLE_NAME USING ERRCODE = 'restrict_violation';
    END IF;
  END IF;
  IF TG_OP = 'DELETE' THEN
    RETURN OLD;
  END IF;
  RETURN NEW;
END $$
""",
    # ---- release members ---------------------------------------------------
    """
CREATE OR REPLACE FUNCTION g2p_catalogue_guard_release_members() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE st varchar;
BEGIN
  IF TG_OP IN ('UPDATE', 'DELETE') THEN
    SELECT status INTO st FROM g2p_catalogue_releases WHERE release_code = OLD.release_code;
    IF st = 'PUBLISHED' THEN
      RAISE EXCEPTION 'G2P-CAT-IMMUTABLE: release % is PUBLISHED and cannot be changed',
        OLD.release_code USING ERRCODE = 'restrict_violation';
    END IF;
  END IF;
  IF TG_OP IN ('INSERT', 'UPDATE') THEN
    SELECT status INTO st FROM g2p_catalogue_releases WHERE release_code = NEW.release_code;
    IF st = 'PUBLISHED' THEN
      RAISE EXCEPTION 'G2P-CAT-IMMUTABLE: release % is PUBLISHED and cannot be changed',
        NEW.release_code USING ERRCODE = 'restrict_violation';
    END IF;
  END IF;
  IF TG_OP = 'DELETE' THEN
    RETURN OLD;
  END IF;
  RETURN NEW;
END $$
""",
    # ---- change log is append-only -----------------------------------------
    # The one exception is the outbox marker: setting forwarded_at (and nothing
    # else) once the event has been delivered.
    """
CREATE OR REPLACE FUNCTION g2p_catalogue_guard_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'UPDATE' AND TG_TABLE_NAME = 'g2p_catalogue_change_log'
     AND (to_jsonb(NEW) - 'forwarded_at') = (to_jsonb(OLD) - 'forwarded_at') THEN
    RETURN NEW;
  END IF;
  RAISE EXCEPTION 'G2P-CAT-IMMUTABLE: % is append-only', TG_TABLE_NAME
    USING ERRCODE = 'restrict_violation';
END $$
""",
]


def _trigger(name: str, table: str, events: str, function: str) -> list[str]:
    return [
        f"DROP TRIGGER IF EXISTS {name} ON {table}",
        f"CREATE TRIGGER {name} BEFORE {events} ON {table} FOR EACH ROW EXECUTE FUNCTION {function}()",
    ]


_TRIGGERS = [
    *_trigger(
        "trg_g2p_list_versions_guard",
        "g2p_list_versions",
        "UPDATE OR DELETE",
        "g2p_catalogue_guard_published_parent",
    ),
    *_trigger(
        "trg_g2p_list_version_values_guard",
        "g2p_list_version_values",
        "INSERT OR UPDATE OR DELETE",
        "g2p_catalogue_guard_list_values",
    ),
    *_trigger(
        "trg_g2p_geo_versions_guard",
        "g2p_geo_versions",
        "UPDATE OR DELETE",
        "g2p_catalogue_guard_published_parent",
    ),
    *_trigger(
        "trg_g2p_geo_version_levels_guard",
        "g2p_geo_version_levels",
        "INSERT OR UPDATE OR DELETE",
        "g2p_catalogue_guard_geo_children",
    ),
    *_trigger(
        "trg_g2p_geo_version_units_guard",
        "g2p_geo_version_units",
        "INSERT OR UPDATE OR DELETE",
        "g2p_catalogue_guard_geo_children",
    ),
    *_trigger(
        "trg_g2p_geo_changes_guard",
        "g2p_geo_changes",
        "INSERT OR UPDATE OR DELETE",
        "g2p_catalogue_guard_geo_children",
    ),
    *_trigger(
        "trg_g2p_catalogue_releases_guard",
        "g2p_catalogue_releases",
        "UPDATE OR DELETE",
        "g2p_catalogue_guard_published_parent",
    ),
    *_trigger(
        "trg_g2p_catalogue_release_members_guard",
        "g2p_catalogue_release_members",
        "INSERT OR UPDATE OR DELETE",
        "g2p_catalogue_guard_release_members",
    ),
    *_trigger(
        "trg_g2p_catalogue_change_log_guard",
        "g2p_catalogue_change_log",
        "UPDATE OR DELETE",
        "g2p_catalogue_guard_append_only",
    ),
]

_FUNCTIONS = [
    # ---- change log ----------------------------------------------------------
    """
CREATE OR REPLACE FUNCTION g2p_catalogue_log(
  p_event_type varchar, p_subject_type varchar, p_subject_id varchar,
  p_version_no integer, p_actor varchar, p_details jsonb
) RETURNS bigint LANGUAGE sql AS $$
  INSERT INTO g2p_catalogue_change_log (event_type, subject_type, subject_id, version_no, actor, at, details)
  VALUES (p_event_type, p_subject_type, p_subject_id, p_version_no, p_actor, now(), p_details)
  RETURNING event_id
$$
""",
    # ---- version numbers: never reused (see the module docstring) -------------
    """
CREATE OR REPLACE FUNCTION g2p_catalogue_next_list_version(p_list_id varchar) RETURNS integer
LANGUAGE sql STABLE AS $$
  SELECT greatest(
    (SELECT coalesce(max(version_no), 0) FROM g2p_list_versions WHERE list_id = p_list_id),
    (SELECT coalesce(max(version_no), 0) FROM g2p_catalogue_change_log
      WHERE subject_type = 'list' AND subject_id = p_list_id)
  ) + 1
$$
""",
    """
CREATE OR REPLACE FUNCTION g2p_catalogue_next_geo_version() RETURNS integer
LANGUAGE sql STABLE AS $$
  SELECT greatest(
    (SELECT coalesce(max(version_no), 0) FROM g2p_geo_versions),
    (SELECT coalesce(max(version_no), 0) FROM g2p_catalogue_change_log WHERE subject_type = 'geo')
  ) + 1
$$
""",
    # ---- legacy read-cache generation (bumped on every re-materialisation) ----
    """
CREATE OR REPLACE FUNCTION g2p_catalogue_bump_legacy_generation() RETURNS void
LANGUAGE sql AS $$
  INSERT INTO g2p_catalogue_state (key, int_value, updated_at)
  VALUES ('legacy.generation', 1, now())
  ON CONFLICT (key) DO UPDATE
    SET int_value = coalesce(g2p_catalogue_state.int_value, 0) + 1, updated_at = now()
$$
""",
    # ---- which version is current (latest published, already in effect) -----
    """
CREATE OR REPLACE FUNCTION g2p_catalogue_current_list_version(
  p_list_id varchar, p_at timestamptz DEFAULT now()
) RETURNS integer LANGUAGE sql STABLE AS $$
  SELECT max(version_no) FROM g2p_list_versions
   WHERE list_id = p_list_id AND status = 'PUBLISHED' AND effective_from <= p_at
$$
""",
    """
CREATE OR REPLACE FUNCTION g2p_catalogue_current_geo_version(
  p_at timestamptz DEFAULT now()
) RETURNS integer LANGUAGE sql STABLE AS $$
  SELECT max(version_no) FROM g2p_geo_versions
   WHERE status = 'PUBLISHED' AND effective_from <= p_at
$$
""",
    # ---- materialise the legacy tables from the current version ---------------
    """
CREATE OR REPLACE FUNCTION g2p_catalogue_materialise_list(p_list_id varchar) RETURNS integer
LANGUAGE plpgsql AS $$
DECLARE
  v integer;
  r g2p_list_versions%ROWTYPE;
BEGIN
  v := g2p_catalogue_current_list_version(p_list_id);
  IF v IS NULL THEN
    -- Nothing in effect yet (never published, or only a future-effective
    -- version): the legacy rows stay as they are.
    RETURN NULL;
  END IF;
  SELECT * INTO r FROM g2p_list_versions WHERE list_id = p_list_id AND version_no = v;
  UPDATE g2p_attributes
     SET attribute_code = coalesce(r.list_code, attribute_code),
         attribute_display = coalesce(r.display, attribute_display),
         is_hierarchical = coalesce(r.is_hierarchical, false),
         display_i18n = r.display_i18n,
         attribute_schema = r.attribute_schema,
         current_version_no = v
   WHERE attribute_id = p_list_id;
  DELETE FROM g2p_attribute_values WHERE attribute_id = p_list_id;
  -- Only ACTIVE values: the legacy tables are the CURRENT state, and a retired
  -- value must stop appearing in registry dropdowns.
  INSERT INTO g2p_attribute_values
    (value_id, attribute_id, value_code, value_display, parent_value_id, sort_order)
  SELECT x.value_id, x.list_id, x.value_code, x.display, p.value_id, x.sort_order
    FROM g2p_list_version_values x
    LEFT JOIN g2p_list_version_values p
      ON p.list_id = x.list_id AND p.version_no = x.version_no AND p.value_code = x.parent_value_code
   WHERE x.list_id = p_list_id AND x.version_no = v AND x.status = 'ACTIVE';
  PERFORM g2p_catalogue_bump_legacy_generation();
  RETURN v;
END $$
""",
    """
CREATE OR REPLACE FUNCTION g2p_catalogue_materialise_geo() RETURNS integer
LANGUAGE plpgsql AS $$
DECLARE v integer;
BEGIN
  v := g2p_catalogue_current_geo_version();
  IF v IS NULL THEN
    RETURN NULL;
  END IF;
  DELETE FROM g2p_geo_level_values;
  DELETE FROM g2p_geo_levels;
  INSERT INTO g2p_geo_levels (level_id, level_mnemonic, parent_level_id)
  SELECT level_id, level_mnemonic, parent_level_id
    FROM g2p_geo_version_levels WHERE version_no = v;
  INSERT INTO g2p_geo_level_values (level_value_id, level_id, level_value_mnemonic, parent_level_value_id)
  SELECT unit_id, level_id, name, parent_unit_id
    FROM g2p_geo_version_units WHERE version_no = v AND status = 'ACTIVE';
  INSERT INTO g2p_catalogue_state (key, int_value, updated_at)
  VALUES ('geo.current_version_no', v, now())
  ON CONFLICT (key) DO UPDATE SET int_value = EXCLUDED.int_value, updated_at = now();
  PERFORM g2p_catalogue_bump_legacy_generation();
  RETURN v;
END $$
""",
    # ---- publish -------------------------------------------------------------
    """
CREATE OR REPLACE FUNCTION g2p_catalogue_publish_list(
  p_list_id varchar, p_version_no integer, p_actor varchar,
  p_effective_from timestamptz, p_note text, p_allow_draft boolean DEFAULT false
) RETURNS timestamptz LANGUAGE plpgsql AS $$
DECLARE
  r g2p_list_versions%ROWTYPE;
  prev g2p_list_versions%ROWTYPE;
  eff timestamptz;
BEGIN
  SELECT * INTO r FROM g2p_list_versions
   WHERE list_id = p_list_id AND version_no = p_version_no FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'G2P-CAT-404: version % of list % not found', p_version_no, p_list_id;
  END IF;
  IF r.status <> 'SUBMITTED' AND NOT (p_allow_draft AND r.status = 'DRAFT') THEN
    RAISE EXCEPTION 'G2P-CAT-409: version % of list % is %, not SUBMITTED', p_version_no, p_list_id, r.status;
  END IF;
  SELECT * INTO prev FROM g2p_list_versions
   WHERE list_id = p_list_id AND status = 'PUBLISHED' ORDER BY version_no DESC LIMIT 1;
  IF FOUND AND prev.version_no > p_version_no THEN
    RAISE EXCEPTION 'G2P-CAT-409: version % of list % was published after version % was drafted',
      prev.version_no, p_list_id, p_version_no;
  END IF;
  eff := coalesce(p_effective_from, r.effective_from, now());
  IF FOUND AND eff < prev.effective_from THEN
    RAISE EXCEPTION 'G2P-CAT-400: effective_from % is earlier than version %''s effective_from %',
      eff, prev.version_no, prev.effective_from;
  END IF;
  UPDATE g2p_list_versions
     SET status = 'PUBLISHED', effective_from = eff, published_at = now(),
         decided_by = coalesce(p_actor, decided_by), decided_at = now(),
         decision_note = coalesce(p_note, decision_note)
   WHERE list_id = p_list_id AND version_no = p_version_no;
  PERFORM g2p_catalogue_materialise_list(p_list_id);
  RETURN eff;
END $$
""",
    """
CREATE OR REPLACE FUNCTION g2p_catalogue_publish_geo(
  p_version_no integer, p_actor varchar, p_effective_from timestamptz,
  p_note text, p_allow_draft boolean DEFAULT false
) RETURNS timestamptz LANGUAGE plpgsql AS $$
DECLARE
  r g2p_geo_versions%ROWTYPE;
  prev g2p_geo_versions%ROWTYPE;
  eff timestamptz;
BEGIN
  SELECT * INTO r FROM g2p_geo_versions WHERE version_no = p_version_no FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'G2P-CAT-404: geography version % not found', p_version_no;
  END IF;
  IF r.status <> 'SUBMITTED' AND NOT (p_allow_draft AND r.status = 'DRAFT') THEN
    RAISE EXCEPTION 'G2P-CAT-409: geography version % is %, not SUBMITTED', p_version_no, r.status;
  END IF;
  SELECT * INTO prev FROM g2p_geo_versions
   WHERE status = 'PUBLISHED' ORDER BY version_no DESC LIMIT 1;
  IF FOUND AND prev.version_no > p_version_no THEN
    RAISE EXCEPTION 'G2P-CAT-409: geography version % was published after version % was drafted',
      prev.version_no, p_version_no;
  END IF;
  eff := coalesce(p_effective_from, r.effective_from, now());
  IF FOUND AND eff < prev.effective_from THEN
    RAISE EXCEPTION 'G2P-CAT-400: effective_from % is earlier than geography version %''s effective_from %',
      eff, prev.version_no, prev.effective_from;
  END IF;
  -- Units new in this version (or brought back) start now; units retired in
  -- this version end now. Carried-over units keep the dates copied from base.
  UPDATE g2p_geo_version_units u SET valid_from = eff, valid_to = NULL
   WHERE u.version_no = p_version_no AND u.status = 'ACTIVE'
     AND NOT EXISTS (SELECT 1 FROM g2p_geo_version_units b
                      WHERE b.version_no = r.base_version_no AND b.unit_id = u.unit_id
                        AND b.status = 'ACTIVE');
  UPDATE g2p_geo_version_units u SET valid_to = eff
   WHERE u.version_no = p_version_no AND u.status = 'RETIRED'
     AND EXISTS (SELECT 1 FROM g2p_geo_version_units b
                  WHERE b.version_no = r.base_version_no AND b.unit_id = u.unit_id
                    AND b.status = 'ACTIVE');
  UPDATE g2p_geo_changes SET effective_date = eff::date
   WHERE version_no = p_version_no AND effective_date IS NULL;
  UPDATE g2p_geo_versions
     SET status = 'PUBLISHED', effective_from = eff, published_at = now(),
         decided_by = coalesce(p_actor, decided_by), decided_at = now(),
         decision_note = coalesce(p_note, decision_note)
   WHERE version_no = p_version_no;
  PERFORM g2p_catalogue_materialise_geo();
  RETURN eff;
END $$
""",
    # ---- complete the lineage of a geography draft -----------------------------
    # Every unit that appears, disappears, is renamed or moves gets a change
    # event, so the crosswalk can always follow it. Explicit events (SPLIT,
    # MERGE, RECODE...) recorded by a person take precedence; this only fills
    # the gaps, one event per unit, flagged is_auto.
    """
CREATE OR REPLACE FUNCTION g2p_catalogue_geo_autolineage(p_version_no integer, p_actor varchar)
RETURNS integer LANGUAGE plpgsql AS $$
DECLARE
  base integer;
  n integer := 0;
  k integer;
BEGIN
  SELECT base_version_no INTO base FROM g2p_geo_versions WHERE version_no = p_version_no;
  IF base IS NULL THEN
    RETURN 0;
  END IF;
  -- Created: active now, not active in base, not the target of any event.
  INSERT INTO g2p_geo_changes (version_no, change_type, from_units, to_units, note, is_auto, created_by, created_at)
  SELECT p_version_no, 'CREATE', ARRAY[]::varchar[], ARRAY[u.unit_id]::varchar[], 'auto: unit created', true, p_actor, now()
    FROM g2p_geo_version_units u
   WHERE u.version_no = p_version_no AND u.status = 'ACTIVE'
     AND NOT EXISTS (SELECT 1 FROM g2p_geo_version_units b
                      WHERE b.version_no = base AND b.unit_id = u.unit_id AND b.status = 'ACTIVE')
     AND NOT EXISTS (SELECT 1 FROM g2p_geo_changes c
                      WHERE c.version_no = p_version_no AND u.unit_id = ANY (c.to_units));
  GET DIAGNOSTICS k = ROW_COUNT; n := n + k;
  -- Retired: active in base, retired (or gone) now, not the source of any event.
  INSERT INTO g2p_geo_changes (version_no, change_type, from_units, to_units, note, is_auto, created_by, created_at)
  SELECT p_version_no, 'RETIRE', ARRAY[b.unit_id]::varchar[], ARRAY[]::varchar[], 'auto: unit retired', true, p_actor, now()
    FROM g2p_geo_version_units b
   WHERE b.version_no = base AND b.status = 'ACTIVE'
     AND NOT EXISTS (SELECT 1 FROM g2p_geo_version_units u
                      WHERE u.version_no = p_version_no AND u.unit_id = b.unit_id AND u.status = 'ACTIVE')
     AND NOT EXISTS (SELECT 1 FROM g2p_geo_changes c
                      WHERE c.version_no = p_version_no AND b.unit_id = ANY (c.from_units));
  GET DIAGNOSTICS k = ROW_COUNT; n := n + k;
  -- Renamed.
  INSERT INTO g2p_geo_changes (version_no, change_type, from_units, to_units, note, is_auto, created_by, created_at)
  SELECT p_version_no, 'RENAME', ARRAY[u.unit_id]::varchar[], ARRAY[u.unit_id]::varchar[],
         'auto: ' || b.name || ' -> ' || u.name, true, p_actor, now()
    FROM g2p_geo_version_units u
    JOIN g2p_geo_version_units b ON b.version_no = base AND b.unit_id = u.unit_id AND b.status = 'ACTIVE'
   WHERE u.version_no = p_version_no AND u.status = 'ACTIVE' AND u.name IS DISTINCT FROM b.name
     AND NOT EXISTS (SELECT 1 FROM g2p_geo_changes c
                      WHERE c.version_no = p_version_no AND c.change_type = 'RENAME'
                        AND u.unit_id = ANY (c.from_units));
  GET DIAGNOSTICS k = ROW_COUNT; n := n + k;
  -- Moved under another parent.
  INSERT INTO g2p_geo_changes (version_no, change_type, from_units, to_units, note, is_auto, created_by, created_at)
  SELECT p_version_no, 'REPARENT', ARRAY[u.unit_id]::varchar[], ARRAY[u.unit_id]::varchar[],
         'auto: parent ' || coalesce(b.parent_unit_id, '-') || ' -> ' || coalesce(u.parent_unit_id, '-'),
         true, p_actor, now()
    FROM g2p_geo_version_units u
    JOIN g2p_geo_version_units b ON b.version_no = base AND b.unit_id = u.unit_id AND b.status = 'ACTIVE'
   WHERE u.version_no = p_version_no AND u.status = 'ACTIVE'
     AND u.parent_unit_id IS DISTINCT FROM b.parent_unit_id
     AND NOT EXISTS (SELECT 1 FROM g2p_geo_changes c
                      WHERE c.version_no = p_version_no AND c.change_type = 'REPARENT'
                        AND u.unit_id = ANY (c.from_units));
  GET DIAGNOSTICS k = ROW_COUNT; n := n + k;
  RETURN n;
END $$
""",
    # ---- migration of pre-catalogue data to version 1 -------------------------
    # Every list that has no version yet becomes version 1 PUBLISHED from the
    # legacy rows, and the legacy geography becomes geography version 1, if
    # there is no geography version yet. effective_from is the epoch: the data
    # was in force before the catalogue existed, so an as_of query for any
    # earlier date still resolves to it. Idempotent: subjects that already have
    # a version are skipped.
    """
CREATE OR REPLACE FUNCTION g2p_catalogue_bootstrap_v1(p_actor varchar) RETURNS jsonb
LANGUAGE plpgsql AS $$
DECLARE
  a record;
  v integer;
  gv integer;
  n_lists integer := 0;
  n_units integer := 0;
  geo_done boolean := false;
  eff timestamptz := '1970-01-01T00:00:00Z';
BEGIN
  PERFORM pg_advisory_xact_lock(hashtext('g2p_catalogue_bootstrap_v1'));

  FOR a IN SELECT * FROM g2p_attributes x
            WHERE NOT EXISTS (SELECT 1 FROM g2p_list_versions v WHERE v.list_id = x.attribute_id)
            ORDER BY x.attribute_id LOOP
    -- 1 on a fresh database; higher only if the change log already used 1.
    v := g2p_catalogue_next_list_version(a.attribute_id);
    INSERT INTO g2p_list_versions
      (list_id, version_no, status, list_code, display, display_i18n, is_hierarchical, attribute_schema,
       change_note, effective_from, created_by, created_at, updated_by, updated_at)
    VALUES
      (a.attribute_id, v, 'DRAFT', coalesce(a.attribute_code, a.attribute_id), a.attribute_display,
       a.display_i18n, coalesce(a.is_hierarchical, false), a.attribute_schema,
       'Version 1: migrated from the pre-catalogue tables', eff, p_actor, now(), p_actor, now());
    INSERT INTO g2p_list_version_values
      (list_id, version_no, value_id, value_code, display, parent_value_code, sort_order, status)
    SELECT x.attribute_id, v, x.value_id, coalesce(x.value_code, x.value_id), x.value_display,
           p.value_code, x.sort_order, 'ACTIVE'
      FROM g2p_attribute_values x
      LEFT JOIN g2p_attribute_values p
        ON p.attribute_id = x.attribute_id AND p.value_id = x.parent_value_id
     WHERE x.attribute_id = a.attribute_id;
    UPDATE g2p_list_versions
       SET status = 'PUBLISHED', published_at = now(), decided_by = p_actor, decided_at = now()
     WHERE list_id = a.attribute_id AND version_no = v;
    UPDATE g2p_attributes SET current_version_no = v WHERE attribute_id = a.attribute_id;
    PERFORM g2p_catalogue_log('list.version.migrated', 'list', a.attribute_id, v, p_actor,
      jsonb_build_object('list_code', coalesce(a.attribute_code, a.attribute_id),
                         'values', (SELECT count(*) FROM g2p_attribute_values y
                                     WHERE y.attribute_id = a.attribute_id)));
    n_lists := n_lists + 1;
  END LOOP;

  IF NOT EXISTS (SELECT 1 FROM g2p_geo_versions) AND EXISTS (SELECT 1 FROM g2p_geo_levels) THEN
    gv := g2p_catalogue_next_geo_version();
    INSERT INTO g2p_geo_versions
      (version_no, status, change_note, effective_from, boundary_objects, created_by, created_at,
       updated_by, updated_at)
    VALUES (gv, 'DRAFT', 'Version 1: migrated from the pre-catalogue tables', eff, '{}'::jsonb,
            p_actor, now(), p_actor, now());
    INSERT INTO g2p_geo_version_levels (version_no, level_id, level_mnemonic, parent_level_id, display)
    SELECT gv, level_id, level_mnemonic, nullif(nullif(parent_level_id, ''), 'NULL'), level_mnemonic
      FROM g2p_geo_levels;
    INSERT INTO g2p_geo_version_units
      (version_no, unit_id, level_id, name, parent_unit_id, status, valid_from)
    SELECT gv, level_value_id, level_id, level_value_mnemonic,
           nullif(nullif(parent_level_value_id, ''), 'NULL'), 'ACTIVE', eff
      FROM g2p_geo_level_values;
    GET DIAGNOSTICS n_units = ROW_COUNT;
    UPDATE g2p_geo_versions
       SET status = 'PUBLISHED', published_at = now(), decided_by = p_actor, decided_at = now()
     WHERE version_no = gv;
    INSERT INTO g2p_catalogue_state (key, int_value, updated_at)
    VALUES ('geo.current_version_no', gv, now())
    ON CONFLICT (key) DO UPDATE SET int_value = gv, updated_at = now();
    PERFORM g2p_catalogue_log('geo.version.migrated', 'geo', 'geography', gv, p_actor,
      jsonb_build_object('units', n_units));
    geo_done := true;
  END IF;

  RETURN jsonb_build_object('lists', n_lists, 'geo', geo_done, 'geo_units', n_units);
END $$
""",
    # ---- future-effective versions coming into effect ------------------------
    # Called on start and periodically by the API (every
    # catalogue_effective_refresh_seconds, so a version comes into effect at most
    # that long after its effective_from). Re-materialises any list (and the
    # geography) whose current version moved because a published version's
    # effective_from has passed, and logs *.version.effective — which the API's
    # outbox relay then forwards to the Audit Manager and WebSub. One caller at
    # a time.
    """
CREATE OR REPLACE FUNCTION g2p_catalogue_refresh_current() RETURNS integer
LANGUAGE plpgsql AS $$
DECLARE
  a record;
  n integer := 0;
  cur integer;
  stored integer;
BEGIN
  IF NOT pg_try_advisory_xact_lock(hashtext('g2p_catalogue_refresh_current')) THEN
    RETURN 0;
  END IF;
  FOR a IN SELECT x.attribute_id, x.current_version_no FROM g2p_attributes x
            WHERE EXISTS (SELECT 1 FROM g2p_list_versions v
                           WHERE v.list_id = x.attribute_id AND v.status = 'PUBLISHED') LOOP
    cur := g2p_catalogue_current_list_version(a.attribute_id);
    IF cur IS NOT NULL AND cur IS DISTINCT FROM a.current_version_no THEN
      PERFORM g2p_catalogue_materialise_list(a.attribute_id);
      PERFORM g2p_catalogue_log('list.version.effective', 'list', a.attribute_id, cur, 'system',
        jsonb_build_object('previous_version_no', a.current_version_no));
      n := n + 1;
    END IF;
  END LOOP;
  cur := g2p_catalogue_current_geo_version();
  SELECT int_value INTO stored FROM g2p_catalogue_state WHERE key = 'geo.current_version_no';
  IF cur IS NOT NULL AND cur IS DISTINCT FROM stored THEN
    PERFORM g2p_catalogue_materialise_geo();
    PERFORM g2p_catalogue_log('geo.version.effective', 'geo', 'geography', cur, 'system',
      jsonb_build_object('previous_version_no', stored));
    n := n + 1;
  END IF;
  RETURN n;
END $$
""",
]

_SCHEMA_MARKER = [
    f"""INSERT INTO g2p_catalogue_state (key, int_value, updated_at)
        VALUES ('schema_version', {CATALOGUE_SCHEMA_VERSION}, now())
        ON CONFLICT (key) DO UPDATE SET int_value = EXCLUDED.int_value, updated_at = now()""",
]


def legacy_alter_statements() -> list[str]:
    return list(_ALTER_LEGACY)


def catalogue_statements() -> list[str]:
    """Indexes, guards, triggers, late columns and functions — after the tables exist."""
    return [*_INDEXES, *_GUARDS, *_TRIGGERS, *_ALTER_CATALOGUE, *_FUNCTIONS]


def schema_marker_statements() -> list[str]:
    return list(_SCHEMA_MARKER)
