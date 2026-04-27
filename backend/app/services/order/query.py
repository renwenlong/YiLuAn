"""Read-side operations for OrderService: get_order, list_orders."""
from __future__ import annotations

import uuid
from typing import Sequence

from app.exceptions import ForbiddenException, NotFoundException
from app.models.order import Order, OrderStatus
from app.models.user import User, UserRole

from ._base import _OrderServiceBase


class _OrderQueryMixin(_OrderServiceBase):
    async def get_order(self, order_id: uuid.UUID, user: User) -> Order:
        order = await self.order_repo.get_by_id(order_id)
        if order is None:
            raise NotFoundException("Order not found")
        if user.role == UserRole.patient and order.patient_id != user.id:
            raise ForbiddenException("Not your order")
        if (
            user.role == UserRole.companion
            and order.companion_id is not None
            and order.companion_id != user.id
            and order.status != OrderStatus.created
        ):
            raise ForbiddenException("Not your order")
        await self._fill_payment_status(order)
        await self._fill_timeline(order)
        return order

    async def list_orders(
        self,
        user: User,
        *,
        status: str | None = None,
        date: str | None = None,
        city: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[Sequence[Order], int]:
        skip = (page - 1) * page_size

        # Virtual status: "cancelled" maps to both cancellation types
        if status == "cancelled":
            order_status = None
            status_list = [
                OrderStatus.cancelled_by_patient,
                OrderStatus.cancelled_by_companion,
                OrderStatus.rejected_by_companion,
                OrderStatus.expired,
            ]
        # Virtual status: "completed" includes reviewed orders
        elif status == "completed":
            order_status = None
            status_list = [
                OrderStatus.completed,
                OrderStatus.reviewed,
            ]
        # Virtual status: "in_progress" includes accepted orders
        elif status == "in_progress":
            order_status = None
            status_list = [
                OrderStatus.accepted,
                OrderStatus.in_progress,
            ]
        else:
            order_status = OrderStatus(status) if status else None
            status_list = None

        if user.role == UserRole.companion:
            if order_status == OrderStatus.created:
                items, total = await self.order_repo.list_available(skip=skip, limit=page_size, date=date, city=city)
            else:
                items, total = await self.order_repo.list_by_companion(
                    user.id, status=order_status, status_list=status_list,
                    date=date, skip=skip, limit=page_size,
                )
        else:
            items, total = await self.order_repo.list_by_patient(
                user.id, status=order_status, status_list=status_list,
                date=date, skip=skip, limit=page_size,
            )
        for item in items:
            await self._fill_payment_status(item)
        return items, total
