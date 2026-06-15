import logging
from typing import List, Optional
from sqlalchemy import select
from openg2p_fastapi_common.service import BaseService

from ..engine import get_session_maker
from ..models import G2PPartner
from ..schemas import G2PPartnerData

_config = None
try:
    from ..config import Settings

    _config = Settings.get_config()
except Exception:
    pass

_logger = logging.getLogger(_config.logging_default_logger_name if _config else "g2p-partner-service")


class G2PPartnerService(BaseService):
    async def get_all_partners(self) -> List[G2PPartnerData]:
        """
        Get all G2P partners.

        Returns:
            List of G2PPartnerData
        """
        async with get_session_maker()() as session:
            query = select(G2PPartner)
            result = await session.execute(query)
            partners = result.scalars().all()

            return [
                G2PPartnerData(
                    partner_id=partner.partner_id,
                    partner_mnemonic=partner.partner_mnemonic,
                    keymanager_reference_id=partner.keymanager_reference_id,
                    is_active=partner.is_active,
                )
                for partner in partners
            ]

    async def get_partner(self, partner_id: str) -> Optional[G2PPartnerData]:
        """
        Get a specific G2P partner by ID.

        Args:
            partner_id: The partner ID to retrieve

        Returns:
            G2PPartnerData if found, None otherwise
        """
        async with get_session_maker()() as session:
            partner = await session.get(G2PPartner, partner_id)

            if partner is None:
                return None

            return G2PPartnerData(
                partner_id=partner.partner_id,
                partner_mnemonic=partner.partner_mnemonic,
                keymanager_reference_id=partner.keymanager_reference_id,
                is_active=partner.is_active,
            )
