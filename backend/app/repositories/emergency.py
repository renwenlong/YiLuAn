"""[F-03] Emergency repositories."""
from uuid import UUID
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.emergency import EmergencyContact, EmergencyEvent
from app.repositories.base import BaseRepository


class EmergencyContactRepository(BaseRepository[EmergencyContact]):
    def __init__(self, session: AsyncSession):
        super().__init__(EmergencyContact, session)

    async def list_by_user(self, user_id: UUID) -> Sequence[EmergencyContact]:
        stmt = (
            select(EmergencyContact)
            .where(EmergencyContact.user_id == user_id)
            .order_by(EmergencyContact.created_at.asc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def count_by_user(self, user_id: UUID) -> int:
        contacts = await self.list_by_user(user_id)
        return len(contacts)


class EmergencyEventRepository(BaseRepository[EmergencyEvent]):
    def __init__(self, session: AsyncSession):
        super().__init__(EmergencyEvent, session)

    async def list_by_patient(self, patient_id: UUID) -> Sequence[EmergencyEvent]:
        stmt = (
            select(EmergencyEvent)
            .where(EmergencyEvent.patient_id == patient_id)
            .order_by(EmergencyEvent.triggered_at.desc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()
