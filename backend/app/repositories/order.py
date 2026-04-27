from datetime import datetime
from decimal import Decimal
from typing import Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.hospital import Hospital
from app.models.order import Order, OrderStatus
from app.models.payment import Payment
from app.repositories.base import BaseRepository


class OrderRepository(BaseRepository[Order]):
    def __init__(self, session: AsyncSession):
        super().__init__(Order, session)

    async def get_by_id_for_update(self, order_id: UUID) -> Order | None:
        stmt = select(Order).where(Order.id == order_id).with_for_update()
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_order_number(self, order_number: str) -> Order | None:
        stmt = select(Order).where(Order.order_number == order_number)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_patient(
        self,
        patient_id: UUID,
        *,
        status: OrderStatus | None = None,
        status_list: list[OrderStatus] | None = None,
        date: str | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> tuple[Sequence[Order], int]:
        stmt = select(Order).where(Order.patient_id == patient_id)
        count_stmt = select(func.count()).select_from(Order).where(
            Order.patient_id == patient_id
        )
        if status_list:
            stmt = stmt.where(Order.status.in_(status_list))
            count_stmt = count_stmt.where(Order.status.in_(status_list))
        elif status:
            stmt = stmt.where(Order.status == status)
            count_stmt = count_stmt.where(Order.status == status)
        if date:
            stmt = stmt.where(Order.appointment_date == date)
            count_stmt = count_stmt.where(Order.appointment_date == date)
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
        status_list: list[OrderStatus] | None = None,
        date: str | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> tuple[Sequence[Order], int]:
        stmt = select(Order).where(Order.companion_id == companion_id)
        count_stmt = select(func.count()).select_from(Order).where(
            Order.companion_id == companion_id
        )
        if status_list:
            stmt = stmt.where(Order.status.in_(status_list))
            count_stmt = count_stmt.where(Order.status.in_(status_list))
        elif status:
            stmt = stmt.where(Order.status == status)
            count_stmt = count_stmt.where(Order.status == status)
        if date:
            stmt = stmt.where(Order.appointment_date == date)
            count_stmt = count_stmt.where(Order.appointment_date == date)
        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar_one()
        stmt = stmt.order_by(Order.created_at.desc()).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all(), total

    async def count_open_by_companion(self, companion_id: UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(Order)
            .where(
                Order.companion_id == companion_id,
                Order.status.in_([OrderStatus.accepted, OrderStatus.in_progress]),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def sum_earnings_by_companion(self, companion_id: UUID) -> Decimal:
        # ADR-0030: 返回 Decimal，避免与 Numeric(10,2) 列做浮点运算
        stmt = select(
            func.coalesce(func.sum(Order.price), 0)
        ).where(
            Order.companion_id == companion_id,
            Order.status.in_([
                OrderStatus.completed,
                OrderStatus.reviewed,
            ]),
        )
        result = await self.session.execute(stmt)
        value = result.scalar_one()
        if isinstance(value, Decimal):
            return value.quantize(Decimal("0.01"))
        return Decimal(str(value)).quantize(Decimal("0.01"))

    async def list_available(
        self, *, skip: int = 0, limit: int = 20, date: str | None = None, city: str | None = None
    ) -> tuple[Sequence[Order], int]:
        stmt = select(Order).where(Order.status == OrderStatus.created)
        count_stmt = (
            select(func.count())
            .select_from(Order)
            .where(Order.status == OrderStatus.created)
        )
        if date:
            stmt = stmt.where(Order.appointment_date == date)
            count_stmt = count_stmt.where(Order.appointment_date == date)
        if city:
            stmt = stmt.join(Hospital, Order.hospital_id == Hospital.id).where(
                Hospital.city == city
            )
            count_stmt = count_stmt.join(
                Hospital, Order.hospital_id == Hospital.id
            ).where(Hospital.city == city)
        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar_one()
        stmt = stmt.order_by(Order.created_at.desc()).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all(), total

    async def list_expired(self, now: datetime) -> Sequence[Order]:
        """Find orders that are created and past their expires_at time."""
        stmt = select(Order).where(
            Order.status == OrderStatus.created,
            Order.expires_at.isnot(None),
            Order.expires_at <= now,
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def has_unpaid_orders(self, patient_id: UUID) -> bool:
        """Check if patient has any created orders without a pay record."""
        paid_order_ids = (
            select(Payment.order_id)
            .where(Payment.payment_type == "pay")
        )
        stmt = (
            select(func.count())
            .select_from(Order)
            .where(
                Order.patient_id == patient_id,
                Order.status == OrderStatus.created,
                Order.id.notin_(paid_order_ids),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one() > 0

    async def list_all(
        self,
        *,
        status: OrderStatus | None = None,
        patient_id: UUID | None = None,
        companion_id: UUID | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> tuple[Sequence[Order], int]:
        """Admin: list all orders with optional filters (status / parties / date range)."""
        where_clause = []
        if status:
            where_clause.append(Order.status == status)
        if patient_id is not None:
            where_clause.append(Order.patient_id == patient_id)
        if companion_id is not None:
            where_clause.append(Order.companion_id == companion_id)
        if date_from is not None:
            where_clause.append(Order.appointment_date >= date_from)
        if date_to is not None:
            where_clause.append(Order.appointment_date <= date_to)

        count_stmt = select(func.count()).select_from(Order)
        if where_clause:
            count_stmt = count_stmt.where(*where_clause)
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = select(Order)
        if where_clause:
            stmt = stmt.where(*where_clause)
        stmt = stmt.order_by(Order.created_at.desc()).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all(), total
