from typing import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payment import Payment
from app.models.user import User, UserRole
from app.repositories.order import OrderRepository
from app.repositories.payment import PaymentRepository


class WalletService:
    def __init__(self, session: AsyncSession):
        self.payment_repo = PaymentRepository(session)
        self.order_repo = OrderRepository(session)

    async def get_summary(self, user: User) -> dict:
        if user.role == UserRole.companion:
            total_income = await self.order_repo.sum_earnings_by_companion(user.id)
            return {
                "balance": total_income,
                "total_income": total_income,
                "withdrawn": 0.0,
            }
        return {"balance": 0.0, "total_income": 0.0, "withdrawn": 0.0}

    async def get_transactions(
        self, user: User, *, page: int = 1, page_size: int = 20
    ) -> tuple[Sequence[Payment], int]:
        skip = (page - 1) * page_size
        return await self.payment_repo.list_by_user(
            user.id, skip=skip, limit=page_size
        )
