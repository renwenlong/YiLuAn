from typing import Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import ConflictException, ForbiddenException, NotFoundException
from app.models.companion_profile import CompanionProfile
from app.models.user import User, UserRole
from app.repositories.companion_profile import CompanionProfileRepository
from app.repositories.order import OrderRepository
from app.repositories.user import UserRepository
from app.schemas.companion import ApplyCompanionRequest, UpdateCompanionProfileRequest


class CompanionProfileService:
    def __init__(self, session: AsyncSession):
        self.repo = CompanionProfileRepository(session)
        self.user_repo = UserRepository(session)
        self.order_repo = OrderRepository(session)
        self.session = session

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
        user.add_role(UserRole.companion)
        await self.user_repo.update(user, {"roles": user.roles})

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
        service_type: str | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> Sequence[CompanionProfile]:
        return await self.repo.search(area=area, service_type=service_type, skip=skip, limit=limit)

    async def get_stats(self, user: User) -> dict:
        if not user.has_role(UserRole.companion):
            raise ForbiddenException("Only companions can view stats")
        profile = await self.repo.get_by_user_id(user.id)
        avg_rating = 0.0
        total_orders = 0
        if profile:
            avg_rating = profile.avg_rating
            total_orders = profile.total_orders

        open_orders = await self.order_repo.count_open_by_companion(user.id)
        total_earnings = await self.order_repo.sum_earnings_by_companion(user.id)

        return {
            "open_orders": open_orders,
            "total_orders": total_orders,
            "avg_rating": avg_rating,
            "total_earnings": total_earnings,
        }
