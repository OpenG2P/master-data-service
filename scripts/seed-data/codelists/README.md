# Legacy code-list SQL

These fixtures were moved from registry extensions when attribute storage moved
to Master Data. They target the Master Data `g2p_attributes` and
`g2p_attribute_values` schema created by `scripts/migrations/002_codelists.sql`.

Country-pack JSON under `openg2p-data/packs` remains the preferred deployment
seed source. These SQL files preserve the earlier core, social-registry, and
agriculture fixtures for migration and compatibility use.

The `social-legacy` fixture comes from the older standalone NSR extension and is
kept separately because it differs from the current social fixture.
