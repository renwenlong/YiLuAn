"""
Payment Service — unified payment entry point.

Supports pluggable providers:
  - mock   : instant success, for dev/test
  - wechat : WeChat Pay v3 JSAPI (production)

Provider is selected by ``settings.payment_provider``.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.exceptions import BadRequestException
from app.models.payment import Payment
from app.repositories.payment import PaymentRepository

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data transfer objects
# ---------------------------------------------------------------------------

@dataclass
class PrepayResult:
    """Returned to the caller after creating a prepay order."""

    payment_id: uuid.UUID
    provider: str  # "mock" | "wechat"
    # Fields only populated by wechat provider:
    prepay_id: str | None = None
    sign_params: dict[str, Any] | None = None
    # For mock provider, payment is already "success":
    mock_success: bool = False


@dataclass
class RefundResult:
    payment_id: uuid.UUID
    provider: str
    refund_id: str | None = None
    mock_success: bool = False


# ---------------------------------------------------------------------------
# Provider interface
# ---------------------------------------------------------------------------

class PaymentProvider:
    """Abstract base for payment providers."""

    async def create_prepay(
        self,
        order_number: str,
        amount_yuan: float,
        description: str,
        openid: str | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError

    async def create_refund(
        self,
        trade_no: str,
        refund_id: str,
        total_yuan: float,
        refund_yuan: float,
    ) -> dict[str, Any]:
        raise NotImplementedError

    async def verify_callback(self, headers: dict, body: bytes) -> dict[str, Any]:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Mock provider (dev / test)
# ---------------------------------------------------------------------------

class MockPaymentProvider(PaymentProvider):
    """Instant‑success provider for development and testing."""

    async def create_prepay(
        self,
        order_number: str,
        amount_yuan: float,
        description: str,
        openid: str | None = None,
    ) -> dict[str, Any]:
        fake_trade = f"MOCK_{uuid.uuid4().hex[:16].upper()}"
        return {
            "trade_no": fake_trade,
            "prepay_id": f"mock_prepay_{fake_trade}",
            "status": "success",
        }

    async def create_refund(
        self,
        trade_no: str,
        refund_id: str,
        total_yuan: float,
        refund_yuan: float,
    ) -> dict[str, Any]:
        return {
            "refund_id": refund_id,
            "status": "success",
        }

    async def verify_callback(self, headers: dict, body: bytes) -> dict[str, Any]:
        return {"verified": True}


# ---------------------------------------------------------------------------
# WeChat Pay v3 provider (production — skeleton)
# ---------------------------------------------------------------------------

class WechatPaymentProvider(PaymentProvider):
    """
    WeChat Pay v3 JSAPI provider.

    Requires merchant credentials in settings:
      - wechat_pay_mch_id
      - wechat_pay_api_key_v3
      - wechat_pay_cert_serial
      - wechat_pay_private_key_path

    TODO: implement when merchant credentials are provided.
    """

    async def create_prepay(
        self,
        order_number: str,
        amount_yuan: float,
        description: str,
        openid: str | None = None,
    ) -> dict[str, Any]:
        # Phase 2: call POST https://api.mch.weixin.qq.com/v3/pay/transactions/jsapi
        raise NotImplementedError(
            "WeChat Pay v3 not yet configured. "
            "Set payment_provider=mock for development."
        )

    async def create_refund(
        self,
        trade_no: str,
        refund_id: str,
        total_yuan: float,
        refund_yuan: float,
    ) -> dict[str, Any]:
        # Phase 2: call POST https://api.mch.weixin.qq.com/v3/refund/domestic/refunds
        raise NotImplementedError("WeChat refund not yet configured.")

    async def verify_callback(self, headers: dict, body: bytes) -> dict[str, Any]:
        # Phase 2: RSA signature verification
        raise NotImplementedError("WeChat callback verification not yet configured.")


# ---------------------------------------------------------------------------
# Provider factory
# ---------------------------------------------------------------------------

def _get_provider() -> PaymentProvider:
    name = getattr(settings, "payment_provider", "mock")
    if name == "wechat":
        return WechatPaymentProvider()
    return MockPaymentProvider()


# ---------------------------------------------------------------------------
# PaymentService
# ---------------------------------------------------------------------------

class PaymentService:
    """
    Orchestrates payment lifecycle: prepay → callback → refund.

    This service owns the Payment model; OrderService delegates here.
    """

    def __init__(self, session: AsyncSession):
        self.repo = PaymentRepository(session)
        self.session = session
        self.provider = _get_provider()

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

        # Idempotency: if a successful pay record exists, reject
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

        # If existing pending record, update it; otherwise create
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

    # -- callback -------------------------------------------------------------

    async def handle_pay_callback(
        self,
        trade_no: str,
        order_number: str,
        success: bool,
    ) -> Payment | None:
        """
        Process payment callback from WeChat.
        Idempotent: if already processed, return existing record.
        """
        payment = await self.repo.get_by_trade_no(trade_no)
        if payment and payment.status in ("success", "failed"):
            logger.info("Callback already processed for trade_no=%s", trade_no)
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

        # Check existing refund (idempotent)
        existing_refund = await self.repo.get_by_order_and_type(order_id, "refund")
        if existing_refund:
            raise BadRequestException("该订单已退款，请勿重复操作")

        # Get original pay record
        original_pay = await self.repo.get_by_order_and_type(order_id, "pay")
        if not original_pay or original_pay.status != "success":
            raise BadRequestException("原订单未支付成功，无法退款")

        refund_number = f"R{uuid.uuid4().hex[:16].upper()}"
        is_mock = isinstance(self.provider, MockPaymentProvider)

        if not is_mock:
            result = await self.provider.create_refund(
                trade_no=original_pay.trade_no or "",
                refund_id=refund_number,
                total_yuan=original_amount,
                refund_yuan=refund_amount,
            )
        else:
            result = {"refund_id": refund_number, "status": "success"}

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
