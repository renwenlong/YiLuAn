"""
PaymentService callback mixin — callback log idempotency + pay/refund
callback handlers.

ADR-0060 §4: ``_PaymentCallbackMixin`` owns the callback-log idempotency
guards (``record_callback_or_skip`` / ``is_callback_processed``) and the
pay + refund callback handlers (``handle_pay_callback`` /
``handle_refund_callback``).

Cross-mixin note (ADR-0060 §5, 雷区2 MRO): ``handle_pay_callback`` calls
``self.create_refund`` (L388-style late-callback auto-refund) which lives
on ``_PaymentRefundMixin``. MRO must keep both mixins reachable via
``self.``. Behaviour is bit-identical to the pre-split
``payment_service.py`` (pure structural move).
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.exceptions import BadRequestException
from app.models.order import PaymentState, RefundState
from app.models.payment import Payment
from app.models.payment_callback_log import PaymentCallbackLog
from app.services.payment._base import _PaymentServiceBase

logger = logging.getLogger(__name__)


class _PaymentCallbackMixin(_PaymentServiceBase):
    """Callback idempotency + pay/refund callback handlers."""

    async def record_callback_or_skip(
        self,
        *,
        provider: str,
        transaction_id: str,
        callback_type: str = "pay",
        out_trade_no: str | None = None,
        raw_body: bytes | str | None = None,
    ) -> bool:
        """
        Insert a PaymentCallbackLog row keyed by (provider, transaction_id).

        Returns
        -------
        ``True`` if this is a **new** callback and the caller should proceed
        with business processing.
        ``False`` if the same notification was already accepted previously
        (duplicate); the caller must NOT re-apply state changes.
        """
        if not transaction_id:
            # [ADR-0035 §3 P0-C / W19-P0-06] No transaction_id == no idempotency
            # key. Previously we defaulted to ``True`` (let caller proceed)
            # which lets a misbehaving PSP poison the ledger via repeated
            # "new" callbacks. Reject + count metric so on-call sees it.
            from app.observability.payment_metrics import (
                PAYMENT_CALLBACK_EMPTY_TXN_TOTAL,
            )

            PAYMENT_CALLBACK_EMPTY_TXN_TOTAL.labels(
                provider=provider or "unknown",
                callback_type=callback_type or "unknown",
            ).inc()
            logger.warning(
                "Rejecting payment callback with empty transaction_id: "
                "provider=%s callback_type=%s",
                provider,
                callback_type,
            )
            return False

        body_str: str | None
        if isinstance(raw_body, bytes):
            body_str = raw_body.decode(errors="replace")[:4000]
        elif isinstance(raw_body, str):
            body_str = raw_body[:4000]
        else:
            body_str = None

        log = PaymentCallbackLog(
            provider=provider,
            transaction_id=transaction_id,
            callback_type=callback_type,
            out_trade_no=out_trade_no,
            status="processed",
            raw_body=body_str,
        )

        # Use a SAVEPOINT so a uniqueness violation does not poison the
        # outer session (FastAPI dependency holds an open transaction).
        try:
            async with self.session.begin_nested():
                self.session.add(log)
                await self.session.flush()
        except IntegrityError:
            logger.info(
                "Duplicate callback ignored: provider=%s txn=%s",
                provider,
                transaction_id,
            )
            return False
        return True

    async def is_callback_processed(
        self, provider: str, transaction_id: str
    ) -> bool:
        """Cheap pre-check used by tests / monitoring."""
        if not transaction_id:
            return False
        stmt = select(PaymentCallbackLog.id).where(
            PaymentCallbackLog.provider == provider,
            PaymentCallbackLog.transaction_id == transaction_id,
        )
        result = await self.session.execute(stmt)
        return result.first() is not None

    # -- callback -------------------------------------------------------------

    async def handle_pay_callback(
        self,
        trade_no: str,
        order_number: str,
        success: bool,
    ) -> Payment | None:
        """
        Process payment callback from WeChat.

        This method is **state-mutating only**; the endpoint MUST first
        call ``record_callback_or_skip`` and only invoke this when the
        callback is genuinely new.

        Even so, we still defensively short-circuit if the Payment row is
        already in a terminal state (success / failed) — this matters for
        the ``订单已关闭后回调`` scenario where the order was cancelled and
        the Payment record may already have been closed out.

        TD-PAY-01 defense: if the order is already in a terminal state
        (expired / cancelled / rejected) and the callback is SUCCESS,
        we still flip the pay row to ``success`` for accounting honesty,
        then issue an automatic refund in the same transaction. This
        guarantees the user never has money parked against a dead order.
        """
        from app.models.order import Order, OrderStatus

        payment = await self.repo.get_by_trade_no(trade_no)
        if payment and payment.status in ("success", "failed"):
            logger.info(
                "Callback already processed for trade_no=%s status=%s",
                trade_no,
                payment.status,
            )
            return payment

        if payment is None:
            logger.warning("No payment found for trade_no=%s", trade_no)
            return None

        # Look up the linked order BEFORE mutating, so the defense
        # decision is made against authoritative state.
        order = (
            await self.session.execute(
                select(Order).where(Order.id == payment.order_id)
            )
        ).scalar_one_or_none()
        order_terminal = order is not None and order.status in (
            OrderStatus.expired,
            OrderStatus.cancelled_by_patient,
            OrderStatus.cancelled_by_companion,
            OrderStatus.rejected_by_companion,
        )

        payment.status = "success" if success else "failed"
        await self.session.flush()

        # H2-be: mirror callback outcome onto the order's payment_state.
        await self._set_payment_state(
            payment.order_id,
            PaymentState.paid if success else PaymentState.failed,
        )

        from app.utils.metrics import order_paid_total, payment_callback_received_total
        payment_callback_received_total.labels(status=payment.status).inc()
        if payment.status == "success":
            order_paid_total.labels(service_type="unknown").inc()
            # [TD-MONEY-01 M1 finishing / D-050]
            # 支付成功 → 追加 wallet_ledger（in / pay）。
            # 幂等键：(trade_no, in)；当 trade_no 缺失时 fallback 到 payment.id。
            await self._append_pay_ledger_safe(payment)
        logger.info(
            "Payment callback processed: trade_no=%s status=%s",
            trade_no,
            payment.status,
        )

        # TD-PAY-01: late SUCCESS callback against a terminal order
        # → immediate auto-refund (idempotent; skipped if a refund row
        # already exists thanks to the unique (order_id, payment_type)
        # constraint surfaced as BadRequestException by create_refund).
        if success and order_terminal and payment.status == "success":
            logger.warning(
                "late_callback_after_terminal: order=%s status=%s "
                "trade_no=%s — auto-refunding",
                order.id,
                order.status.value,
                trade_no,
            )
            try:
                await self.create_refund(
                    order_id=order.id,
                    user_id=payment.user_id,
                    original_amount=order.service_price_snapshot or order.price,
                    refund_amount=order.service_price_snapshot or order.price,
                )
            except BadRequestException as e:
                # Already refunded — idempotent ok.
                logger.info(
                    "late_callback_refund_skip order=%s reason=%s",
                    order.id,
                    e.detail,
                )
            except Exception as e:  # pragma: no cover - safety net
                logger.error(
                    "late_callback_refund_error order=%s err=%s",
                    order.id,
                    e,
                    exc_info=True,
                )

        # [ADR-0032 / TD-MONEY-01 M3 / D-044] 增量对账事件：回调落盘后丢进进程
        # 内队列，供 5min sweeper 拉走对账 + autofix。
        # Fire-and-forget：入队失败不能影响主业务 — sweeper 还会走
        # payment_callback_log lookback 兑底。
        try:
            from app.services.reconciliation.incremental import (
                enqueue_incremental_event,
            )
            await enqueue_incremental_event(
                order_id=payment.order_id,
                provider=getattr(payment, "provider", None) or "unknown",
                transaction_id=trade_no,
            )
        except Exception as exc:  # pragma: no cover - defence only
            logger.warning(
                "reconciliation enqueue failed (non-fatal) trade_no=%s err=%s",
                trade_no,
                exc,
            )

        return payment

    # -- close order -----------------------------------------------------------

    async def handle_refund_callback(
        self,
        refund_id: str,
        refund_status: str,
        raw_body: str | None = None,
    ) -> Payment | None:
        """
        Process refund callback from WeChat.

        Must be called AFTER ``record_callback_or_skip`` confirms this is
        a new (non-duplicate) notification.

        Returns the updated Payment, or ``None`` if the refund_id is unknown.
        """
        payment = await self.repo.get_by_refund_id(refund_id)

        if payment is None:
            logger.warning(
                "Refund callback for unknown refund_id=%s — ignoring",
                refund_id,
            )
            return None

        # Already terminal — idempotent success
        if payment.status in ("success", "failed"):
            logger.info(
                "Refund already terminal: refund_id=%s status=%s",
                refund_id,
                payment.status,
            )
            return payment

        if refund_status == "SUCCESS":
            payment.status = "success"
            logger.info(
                "Refund succeeded: refund_id=%s amount=%s",
                refund_id,
                payment.amount,
            )
        else:
            # CHANGE / REFUNDCLOSE / ABNORMAL or any non-SUCCESS
            payment.status = "failed"
            logger.error(
                "Refund FAILED: refund_id=%s wechat_status=%s — "
                "manual intervention may be required",
                refund_id,
                refund_status,
            )

        if raw_body:
            payment.callback_raw = raw_body[:4000]

        await self.session.flush()

        # H2-be: mirror refund outcome on the order's refund_state.
        await self._set_refund_state(
            payment.order_id,
            RefundState.refunded if payment.status == "success" else RefundState.failed,
        )

        # [TD-MONEY-01 M1 finishing / D-050]
        # 退款成功 → 追加 wallet_ledger（out / refund）。
        if payment.status == "success":
            await self._append_refund_ledger_safe(payment)

        return payment
