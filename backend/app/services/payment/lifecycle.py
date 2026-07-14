"""
PaymentService lifecycle mixin — prepay creation + pending closure.

ADR-0060 §4: ``_PaymentLifecycleMixin`` owns the payment life-cycle
entry points (``create_prepay``, ``close_pending_payment``) that do
NOT depend on callback / refund state. Behaviour is bit-identical to
the pre-split ``payment_service.py`` (pure structural move).
"""

from __future__ import annotations

import json
import logging
import uuid
from decimal import Decimal

from app.core import error_codes
from app.exceptions import BadRequestException
from app.models.order import PaymentState
from app.models.payment import Payment
from app.services.payment._base import _PaymentServiceBase
from app.services.payment._dto import PrepayResult
from app.services.providers.payment import MockPaymentProvider
from app.services.providers.payment.base import _to_decimal

logger = logging.getLogger(__name__)


class _PaymentLifecycleMixin(_PaymentServiceBase):
    """Prepay creation + pending closure."""

    # -- prepay ---------------------------------------------------------------

    async def create_prepay(
        self,
        order_id: uuid.UUID,
        order_number: str,
        user_id: uuid.UUID,
        amount: Decimal | int | float | str,
        description: str = "医路安陪诊服务",
        openid: str | None = None,
    ) -> PrepayResult:
        """Create a prepay order. Returns signing params for the client."""

        amount_dec = _to_decimal(amount).quantize(Decimal("0.01"))

        existing = await self.repo.get_by_order_and_type(order_id, "pay")
        if existing and existing.status == "success":
            raise BadRequestException(
                "订单已支付，请勿重复操作",
                error_code=error_codes.PAYMENT_ALREADY_PAID,
            )

        # D-058 F2: same-order retry while a prepay is still ``pending`` and
        # we already have a cached sign payload -> return it verbatim,
        # **without** re-hitting the PSP. Avoids wasted RPCs and keeps the
        # client's signing payload stable across retries.
        if (
            existing
            and existing.status == "pending"
            and existing.sign_params_cache
        ):
            is_mock_replay = isinstance(self.provider, MockPaymentProvider)
            try:
                cached_params = json.loads(existing.sign_params_cache)
            except json.JSONDecodeError:
                logger.warning(
                    "sign_params_cache corrupt for payment=%s — falling back to provider",
                    existing.id,
                )
            else:
                return PrepayResult(
                    payment_id=existing.id,
                    provider="mock" if is_mock_replay else "wechat",
                    prepay_id=existing.prepay_id,
                    sign_params=cached_params,
                    mock_success=False,
                )

        result = await self.provider.create_prepay(
            order_number=order_number,
            amount_yuan=amount_dec,
            description=description,
            openid=openid,
        )

        trade_no = result.get("trade_no", "")
        prepay_id = result.get("prepay_id")
        is_mock = isinstance(self.provider, MockPaymentProvider)

        payment = Payment(
            order_id=order_id,
            user_id=user_id,
            amount=amount_dec,
            payment_type="pay",
            status="success" if is_mock else "pending",
            trade_no=trade_no,
            prepay_id=prepay_id,
        )

        if existing and existing.status == "pending":
            existing.trade_no = trade_no
            existing.prepay_id = prepay_id
            existing.sign_params_cache = json.dumps(
                result.get("sign_params") or {}, default=str
            )
            if is_mock:
                existing.status = "success"
            await self.session.flush()
            payment = existing
        else:
            payment.sign_params_cache = json.dumps(
                result.get("sign_params") or {}, default=str
            )
            payment = await self.repo.create(payment)

        # H2-be: surface fund-side state on the order so the UI can show
        # “支付中 / 已付款” without coupling to OrderStatus.
        await self._set_payment_state(
            order_id,
            PaymentState.paid if payment.status == "success" else PaymentState.paying,
        )

        # Mock provider 即时成功 → 同步追加 ledger（生产 wechat 等回调）
        if is_mock and payment.status == "success":
            await self._append_pay_ledger_safe(payment)

        return PrepayResult(
            payment_id=payment.id,
            provider="mock" if is_mock else "wechat",
            prepay_id=prepay_id,
            sign_params=result.get("sign_params"),
            mock_success=is_mock,
        )

    # -- callback idempotency -------------------------------------------------

    async def close_pending_payment(
        self,
        order_id: uuid.UUID,
    ) -> None:
        """
        Close a pending payment at the PSP and mark it CLOSED locally.

        Raises BadRequestException if the PSP rejects the close (e.g. already paid).
        """
        payment = await self.repo.get_by_order_and_type(order_id, "pay")
        if payment is None or payment.status != "pending":
            return  # nothing to close

        try:
            await self.provider.close_order(payment.trade_no or "")
        except Exception as e:
            logger.error(
                "close_order failed for order=%s trade_no=%s: %s",
                order_id,
                payment.trade_no,
                e,
                exc_info=True,
            )
            raise BadRequestException(
                f"无法关闭支付单，可能用户已完成支付: {e}"
            ) from e

        payment.status = "closed"
        await self.session.flush()
        logger.info(
            "Payment closed: order=%s trade_no=%s",
            order_id,
            payment.trade_no,
        )

    # -- refund ---------------------------------------------------------------

