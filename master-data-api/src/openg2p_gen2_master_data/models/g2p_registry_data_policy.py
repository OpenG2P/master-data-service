"""Read-only mapping to registry ``g2p_registry_data_policies`` for GEO policy resolution."""

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column
from openg2p_fastapi_common.models import BaseORMModel


class G2PRegistryDataPolicy(BaseORMModel):
    """Registry data policy row (read-only from master-data-service)."""

    __tablename__ = "g2p_registry_data_policies"

    policy_id: Mapped[str] = mapped_column(String, primary_key=True)
    policy_mnemonic: Mapped[str] = mapped_column(String, nullable=False)
    policy_description: Mapped[str | None] = mapped_column(String, nullable=True)
    register_id: Mapped[str | None] = mapped_column(String, nullable=True)
    policy_target: Mapped[str] = mapped_column(String, nullable=False)
    policy_type: Mapped[str] = mapped_column(String, nullable=False)
    policy_filter_expression: Mapped[dict] = mapped_column(JSON, nullable=False)
