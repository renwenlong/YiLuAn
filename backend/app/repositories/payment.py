from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order_status_history import OrderStatusHistory
from app.models.payment import Payment
from app.repositories.base import BaseRepository


class OrderStatusHistoryRepository(BaseRepository[OrderStatusHistory]):
    def __init__(self, session: AsyncSession):
        super().__init__(OrderStatusHistory, session)


class PaymentRepository(BaseRepository[Payment]):
    def __init__(self, session: AsyncSession):
        super().__init__(Payment, session)

    async def get_by_order_id(self, order_id: UUID) -> Payment | None:
        from sqlalchemy import select

        stmt = select(Payment).where(Payment.order_id == order_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
