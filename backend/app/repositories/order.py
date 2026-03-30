from typing import Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Order, OrderStatus
from app.repositories.base import BaseRepository


class OrderRepository(BaseRepository[Order]):
    def __init__(self, session: AsyncSession):
        super().__init__(Order, session)

    async def get_by_order_number(self, order_number: str) -> Order | None:
        stmt = select(Order).where(Order.order_number == order_number)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_patient(
        self,
        patient_id: UUID,
        *,
        status: OrderStatus | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> tuple[Sequence[Order], int]:
        stmt = select(Order).where(Order.patient_id == patient_id)
        count_stmt = select(func.count()).select_from(Order).where(
            Order.patient_id == patient_id
        )
        if status:
            stmt = stmt.where(Order.status == status)
            count_stmt = count_stmt.where(Order.status == status)
        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar_one()
        stmt = stmt.order_by(Order.created_at.desc()).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all(), total

    async def list_by_companion(
        self,
        companion_id: UUID,
        *,
        status: OrderStatus | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> tuple[Sequence[Order], int]:
        stmt = select(Order).where(Order.companion_id == companion_id)
        count_stmt = select(func.count()).select_from(Order).where(
            Order.companion_id == companion_id
        )
        if status:
            stmt = stmt.where(Order.status == status)
            count_stmt = count_stmt.where(Order.status == status)
        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar_one()
        stmt = stmt.order_by(Order.created_at.desc()).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all(), total

    async def list_available(
        self, *, skip: int = 0, limit: int = 20
    ) -> tuple[Sequence[Order], int]:
        stmt = select(Order).where(Order.status == OrderStatus.created)
        count_stmt = (
            select(func.count())
            .select_from(Order)
            .where(Order.status == OrderStatus.created)
        )
        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar_one()
        stmt = stmt.order_by(Order.created_at.desc()).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all(), total
