from typing import Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import error_codes
from app.exceptions import BadRequestException, ConflictException, ForbiddenException, NotFoundException
from app.models.companion_profile import CompanionProfile
from app.models.user import User, UserRole
from app.repositories.companion_profile import CompanionProfileRepository
from app.repositories.hospital import HospitalRepository
from app.repositories.order import OrderRepository
from app.repositories.review import ReviewRepository
from app.repositories.user import UserRepository
from app.schemas.companion import ApplyCompanionRequest, UpdateCompanionProfileRequest


class CompanionProfileService:
    def __init__(self, session: AsyncSession):
        self.repo = CompanionProfileRepository(session)
        self.user_repo = UserRepository(session)
        self.order_repo = OrderRepository(session)
        self.review_repo = ReviewRepository(session)
        self.hospital_repo = HospitalRepository(session)
        self.session = session

    async def apply(self, user: User, data: ApplyCompanionRequest) -> CompanionProfile:
        # 前置：申请陪诊师资质前必须已绑定手机号（实名联系方式刚需）
        if not user.phone:
            raise BadRequestException(
                "请先绑定手机号后再申请陪诊师资质",
                error_code=error_codes.PHONE_REQUIRED,
            )
        existing = await self.repo.get_by_user_id(user.id)
        if existing is not None:
            raise ConflictException(
                "Companion profile already exists",
                error_code=error_codes.COMPANION_PROFILE_EXISTS,
            )

        profile = CompanionProfile(
            user_id=user.id,
            real_name=data.real_name,
            id_number=data.id_number,
            certifications=data.certifications,
            service_area=data.service_area,
            service_types=data.service_types,
            service_hospitals=data.service_hospitals,
            service_city=data.service_city,
            bio=data.bio,
        )
        profile = await self.repo.create(profile)

        if user.role is None:
            await self.user_repo.update(user, {"role": UserRole.companion})
        user.add_role(UserRole.companion)
        await self.user_repo.update(user, {"roles": user.roles})

        return profile

    async def update_profile(
        self, user_id: UUID, data: UpdateCompanionProfileRequest, display_name: str | None = None
    ) -> CompanionProfile:
        profile = await self.repo.get_by_user_id(user_id)
        if profile is None:
            # Auto-create profile for users with companion role but no profile record
            real_name = display_name or "未填写"
            update_data = data.model_dump(exclude_unset=True)
            profile = CompanionProfile(
                user_id=user_id,
                real_name=real_name,
                **{k: v for k, v in update_data.items() if v is not None},
            )
            return await self.repo.create(profile)
        update_data = data.model_dump(exclude_unset=True)
        if not update_data:
            return profile
        return await self.repo.update(profile, update_data)

    async def get_detail(self, companion_id: UUID) -> CompanionProfile:
        profile = await self.repo.get_by_id(companion_id)
        if profile is None:
            raise NotFoundException("Companion not found")
        # F-04: attach dimension averages so CompanionDetailResponse can
        # populate `dimension_scores` via from_attributes.
        scores = await self.review_repo.get_companion_dimension_averages(profile.user_id)
        # Round to 1 decimal for nicer display; pydantic will cast to float.
        profile.dimension_scores = {  # type: ignore[attr-defined]
            "punctuality": round(scores["punctuality"], 2),
            "professionalism": round(scores["professionalism"], 2),
            "communication": round(scores["communication"], 2),
            "attitude": round(scores["attitude"], 2),
        }
        return profile

    async def get_detail_by_user(self, user_id: UUID, display_name: str | None = None) -> CompanionProfile:
        profile = await self.repo.get_by_user_id(user_id)
        if profile is None:
            # Auto-create profile for users with companion role but no profile record
            real_name = display_name or "未填写"
            profile = CompanionProfile(user_id=user_id, real_name=real_name)
            profile = await self.repo.create(profile)
        scores = await self.review_repo.get_companion_dimension_averages(user_id)
        profile.dimension_scores = {  # type: ignore[attr-defined]
            "punctuality": round(scores["punctuality"], 2),
            "professionalism": round(scores["professionalism"], 2),
            "communication": round(scores["communication"], 2),
            "attitude": round(scores["attitude"], 2),
        }
        return profile

    async def list_companions(
        self,
        *,
        area: str | None = None,
        city: str | None = None,
        service_type: str | None = None,
        hospital_id: str | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> Sequence[CompanionProfile]:
        hospital_district: str | None = None
        if hospital_id:
            hospital = await self.hospital_repo.get_by_id(UUID(hospital_id))
            if hospital and hospital.district:
                hospital_district = hospital.district
        return await self.repo.search(
            area=area,
            city=city,
            service_type=service_type,
            hospital_id=hospital_id,
            hospital_district=hospital_district,
            skip=skip,
            limit=limit,
        )

    async def get_stats(self, user: User) -> dict:
        if not user.has_role(UserRole.companion):
            raise ForbiddenException("Only companions can view stats")
        profile = await self.repo.get_by_user_id(user.id)
        if profile:
            avg_rating = profile.avg_rating
            total_orders = profile.total_orders
        else:
            # Fallback: query reviews directly for companions without profile
            avg_rating = await self.review_repo.get_companion_avg_rating(user.id)
            total_orders = await self.review_repo.count_by_companion(user.id)

        open_orders = await self.order_repo.count_open_by_companion(user.id)
        total_earnings = await self.order_repo.sum_earnings_by_companion(user.id)

        return {
            "open_orders": open_orders,
            "total_orders": total_orders,
            "avg_rating": avg_rating,
            "total_earnings": total_earnings,
        }
