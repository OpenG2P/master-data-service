from typing import Optional

from openg2p_fastapi_common.models import BaseORMModel
from sqlalchemy import Boolean, Integer, String, Text
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
# ---------------------------------------------------------------------------


class G2PAttribute(BaseORMModel):
    __tablename__ = "g2p_attributes"

    attribute_id: Mapped[str] = mapped_column(String, primary_key=True)
    attribute_code: Mapped[str] = mapped_column(String, nullable=True, index=True)
    attribute_display: Mapped[str] = mapped_column(String, nullable=True)
    is_hierarchical: Mapped[bool] = mapped_column(Boolean, nullable=True, default=False)

    # Catalogue columns. This table is the list registry AND the materialised
    # current published state of each list: code, display, display_i18n,
    # is_hierarchical and attribute_schema are refreshed from the current
    # published version on every publish (see g2p_list_versions). description
    # and owner_org are administrative, not versioned. Added to an existing
    # table by ALTER ... ADD COLUMN IF NOT EXISTS in migrate_database.
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    display_i18n: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    attribute_schema: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # Department that owns the list; used for approval routing and shown in the UI.
    owner_org: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Pack domain the list belongs to ("core", "agriculture", ...), set by the
    # country-pack loader or by the maker; NULL for lists of unknown origin.
    # Administrative, like owner_org: a filter in the UI, not versioned.
    domain: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # The published version the legacy rows currently show (latest published
    # version whose effective_from has passed). NULL until first published.
    current_version_no: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)


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
