from typing import Sequence
from uuid import UUID

from sqlalchemy import func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.companion_profile import CompanionProfile, VerificationStatus
from app.repositories.base import BaseRepository


class CompanionProfileRepository(BaseRepository[CompanionProfile]):
    def __init__(self, session: AsyncSession):
        super().__init__(CompanionProfile, session)

    async def get_by_user_id(self, user_id: UUID) -> CompanionProfile | None:
        stmt = select(CompanionProfile).where(CompanionProfile.user_id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def search(
        self,
        *,
        area: str | None = None,
        city: str | None = None,
        service_type: str | None = None,
        hospital_id: str | None = None,
        hospital_district: str | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> Sequence[CompanionProfile]:
        stmt = select(CompanionProfile).where(
            CompanionProfile.verification_status == VerificationStatus.verified
        )
        if area:
            stmt = stmt.where(CompanionProfile.service_area.contains(area))
        if city:
            stmt = stmt.where(CompanionProfile.service_city == city)
        if service_type:
            padded = func.concat(literal(","), CompanionProfile.service_types, literal(","))
            stmt = stmt.where(padded.contains("," + service_type + ","))
        if hospital_id:
            h_padded = func.concat(
                literal(","), CompanionProfile.service_hospitals, literal(",")
            )
            exact_match = h_padded.contains("," + hospital_id + ",")
            if hospital_district:
                # Fallback: match by district when service_hospitals is not set
                district_match = CompanionProfile.service_area.contains(hospital_district)
                no_hospitals = or_(
                    CompanionProfile.service_hospitals.is_(None),
                    CompanionProfile.service_hospitals == "",
                )
                stmt = stmt.where(or_(exact_match, (no_hospitals & district_match)))
            else:
                stmt = stmt.where(exact_match)
        stmt = stmt.offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()
