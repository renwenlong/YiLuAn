"""
AdminAuditService — companion audit business logic scaffold (A6).

TODO: implement actual DB queries and state transitions.
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession


class AdminAuditService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_pending_companions(self, page: int = 1, page_size: int = 20):
        # TODO: query CompanionProfile where verification_status == pending, paginated
        raise NotImplementedError("A6 scaffold — list_pending_companions not yet implemented")

    async def approve_companion(self, companion_id: UUID, operator_id: UUID):
        # TODO: set verification_status to verified, record operator audit log
        raise NotImplementedError("A6 scaffold — approve_companion not yet implemented")

    async def reject_companion(self, companion_id: UUID, operator_id: UUID, reason: str):
        # TODO: set verification_status to rejected, record reason + operator audit log
        raise NotImplementedError("A6 scaffold — reject_companion not yet implemented")
