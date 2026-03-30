from typing import Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import ConflictException, ForbiddenException, NotFoundException
from app.models.companion_profile import CompanionProfile
from app.models.user import User, UserRole
from app.repositories.companion_profile import CompanionProfileRepository
from app.repositories.user import UserRepository
from app.schemas.companion import ApplyCompanionRequest, UpdateCompanionProfileRequest


class CompanionProfileService:
    def __init__(self, session: AsyncSession):
        self.repo = CompanionProfileRepository(session)
        self.user_repo = UserRepository(session)

    async def apply(self, user: User, data: ApplyCompanionRequest) -> CompanionProfile:
        existing = await self.repo.get_by_user_id(user.id)
        if existing is not None:
            raise ConflictException("Companion profile already exists")

        profile = CompanionProfile(
            user_id=user.id,
            real_name=data.real_name,
            id_number=data.id_number,
            certifications=data.certifications,
            service_area=data.service_area,
            bio=data.bio,
        )
        profile = await self.repo.create(profile)

        if user.role is None:
            await self.user_repo.update(user, {"role": UserRole.companion})

        return profile

    async def update_profile(
        self, user_id: UUID, data: UpdateCompanionProfileRequest
    ) -> CompanionProfile:
        profile = await self.repo.get_by_user_id(user_id)
        if profile is None:
            raise NotFoundException("Companion profile not found")
        update_data = data.model_dump(exclude_unset=True)
        if not update_data:
            return profile
        return await self.repo.update(profile, update_data)

    async def get_detail(self, companion_id: UUID) -> CompanionProfile:
        profile = await self.repo.get_by_id(companion_id)
        if profile is None:
            raise NotFoundException("Companion not found")
        return profile

    async def list_companions(
        self,
        *,
        area: str | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> Sequence[CompanionProfile]:
        return await self.repo.search(area=area, skip=skip, limit=limit)
