-- =========================================================================
-- Geo hierarchy: P-codes, boundary references, display labels, versioning
-- =========================================================================
-- Adds the columns needed for reliable hierarchical drill-down and choropleth
-- rendering (consumed by G2P Insight).
--
-- SAFE TO RUN ON A LIVE DEPLOYMENT:
--   * every column is NULLABLE with no default  -> no table rewrite, no lock
--     beyond a brief ACCESS EXCLUSIVE for the catalog update
--   * nothing is renamed or dropped             -> existing consumers unaffected
--   * idempotent (IF NOT EXISTS)                -> safe to re-run
--
-- Apply:
--   psql "$MASTER_DATA_DB_URL" -f 001_geo_pcode_boundaries.sql
-- =========================================================================

BEGIN;

-- ---------------------------------------------------------------- levels --
ALTER TABLE g2p_geo_levels
    -- Translatable label for the level itself ("Province", not "province").
    ADD COLUMN IF NOT EXISTS display_name       varchar,
    ADD COLUMN IF NOT EXISTS display_name_i18n  jsonb,
    -- Structure vintage: admin structures change (regions split/merge), so a
    -- report must be able to state which version it was drawn against.
    ADD COLUMN IF NOT EXISTS version            varchar,
    ADD COLUMN IF NOT EXISTS valid_from         date,
    ADD COLUMN IF NOT EXISTS valid_to           date;

CREATE INDEX IF NOT EXISTS ix_g2p_geo_levels_version
    ON g2p_geo_levels (version);

-- ---------------------------------------------------------- level values --
ALTER TABLE g2p_geo_level_values
    -- Official administrative P-code. `level_value_id` stays the internal key;
    -- `pcode` is the join key to boundary files and registry data. Name-based
    -- joins measured only ~76% exact / 91% fuzzy against real data, with
    -- geographically WRONG matches where names recur under different parents.
    ADD COLUMN IF NOT EXISTS pcode                    varchar,
    ADD COLUMN IF NOT EXISTS pcode_source             varchar,
    -- Pointers to boundary geometry. The geometry is NOT stored here; the
    -- referenced GeoJSON MUST carry the same `pcode` as a feature property.
    ADD COLUMN IF NOT EXISTS boundary_uri             varchar,
    ADD COLUMN IF NOT EXISTS boundary_simplified_uri  varchar,
    -- `level_value_mnemonic` is a slug; these are the presentable labels.
    ADD COLUMN IF NOT EXISTS display_name             varchar,
    ADD COLUMN IF NOT EXISTS display_name_i18n        jsonb,
    ADD COLUMN IF NOT EXISTS version                  varchar,
    ADD COLUMN IF NOT EXISTS valid_from               date,
    ADD COLUMN IF NOT EXISTS valid_to                 date;

CREATE INDEX IF NOT EXISTS ix_g2p_geo_level_values_pcode
    ON g2p_geo_level_values (pcode);

CREATE INDEX IF NOT EXISTS ix_g2p_geo_level_values_version
    ON g2p_geo_level_values (version);

-- A pcode must be unique within a level for a given structure version.
-- Partial so the many existing NULL-pcode rows are ignored until backfilled.
CREATE UNIQUE INDEX IF NOT EXISTS uq_g2p_geo_level_values_pcode_level_version
    ON g2p_geo_level_values (level_id, pcode, version)
    WHERE pcode IS NOT NULL;

COMMIT;

-- =========================================================================
-- Backfill (per deployment — NOT part of this migration)
-- =========================================================================
-- 1. Populate `pcode` from the national statistics agency codes, or OCHA/HDX
--    COD-AB as a fallback. Do NOT derive pcodes from names.
-- 2. Upload boundary GeoJSON (per country/level/version) to object storage and
--    set `boundary_uri` / `boundary_simplified_uri`. Each feature must carry
--    its `pcode` as a property.
-- 3. Set `display_name` (and `display_name_i18n` where localisation is needed).
-- 4. Stamp `version` / `valid_from` on the current structure so future changes
--    can be dated rather than silently overwriting history.
--
-- Until pcode is backfilled, G2P Insight falls back to matching on the leaf
-- token of `level_value_id`, which is explicitly marked as unreliable.
-- =========================================================================
