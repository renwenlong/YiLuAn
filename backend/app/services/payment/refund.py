"""
PaymentService refund mixin — refund creation.

ADR-0060 §4: ``_PaymentRefundMixin`` owns ``create_refund``. Called both
directly by admin flows and cross-mixin from ``handle_pay_callback``
(late-callback auto-refund). Behaviour is bit-identical to the pre-split
``payment_service.py`` (pure structural move).
"""

from __future__ import annotations

import logging
import uuid
from decimal import Decimal

from app.exceptions import BadRequestException
from app.models.order import RefundState
from app.models.payment import Payment
from app.services.payment._base import _PaymentServiceBase
from app.services.payment._dto import RefundResult
from app.services.providers.payment import MockPaymentProvider
from app.services.providers.payment.base import _to_decimal

logger = logging.getLogger(__name__)


class _PaymentRefundMixin(_PaymentServiceBase):
    """Refund creation."""
    async def create_refund(
        self,
        order_id: uuid.UUID,
        user_id: uuid.UUID,
        original_amount: Decimal | int | float | str,
        refund_amount: Decimal | int | float | str,
    ) -> RefundResult:
        """Create a refund for an order."""

        original_dec = _to_decimal(original_amount).quantize(Decimal("0.01"))
        refund_dec = _to_decimal(refund_amount).quantize(Decimal("0.01"))

        existing_refund = await self.repo.get_by_order_and_type(
            order_id, "refund"
        )
        if existing_refund:
            raise BadRequestException("该订单已退款，请勿重复操作")

        original_pay = await self.repo.get_by_order_and_type(order_id, "pay")
        if not original_pay or original_pay.status != "success":
            raise BadRequestException("原订单未支付成功，无法退款")

        refund_number = f"R{uuid.uuid4().hex[:16].upper()}"
        is_mock = isinstance(self.provider, MockPaymentProvider)

        try:
            result = await self.provider.create_refund(
                trade_no=original_pay.trade_no or "",
                refund_id=refund_number,
                total_yuan=original_dec,
                refund_yuan=refund_dec,
            )
        except BadRequestException:
            # Provider explicitly rejected — propagate to caller as-is so
            # the API surface returns a 400 with the underlying reason.
            raise
        except Exception as e:
            # Provider hard-failure (network, etc.). Surface as 400 so the
            # request is rolled back cleanly; do NOT persist a partial
            # success record. Operators can replay the request once the
            # provider recovers; the unique (order_id, payment_type=refund)
            # constraint still protects against double-refund.
            logger.error(
                "Refund provider call failed for order=%s: %s",
                order_id,
                e,
                exc_info=True,
            )
            raise BadRequestException(f"退款渠道异常: {e}") from e

        refund = Payment(
            order_id=order_id,
            user_id=user_id,
            amount=refund_dec,
            payment_type="refund",
            status="success" if is_mock else "pending",
            trade_no=original_pay.trade_no,
            refund_id=result.get("refund_id", refund_number),
        )
        refund = await self.repo.create(refund)

        # H2-be: refund_state → refunding (mock-success will be flipped
        # to ``refunded`` immediately below).
        _refund_target = (
            RefundState.refunded
            if (is_mock and refund.status == "success")
            else RefundState.refunding
        )
        await self._set_refund_state(
            order_id,
            _refund_target,
        )

        # Mock provider 即时成功 → 同步追加 ledger（生产走 refund callback）
        if is_mock and refund.status == "success":
            await self._append_refund_ledger_safe(refund)

        return RefundResult(
            payment_id=refund.id,
            provider="mock" if is_mock else "wechat",
            refund_id=refund.refund_id,
            mock_success=is_mock,
        )

