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

    async def get_companion_dimension_averages(
        self, companion_id: UUID
    ) -> dict[str, float]:
        """返回 F-04 四个维度的平均分（无评价时均为 0.0）。

        旧数据迁移后维度列会被回填为原 rating，但为防御未迁移 / 边界场景，
        AVG 在遇到 NULL 时会自动忽略，COALESCE 到 0。
        """
        from app.models.review import Review as _R

        stmt = select(
            func.coalesce(func.avg(_R.punctuality_rating), 0.0),
            func.coalesce(func.avg(_R.professionalism_rating), 0.0),
            func.coalesce(func.avg(_R.communication_rating), 0.0),
            func.coalesce(func.avg(_R.attitude_rating), 0.0),
        ).where(_R.companion_id == companion_id)
        row = (await self.session.execute(stmt)).one()
        return {
            "punctuality": float(row[0] or 0.0),
            "professionalism": float(row[1] or 0.0),
            "communication": float(row[2] or 0.0),
            "attitude": float(row[3] or 0.0),
        }

    async def count_by_companion(self, companion_id: UUID) -> int:
        stmt = select(func.count()).where(Review.companion_id == companion_id)
        result = await self.session.execute(stmt)
        return result.scalar() or 0
