import uuid
from sqlalchemy import String, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from openg2p_fastapi_common.models import BaseORMModel


class G2PPartner(BaseORMModel):
    """Model for G2P Partners - renamed from IncomingPartner"""
    
    __tablename__ = "g2p_partners"

    partner_id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    partner_mnemonic: Mapped[str] = mapped_column(
        String, nullable=False, unique=True, index=True
    )
    keymanager_reference_id: Mapped[str] = mapped_column(
        String, nullable=False, unique=True, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

