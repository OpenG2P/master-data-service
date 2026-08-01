from datetime import date

from openg2p_fastapi_common.models import BaseORMModel
from sqlalchemy import Boolean, Date, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

# ---------------------------------------------------------------------------
# Country code lists.
#
# The values a deployment offers — gender, education level, crop, programme —
# come from its country pack, not from a registry's compiled enums. A universal
# superset was considered and does not exist: countries define genuinely
# different taxonomies rather than subsets of one, gender being the clearest
# case. So a registry seeds its own copy from here at install and validates
# against that copy, which is what lets one registry image serve any country.
#
# Everything here is additive. No existing table, endpoint or consumer changes,
# and nothing reads these until a deployment opts in.
# ---------------------------------------------------------------------------


class G2PAttribute(BaseORMModel):
    __tablename__ = "g2p_attributes"

    attribute_id: Mapped[str] = mapped_column(String, primary_key=True)
    attribute_code: Mapped[str] = mapped_column(String, nullable=True, index=True)
    attribute_display: Mapped[str] = mapped_column(String, nullable=True)
    is_hierarchical: Mapped[bool] = mapped_column(Boolean, nullable=True, default=False)

    display_name_i18n: Mapped[dict] = mapped_column(JSONB, nullable=True)

    # Provenance, so a registry can assert it seeded against the pack it meant
    # to rather than assume — the same guarantee the geo rows already give.
    country: Mapped[str] = mapped_column(String, nullable=True, index=True)
    version: Mapped[str] = mapped_column(String, nullable=True, index=True)
    valid_from: Mapped[date] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date] = mapped_column(Date, nullable=True)


class G2PAttributeValue(BaseORMModel):
    __tablename__ = "g2p_attribute_values"

    # Composite key: a value is its list plus its code. 'OTHER' appears in 13 of
    # Ethiopia's lists, so the code alone cannot identify it — the registry's
    # flat key is exactly why Farmer prefixes every value and NSR does not.
    value_id: Mapped[str] = mapped_column(String, primary_key=True)
    attribute_id: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    value_code: Mapped[str] = mapped_column(String, nullable=True)
    value_display: Mapped[str] = mapped_column(String, nullable=True)
    parent_value_id: Mapped[str] = mapped_column(String, nullable=True, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=True)

    display_name_i18n: Mapped[dict] = mapped_column(JSONB, nullable=True)

    # Semantic roles — see openg2p-data/packs/roles.json. Logic asks for the
    # role, never the literal: `is_head` written as
    # `relationship_to_head = 'SELF'` reads false for every household the moment
    # a country names that value differently, and it fails silently.
    roles: Mapped[list] = mapped_column(JSONB, nullable=True)

    # NULL for the core lists; 'agriculture' and the like for domain lists, so a
    # registry seeds only the domains it serves.
    domain: Mapped[str] = mapped_column(String, nullable=True, index=True)

    country: Mapped[str] = mapped_column(String, nullable=True, index=True)
    version: Mapped[str] = mapped_column(String, nullable=True, index=True)
    valid_from: Mapped[date] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date] = mapped_column(Date, nullable=True)
