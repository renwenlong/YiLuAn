from typing import Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.review import Review
from app.repositories.base import BaseRepository


class ReviewRepository(BaseRepository[Review]):
    def __init__(self, session: AsyncSession):
        super().__init__(Review, session)

    async def get_by_order_id(self, order_id: UUID) -> Review | None:
        stmt = select(Review).where(Review.order_id == order_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_companion(
        self,
        companion_id: UUID,
        *,
        skip: int = 0,
        limit: int = 20,
    ) -> tuple[Sequence[Review], int]:
        base = select(Review).where(Review.companion_id == companion_id)
        count_stmt = select(func.count()).select_from(base.subquery())
        total = (await self.session.execute(count_stmt)).scalar() or 0

        stmt = base.order_by(Review.created_at.desc()).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all(), total

    async def get_companion_avg_rating(self, companion_id: UUID) -> float:
        stmt = select(func.avg(Review.rating)).where(
            Review.companion_id == companion_id
        )
        result = await self.session.execute(stmt)
        return float(result.scalar() or 0.0)
