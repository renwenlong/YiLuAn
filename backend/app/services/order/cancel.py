"""Cancellation transitions: cancel_order (patient/companion) and reject_order (companion)."""
from __future__ import annotations

import uuid
from decimal import ROUND_HALF_UP, Decimal

from app.exceptions import BadRequestException, ForbiddenException
from app.models.order import Order, OrderStatus
from app.models.user import User, UserRole
from app.services.dead_letter import record_dead_letter

from ._base import _OrderServiceBase


class _OrderCancelMixin(_OrderServiceBase):
    async def cancel_order(self, order_id: uuid.UUID, user: User) -> Order:
        order = await self._get_order_for_update_or_404(order_id)

        if user.has_role(UserRole.patient):
            if order.patient_id != user.id:
                raise ForbiddenException("Not your order")
            new_status = OrderStatus.cancelled_by_patient
        elif user.has_role(UserRole.companion):
            if order.companion_id != user.id:
                raise ForbiddenException("Not your order")
            new_status = OrderStatus.cancelled_by_companion
        else:
            raise ForbiddenException("Invalid role")

        self._validate_transition(order.status, new_status)

        old_status = order.status
        order = await self.order_repo.update(order, {"status": new_status})
        await self._record_history(order.id, old_status, new_status, user.id)

        # Auto-refund if already paid — staged refund based on old status.
        # NOTE: tests/test_orders.py patches `app.services.order.PaymentService.create_refund`.
        # Because self.payment_svc is an instance of that same PaymentService class,
        # patching the class method propagates here via normal attribute lookup.
        existing_pay = await self.payment_repo.get_by_order_and_type(order_id, "pay")
        if existing_pay and existing_pay.status == "success":
            if old_status in (OrderStatus.created, OrderStatus.accepted):
                refund_amount = order.price  # 100% refund
            else:
                # ADR-0030: 使用 Decimal 算术 + 半进位
                refund_amount = (order.price * Decimal("0.5")).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
            try:
                await self.payment_svc.create_refund(
                    order_id=order_id,
                    user_id=order.patient_id,
                    original_amount=order.price,
                    refund_amount=refund_amount,
                )
            except BadRequestException as e:
                self.logger.error(
                    "auto_refund_failed",
                    extra={
                        "order_id": str(order_id),
                        "amount": refund_amount,
                        "reason": str(e.detail),
                        "trigger": "cancel_order",
                    },
                )
                raise BadRequestException(
                    f"订单已取消，但退款失败，请联系客服处理: {e.detail}"
                ) from e

        from app.utils.metrics import order_cancelled_total
        _st = (
            order.service_type.value
            if hasattr(order.service_type, 'value')
            else order.service_type
        )
        # ADR-0055: derive cancelled_by from new_status (set above per has_role check),
        # avoiding direct read of deprecated user.role enum field.
        _cb = "patient" if new_status == OrderStatus.cancelled_by_patient else "companion"
        order_cancelled_total.labels(service_type=_st, cancelled_by=_cb).inc()

        # Notify the other party about cancellation
        if user.has_role(UserRole.patient) and order.companion_id:
            await self.notification_svc.notify_order_status_changed(
                order, new_status.value, order.companion_id
            )
        elif user.has_role(UserRole.companion):
            await self.notification_svc.notify_order_status_changed(
                order, new_status.value, order.patient_id
            )
        return order

    async def reject_order(self, order_id: uuid.UUID, user: User) -> Order:
        order = await self._get_order_for_update_or_404(order_id)
        if not user.has_role(UserRole.companion):
            raise ForbiddenException("Only companions can reject orders")

        if order.status != OrderStatus.created:
            raise BadRequestException("Can only reject orders in created status")

        # For broadcast orders (no companion_id), companion just skips it — no state change
        if order.companion_id is None:
            raise BadRequestException("广播订单无需拒绝，其他陪诊师仍可接单")

        if order.companion_id != user.id:
            raise ForbiddenException("Not your order")

        self._validate_transition(order.status, OrderStatus.rejected_by_companion)

        order = await self.order_repo.update(
            order, {"status": OrderStatus.rejected_by_companion}
        )
        await self._record_history(
            order.id, OrderStatus.created, OrderStatus.rejected_by_companion, user.id
        )

        # Auto-refund if paid
        existing_pay = await self.payment_repo.get_by_order_and_type(order_id, "pay")
        if existing_pay and existing_pay.status == "success":
            try:
                await self.payment_svc.create_refund(
                    order_id=order_id,
                    user_id=order.patient_id,
                    original_amount=order.price,
                    refund_amount=order.price,
                )
            except BadRequestException as e:
                self.logger.error(
                    "auto_refund_failed",
                    extra={
                        "order_id": str(order_id),
                        "amount": order.price,
                        "reason": str(e.detail),
                        "trigger": "reject_by_companion",
                    },
                )
                # Best-effort dead_letter so ops can compensate manually.
                # Must use a *new* session: the primary session's transaction
                # was poisoned by the BadRequestException raised inside
                # PaymentService.create_refund (the call site rolls back).
                # Do not block rejection — patient can request manual refund
                # while the dead_letter row drives ops follow-up.
                try:
                    from app.database import async_session as _async_session

                    async with _async_session() as _dl_session:
                        await record_dead_letter(
                            _dl_session,
                            channel="order_refund",
                            reason="refund_provider_error",
                            target_type="order",
                            target_id=order_id,
                            payload={
                                "trigger": "reject_by_companion",
                                "amount": str(order.price),
                                "error": str(e.detail),
                            },
                        )
                        await _dl_session.commit()
                except Exception:  # noqa: BLE001
                    self.logger.exception("dead_letter_record_failed")

        # Notify patient
        await self.notification_svc.notify_order_rejected(order, order.patient_id)
        return order
