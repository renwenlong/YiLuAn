from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.patient_profile import PatientProfile
from app.repositories.patient_profile import PatientProfileRepository
from app.schemas.patient import UpdatePatientProfileRequest


class PatientProfileService:
    def __init__(self, session: AsyncSession):
        self.repo = PatientProfileRepository(session)

    async def get_or_create(self, user_id: UUID) -> PatientProfile:
        profile = await self.repo.get_by_user_id(user_id)
        if profile is None:
            profile = PatientProfile(user_id=user_id)
            profile = await self.repo.create(profile)
        return profile

    async def update_profile(
        self, user_id: UUID, data: UpdatePatientProfileRequest
    ) -> PatientProfile:
        profile = await self.get_or_create(user_id)
        update_data = data.model_dump(exclude_unset=True)
        if not update_data:
            return profile
        return await self.repo.update(profile, update_data)
