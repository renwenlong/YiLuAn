from decimal import Decimal
from typing import Sequence

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payment import Payment
from app.models.user import User, UserRole
from app.models.wallet_ledger import WalletLedger, WalletLedgerDirection
from app.repositories.order import OrderRepository
from app.repositories.payment import PaymentRepository


_ZERO = Decimal("0.00")


class WalletService:
    """[ADR-0032 §3.5] 钱包服务。

    ``get_summary`` 优先走 ``wallet_ledger``（追加式账本，``SUM(amount * sign)``）；
    若账本为空（首次部署 / 未 backfill），回退到原 ``OrderRepository.sum_earnings_by_companion``
    保持向后兼容，绝不让钱包数字突然清零。
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.payment_repo = PaymentRepository(session)
        self.order_repo = OrderRepository(session)

    async def get_summary(self, user: User) -> dict:
        if user.role != UserRole.companion:
            return {"balance": _ZERO, "total_income": _ZERO, "withdrawn": _ZERO}

        balance = await self._sum_from_ledger(user)
        if balance is None:
            # fallback：账本表为空 → 走旧实现
            total_income = await self.order_repo.sum_earnings_by_companion(user.id)
            return {
                "balance": total_income,
                "total_income": total_income,
                "withdrawn": _ZERO,
            }
        return {
            "balance": balance,
            "total_income": balance,
            "withdrawn": _ZERO,
        }

    async def _sum_from_ledger(self, user: User) -> Decimal | None:
        """账本聚合：``SUM(amount * sign(direction))``。

        返回 None 表示账本表里这位用户**一条都没有**——交给 fallback 决定。
        """
        # 先看是否有任何 ledger 记录；空集合走 fallback
        exists_stmt = select(func.count()).select_from(WalletLedger).where(
            WalletLedger.user_id == user.id
        )
        exists_count = (await self.session.execute(exists_stmt)).scalar_one()
        if exists_count == 0:
            return None

        sign_expr = case(
            (WalletLedger.direction == WalletLedgerDirection.in_, 1),
            else_=-1,
        )
        stmt = select(
            func.coalesce(func.sum(WalletLedger.amount * sign_expr), 0)
        ).where(WalletLedger.user_id == user.id)
        value = (await self.session.execute(stmt)).scalar_one()
        if isinstance(value, Decimal):
            return value.quantize(Decimal("0.01"))
        return Decimal(str(value)).quantize(Decimal("0.01"))

    async def get_transactions(
        self, user: User, *, page: int = 1, page_size: int = 20
    ) -> tuple[Sequence[Payment], int]:
        skip = (page - 1) * page_size
        return await self.payment_repo.list_by_user(
            user.id, skip=skip, limit=page_size
        )
