from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.patient_profile import PatientProfile
from app.repositories.base import BaseRepository


class PatientProfileRepository(BaseRepository[PatientProfile]):
    def __init__(self, session: AsyncSession):
        super().__init__(PatientProfile, session)

    async def get_by_user_id(self, user_id: UUID) -> PatientProfile | None:
        stmt = select(PatientProfile).where(PatientProfile.user_id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
