from typing import Sequence
from uuid import UUID

from sqlalchemy import func, literal, select
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
        service_type: str | None = None,
        hospital_id: str | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> Sequence[CompanionProfile]:
        stmt = select(CompanionProfile).where(
            CompanionProfile.verification_status == VerificationStatus.verified
        )
        if area:
            stmt = stmt.where(CompanionProfile.service_area.contains(area))
        if service_type:
            padded = func.concat(literal(","), CompanionProfile.service_types, literal(","))
            stmt = stmt.where(padded.contains("," + service_type + ","))
        if hospital_id:
            h_padded = func.concat(literal(","), CompanionProfile.service_hospitals, literal(","))
            stmt = stmt.where(h_padded.contains("," + hospital_id + ","))
        stmt = stmt.offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()
