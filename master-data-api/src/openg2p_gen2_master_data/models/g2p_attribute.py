from openg2p_fastapi_common.models import BaseORMModel
from sqlalchemy import Boolean, Integer, String
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
