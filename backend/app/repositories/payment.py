from typing import Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order_status_history import OrderStatusHistory
from app.models.payment import Payment
from app.repositories.base import BaseRepository


class OrderStatusHistoryRepository(BaseRepository[OrderStatusHistory]):
    def __init__(self, session: AsyncSession):
        super().__init__(OrderStatusHistory, session)

    async def list_by_order_id(
        self, order_id: UUID
    ) -> Sequence[OrderStatusHistory]:
        stmt = (
            select(OrderStatusHistory)
            .where(OrderStatusHistory.order_id == order_id)
            .order_by(OrderStatusHistory.created_at.asc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()


class PaymentRepository(BaseRepository[Payment]):
    def __init__(self, session: AsyncSession):
        super().__init__(Payment, session)

    async def get_by_order_id(self, order_id: UUID) -> Payment | None:
        stmt = select(Payment).where(Payment.order_id == order_id).limit(1)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_order_and_type(
        self, order_id: UUID, payment_type: str
    ) -> Payment | None:
        stmt = select(Payment).where(
            Payment.order_id == order_id,
            Payment.payment_type == payment_type,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_order_id(self, order_id: UUID) -> Sequence[Payment]:
        stmt = select(Payment).where(Payment.order_id == order_id)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def list_by_user(
        self, user_id: UUID, *, skip: int = 0, limit: int = 20
    ) -> tuple[Sequence[Payment], int]:
        count_stmt = (
            select(func.count())
            .select_from(Payment)
            .where(Payment.user_id == user_id)
        )
        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar_one()
        stmt = (
            select(Payment)
            .where(Payment.user_id == user_id)
            .order_by(Payment.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all(), total
