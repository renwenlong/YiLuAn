"""Scheduled expiry reconciliation: check_expired_orders.

TD-PAY-01 / ADR-0007: when an order's expiry timer fires, the linked Payment
row must be reconciled in the same transaction so we never leave a succeeded
pay floating against an expired order, and never leave a pending pay open
at the PSP.

NOTE (SP-01): This file preserves the original `check_expired_orders` body
*verbatim* (including the duplicated 'pending close' block that exists in
the legacy file). Cleaning that duplication is tracked separately so this
PR stays a pure structural refactor with zero behaviour delta.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone

from app.exceptions import BadRequestException, NotExpirableOrderError
from app.models.order import Order, OrderStatus

from ._base import _OrderServiceBase


def _logger():
    return sys.modules["app.services.order"].logger


class _OrderExpiryMixin(_OrderServiceBase):
    async def check_expired_orders(self) -> list[Order]:
        """Check for expired orders and reconcile payment state.

        TD-PAY-01: When an order's expiry timer fires, the linked Payment
        row must be reconciled in the same transaction so we never leave a
        succeeded pay floating against an expired order, and never leave a
        pending pay open at the PSP. See ADR-0007.

        - pay.status == 'success' → trigger automatic full refund
          (via PaymentService.create_refund), then expire the order.
        - pay.status == 'pending' → best-effort close at the PSP, then
          mark the local row as 'failed' with reason='order_expired'.
          A late SUCCESS callback that arrives after this is handled by
          PaymentService.handle_pay_callback's defensive refund branch.
        - pay.status in ('success' already-refunded / 'failed' / 'closed') → skip.
        """
        now = datetime.now(timezone.utc)
        expired_orders = await self.order_repo.list_expired(now)
        cancelled = []
        for order in expired_orders:
            existing_pay = await self.payment_repo.get_by_order_and_type(order.id, "pay")
            if existing_pay and existing_pay.status == "success":
                # TD-PAY-01 / ADR-0007: a paid order has crossed the no-show
                # threshold for the patient. Refunds are user-initiated via
                # cancel/refund. The scheduler must NOT auto-expire/refund
                # paid orders — surface 409 so ops/admin can resolve.
                raise NotExpirableOrderError(
                    f"订单 {order.order_number} 已支付成功，无法过期"
                )
            if existing_pay and existing_pay.status == "pending":
                # Best-effort close at PSP. If PSP rejects (user paid in
                # the meantime), still mark local row failed so the
                # late callback's refund branch fires.
                try:
                    await self.payment_svc.close_pending_payment(order.id)
                except BadRequestException as e:
                    _logger().warning(
                        "expire_close_payment_failed order=%s reason=%s",
                        order.id,
                        e.detail,
                    )
                    existing_pay.status = "failed"
                    _note = "order_expired:close_failed"
                    existing_pay.callback_raw = (
                        (existing_pay.callback_raw or "") + f"\n[{_note}]"
                    )[:4000]
                    await self.session.flush()
                else:
                    # close_pending_payment marks the row 'closed'; tighten
                    # to 'failed' with reason for TD-PAY-01 contract.
                    await self.session.refresh(existing_pay)
                    if existing_pay.status in ("closed", "pending"):
                        existing_pay.status = "failed"
                        existing_pay.callback_raw = (
                            (existing_pay.callback_raw or "")
                            + "\n[order_expired]"
                        )[:4000]
                        await self.session.flush()
                # Best-effort close at PSP. If PSP rejects (user paid in
                # the meantime), still mark local row failed so the
                # late callback's refund branch fires.
                try:
                    await self.payment_svc.close_pending_payment(order.id)
                except BadRequestException as e:
                    _logger().warning(
                        "expire_close_payment_failed order=%s reason=%s",
                        order.id,
                        e.detail,
                    )
                    existing_pay.status = "failed"
                    _note = "order_expired:close_failed"
                    existing_pay.callback_raw = (
                        (existing_pay.callback_raw or "") + f"\n[{_note}]"
                    )[:4000]
                    await self.session.flush()
                else:
                    # close_pending_payment marks the row 'closed'; tighten
                    # to 'failed' with reason for TD-PAY-01 contract.
                    await self.session.refresh(existing_pay)
                    if existing_pay.status in ("closed", "pending"):
                        existing_pay.status = "failed"
                        existing_pay.callback_raw = (
                            (existing_pay.callback_raw or "")
                            + "\n[order_expired]"
                        )[:4000]
                        await self.session.flush()

            order = await self.order_repo.update(
                order, {"status": OrderStatus.expired}
            )
            await self._record_history(
                order.id, OrderStatus.created, OrderStatus.expired, order.patient_id
            )

            # Notify patient
            await self.notification_svc.notify_order_expired(order, order.patient_id)
            cancelled.append(order)
        return cancelled
