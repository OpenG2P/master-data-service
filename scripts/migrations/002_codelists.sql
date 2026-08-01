-- =========================================================================
-- Country code lists: gender, education, crop, programme …
-- =========================================================================
-- A country pack carries more than geography. These tables hold the code lists
-- a deployment offers, so a registry can seed its own copy at install rather
-- than compiling the values into its image — which is what stops one image
-- serving two countries.
--
-- SAFE TO RUN ON A LIVE DEPLOYMENT:
--   * only CREATE TABLE IF NOT EXISTS  -> nothing existing is touched
--   * no change to g2p_geo_*           -> geo endpoints and the registry's
--                                         direct reads are unaffected
--   * idempotent                       -> safe to re-run
--   * rollback is DROP TABLE on these two, geo is untouched
--
-- Nothing reads these until a deployment opts in (geoSeed.load.codelists).
--
-- Apply:
--   psql "$MASTER_DATA_DB_URL" -f 002_codelists.sql
-- =========================================================================

BEGIN;

-- Same table and column names as the registry's own attribute tables, on
-- purpose: the install-time copy is then a straight insert with no mapping.
-- They live in different databases; the connection decides which you get.
CREATE TABLE IF NOT EXISTS g2p_attributes (
    attribute_id        VARCHAR PRIMARY KEY,
    attribute_code      VARCHAR,
    attribute_display   VARCHAR,
    is_hierarchical     BOOLEAN DEFAULT FALSE,

    -- Label i18n, matching what g2p_geo_* already carries. The registry's
    -- version has none, so attribute labels are translated today by a frontend
    -- message catalogue rather than by data.
    display_name_i18n   JSONB,

    -- Which pack, and which version of it, these values came from. Lets a
    -- registry assert it seeded against the pack it expected instead of
    -- assuming, the way the geo rows already allow.
    country             VARCHAR,
    version             VARCHAR,
    valid_from          DATE,
    valid_to            DATE
);

-- The key is COMPOSITE. A value is identified by its list plus its code, not by
-- the code alone: 'OTHER' occurs in 13 of Ethiopia's lists, 'NONE' in 5,
-- 'TEMPORARY' in 3. The registry's own table uses value_id alone, which is why
-- Farmer had to prefix every value (CROP_WHEAT, LSTK_CATTLE) while NSR's stay
-- bare (PIPED, OTHER) — an inconsistency this avoids rather than inherits.
CREATE TABLE IF NOT EXISTS g2p_attribute_values (
    value_id            VARCHAR NOT NULL,
    attribute_id        VARCHAR NOT NULL,
    value_code          VARCHAR,
    value_display       VARCHAR,
    parent_value_id     VARCHAR,
    sort_order          INTEGER,

    display_name_i18n   JSONB,

    -- Semantic roles this value plays — see openg2p-data/packs/roles.json.
    -- Platform logic asks for a role ("the value meaning head of household")
    -- rather than a literal, so a report survives a country that names things
    -- differently. Stored as JSONB because a value may hold several.
    roles               JSONB,

    -- Which domain this list belongs to, e.g. 'agriculture'. NULL means the
    -- core set every registry uses. Lets a registry seed only what it needs.
    domain              VARCHAR,

    country             VARCHAR,
    version             VARCHAR,
    valid_from          DATE,
    valid_to            DATE,

    PRIMARY KEY (attribute_id, value_id)
);

CREATE INDEX IF NOT EXISTS ix_g2p_attributes_code
    ON g2p_attributes (attribute_code);
CREATE INDEX IF NOT EXISTS ix_g2p_attribute_values_attribute_id
    ON g2p_attribute_values (attribute_id);
CREATE INDEX IF NOT EXISTS ix_g2p_attribute_values_parent
    ON g2p_attribute_values (parent_value_id);
CREATE INDEX IF NOT EXISTS ix_g2p_attribute_values_domain
    ON g2p_attribute_values (domain);

COMMIT;
