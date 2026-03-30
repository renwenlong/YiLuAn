from typing import Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.hospital import Hospital
from app.repositories.base import BaseRepository


class HospitalRepository(BaseRepository[Hospital]):
    def __init__(self, session: AsyncSession):
        super().__init__(Hospital, session)

    async def search(
        self,
        *,
        keyword: str | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> tuple[Sequence[Hospital], int]:
        stmt = select(Hospital)
        count_stmt = select(func.count()).select_from(Hospital)

        if keyword:
            stmt = stmt.where(Hospital.name.contains(keyword))
            count_stmt = count_stmt.where(Hospital.name.contains(keyword))

        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar_one()

        stmt = stmt.offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all(), total
