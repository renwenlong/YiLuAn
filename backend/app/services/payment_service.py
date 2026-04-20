"""
Payment Service — unified payment entry point.

Supports pluggable providers selected by ``settings.payment_provider``:

  * ``mock``   — instant success, for dev/test (default)
  * ``wechat`` — WeChat Pay v3 JSAPI (production)

Provider implementations live in :mod:`app.services.providers.payment`.
This module is the **orchestration layer**: it owns the ``Payment`` model
and the cross-provider concerns (idempotency, refund bookkeeping, etc.).

Backwards-compatibility re-exports
----------------------------------
Existing tests import ``MockPaymentProvider``, ``WechatPaymentProvider``
and ``PaymentProvider`` from this module. To avoid touching call-sites
during the P0-1 refactor, those names are re-exported below.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.exceptions import BadRequestException
from app.models.payment import Payment
from app.models.payment_callback_log import PaymentCallbackLog
from app.repositories.payment import PaymentRepository
from app.services.providers.payment import (
    MockPaymentProvider,
    PaymentProvider,
    WechatPaymentProvider,
    get_payment_provider,
)
from app.services.providers.payment.wechat import (
    _platform_cert_cache,  # noqa: F401  (re-exported for legacy tests)
)

logger = logging.getLogger(__name__)


__all__ = [
    "PrepayResult",
    "RefundResult",
    "PaymentService",
    # legacy re-exports (don't remove without migrating tests)
    "PaymentProvider",
    "MockPaymentProvider",
    "WechatPaymentProvider",
]


# ---------------------------------------------------------------------------
# Data transfer objects
# ---------------------------------------------------------------------------

@dataclass
class PrepayResult:
    """Returned to the caller after creating a prepay order."""

    payment_id: uuid.UUID
    provider: str  # "mock" | "wechat"
    prepay_id: str | None = None
    sign_params: dict[str, Any] | None = None
    mock_success: bool = False


@dataclass
class RefundResult:
    payment_id: uuid.UUID
    provider: str
    refund_id: str | None = None
    mock_success: bool = False


# ---------------------------------------------------------------------------
# PaymentService
# ---------------------------------------------------------------------------

class PaymentService:
    """
    Orchestrates payment lifecycle: prepay → callback → refund.

    Owns ``Payment`` + ``PaymentCallbackLog`` persistence; OrderService
    delegates here.
    """

    def __init__(self, session: AsyncSession):
        self.repo = PaymentRepository(session)
        self.session = session
        self.provider = get_payment_provider()

    # -- prepay ---------------------------------------------------------------

    async def create_prepay(
        self,
        order_id: uuid.UUID,
        order_number: str,
        user_id: uuid.UUID,
        amount: float,
        description: str = "医路安陪诊服务",
        openid: str | None = None,
    ) -> PrepayResult:
        """Create a prepay order. Returns signing params for the client."""

        existing = await self.repo.get_by_order_and_type(order_id, "pay")
        if existing and existing.status == "success":
            raise BadRequestException("订单已支付，请勿重复操作")

        result = await self.provider.create_prepay(
            order_number=order_number,
            amount_yuan=amount,
            description=description,
            openid=openid,
        )

        trade_no = result.get("trade_no", "")
        prepay_id = result.get("prepay_id")
        is_mock = isinstance(self.provider, MockPaymentProvider)

        payment = Payment(
            order_id=order_id,
            user_id=user_id,
            amount=amount,
            payment_type="pay",
            status="success" if is_mock else "pending",
            trade_no=trade_no,
            prepay_id=prepay_id,
        )

        if existing and existing.status == "pending":
            existing.trade_no = trade_no
            existing.prepay_id = prepay_id
            if is_mock:
                existing.status = "success"
            await self.session.flush()
            payment = existing
        else:
            payment = await self.repo.create(payment)

        return PrepayResult(
            payment_id=payment.id,
            provider="mock" if is_mock else "wechat",
            prepay_id=prepay_id,
            sign_params=result.get("sign_params"),
            mock_success=is_mock,
        )

    # -- callback idempotency -------------------------------------------------

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
            # Without a transaction_id we cannot deduplicate; let caller
            # decide. Default to "process" because the alternative is to
            # silently drop the callback.
            return True

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
        """
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

        payment.status = "success" if success else "failed"
        await self.session.flush()
        logger.info(
            "Payment callback processed: trade_no=%s status=%s",
            trade_no,
            payment.status,
        )
        return payment

    # -- refund ---------------------------------------------------------------

    async def create_refund(
        self,
        order_id: uuid.UUID,
        user_id: uuid.UUID,
        original_amount: float,
        refund_amount: float,
    ) -> RefundResult:
        """Create a refund for an order."""

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
                total_yuan=original_amount,
                refund_yuan=refund_amount,
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
            amount=refund_amount,
            payment_type="refund",
            status="success" if is_mock else "pending",
            trade_no=original_pay.trade_no,
            refund_id=result.get("refund_id", refund_number),
        )
        refund = await self.repo.create(refund)

        return RefundResult(
            payment_id=refund.id,
            provider="mock" if is_mock else "wechat",
            refund_id=refund.refund_id,
            mock_success=is_mock,
        )

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
        return payment
