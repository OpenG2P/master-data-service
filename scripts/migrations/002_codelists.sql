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

-- Attribute catalog owned by Master Data and consumed through its API.
CREATE TABLE IF NOT EXISTS g2p_attributes (
    attribute_id        VARCHAR PRIMARY KEY,
    attribute_code      VARCHAR,
    attribute_display   VARCHAR,
    is_hierarchical     BOOLEAN DEFAULT FALSE
);

-- The key is COMPOSITE. A value is identified by its list plus its code, not by
-- the code alone: 'OTHER' occurs in 13 of Ethiopia's lists, 'NONE' in 5,
-- and 'TEMPORARY' in 3.
CREATE TABLE IF NOT EXISTS g2p_attribute_values (
    value_id            VARCHAR NOT NULL,
    attribute_id        VARCHAR NOT NULL,
    value_code          VARCHAR,
    value_display       VARCHAR,
    parent_value_id     VARCHAR,
    sort_order          INTEGER,

    PRIMARY KEY (attribute_id, value_id)
);

CREATE INDEX IF NOT EXISTS ix_g2p_attributes_code
    ON g2p_attributes (attribute_code);
CREATE INDEX IF NOT EXISTS ix_g2p_attribute_values_attribute_id
    ON g2p_attribute_values (attribute_id);
CREATE INDEX IF NOT EXISTS ix_g2p_attribute_values_parent
    ON g2p_attribute_values (parent_value_id);

COMMIT;
