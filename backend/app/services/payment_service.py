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

    When real credentials are configured (settings.wechat_pay_mch_id etc.),
    this provider calls the actual WeChat Pay v3 API.
    When credentials are empty, it falls back to mock-style responses
    that mirror the real API response structure.
    """

    def __init__(self):
        self.mch_id = settings.wechat_pay_mch_id
        self.api_key_v3 = settings.wechat_pay_api_key_v3
        self.cert_serial = settings.wechat_pay_cert_serial
        self.private_key_path = settings.wechat_pay_private_key_path
        self.notify_url = settings.wechat_pay_notify_url
        self.app_id = settings.wechat_app_id
        self._has_credentials = bool(self.mch_id and self.api_key_v3)

    async def create_prepay(
        self,
        order_number: str,
        amount_yuan: float,
        description: str,
        openid: str | None = None,
    ) -> dict[str, Any]:
        import time

        amount_fen = int(round(amount_yuan * 100))

        if not self._has_credentials:
            # Simulate WeChat v3 response structure with mock data
            fake_prepay = f"wx_prepay_{uuid.uuid4().hex[:16]}"
            fake_trade = f"WX_{uuid.uuid4().hex[:20].upper()}"
            timestamp = str(int(time.time()))
            nonce = uuid.uuid4().hex[:32]
            return {
                "trade_no": fake_trade,
                "prepay_id": fake_prepay,
                "status": "success",
                "sign_params": {
                    "appId": self.app_id or "wx_mock_appid",
                    "timeStamp": timestamp,
                    "nonceStr": nonce,
                    "package": f"prepay_id={fake_prepay}",
                    "signType": "RSA",
                    "paySign": f"mock_sign_{nonce[:8]}",
                },
            }

        # --- Real WeChat Pay v3 JSAPI call ---
        # POST https://api.mch.weixin.qq.com/v3/pay/transactions/jsapi
        import httpx

        url = "https://api.mch.weixin.qq.com/v3/pay/transactions/jsapi"
        body = {
            "appid": self.app_id,
            "mchid": self.mch_id,
            "description": description,
            "out_trade_no": order_number,
            "notify_url": self.notify_url,
            "amount": {
                "total": amount_fen,
                "currency": "CNY",
            },
            "payer": {
                "openid": openid or "",
            },
        }

        headers = self._build_auth_header("POST", "/v3/pay/transactions/jsapi", body)

        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=body, headers=headers, timeout=30)

        if resp.status_code != 200:
            logger.error("WeChat prepay failed: %s %s", resp.status_code, resp.text)
            raise BadRequestException(f"微信支付下单失败: {resp.status_code}")

        data = resp.json()
        prepay_id = data.get("prepay_id", "")
        timestamp = str(int(time.time()))
        nonce = uuid.uuid4().hex[:32]

        # Build sign params for wx.requestPayment
        sign_str = f"{self.app_id}\n{timestamp}\n{nonce}\nprepay_id={prepay_id}\n"
        pay_sign = self._rsa_sign(sign_str)

        return {
            "trade_no": order_number,
            "prepay_id": prepay_id,
            "status": "pending",
            "sign_params": {
                "appId": self.app_id,
                "timeStamp": timestamp,
                "nonceStr": nonce,
                "package": f"prepay_id={prepay_id}",
                "signType": "RSA",
                "paySign": pay_sign,
            },
        }

    async def create_refund(
        self,
        trade_no: str,
        refund_id: str,
        total_yuan: float,
        refund_yuan: float,
    ) -> dict[str, Any]:
        total_fen = int(round(total_yuan * 100))
        refund_fen = int(round(refund_yuan * 100))

        if not self._has_credentials:
            return {
                "refund_id": refund_id,
                "status": "success",
            }

        # --- Real WeChat Pay v3 refund ---
        import httpx

        url = "https://api.mch.weixin.qq.com/v3/refund/domestic/refunds"
        body = {
            "out_trade_no": trade_no,
            "out_refund_no": refund_id,
            "amount": {
                "refund": refund_fen,
                "total": total_fen,
                "currency": "CNY",
            },
            "notify_url": f"{self.notify_url.rstrip('/')}-refund"
            if self.notify_url
            else "",
        }

        headers = self._build_auth_header(
            "POST", "/v3/refund/domestic/refunds", body
        )

        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=body, headers=headers, timeout=30)

        if resp.status_code not in (200, 201):
            logger.error("WeChat refund failed: %s %s", resp.status_code, resp.text)
            raise BadRequestException(f"微信退款失败: {resp.status_code}")

        data = resp.json()
        return {
            "refund_id": data.get("out_refund_no", refund_id),
            "status": data.get("status", "PROCESSING").lower(),
        }

    async def verify_callback(
        self, headers: dict, body: bytes
    ) -> dict[str, Any]:
        """Verify WeChat callback signature and decrypt payload."""
        if not self._has_credentials:
            # Mock mode: trust everything
            import json

            try:
                return json.loads(body)
            except Exception:
                return {"verified": True, "raw": body.decode(errors="replace")}

        # --- Real signature verification ---
        # 1. Extract Wechatpay-Timestamp, Wechatpay-Nonce, Wechatpay-Signature
        # 2. Construct verification string
        # 3. Verify with WeChat platform public key
        # 4. Decrypt resource field with AES-256-GCM using api_key_v3
        timestamp = headers.get("wechatpay-timestamp", "")
        nonce = headers.get("wechatpay-nonce", "")
        signature = headers.get("wechatpay-signature", "")
        serial = headers.get("wechatpay-serial", "")

        verify_str = f"{timestamp}\n{nonce}\n{body.decode()}\n"

        # TODO: fetch WeChat platform certificate and verify signature
        # TODO: decrypt resource.ciphertext with AES-256-GCM
        logger.warning(
            "WeChat callback signature verification not fully implemented. "
            "serial=%s",
            serial,
        )

        import json

        return json.loads(body)

    def _build_auth_header(
        self, method: str, path: str, body: Any
    ) -> dict[str, str]:
        """Build WECHATPAY2-SHA256-RSA2048 Authorization header."""
        import json
        import time as _time

        timestamp = str(int(_time.time()))
        nonce = uuid.uuid4().hex[:32]
        body_str = json.dumps(body, ensure_ascii=False) if body else ""
        sign_str = f"{method}\n{path}\n{timestamp}\n{nonce}\n{body_str}\n"
        signature = self._rsa_sign(sign_str)

        auth = (
            f'WECHATPAY2-SHA256-RSA2048 '
            f'mchid="{self.mch_id}",'
            f'nonce_str="{nonce}",'
            f'timestamp="{timestamp}",'
            f'serial_no="{self.cert_serial}",'
            f'signature="{signature}"'
        )
        return {
            "Authorization": auth,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _rsa_sign(self, message: str) -> str:
        """Sign message with merchant RSA private key."""
        import base64

        if not self.private_key_path:
            return "mock_rsa_signature"

        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import padding

            with open(self.private_key_path, "rb") as f:
                private_key = serialization.load_pem_private_key(f.read(), password=None)

            sig = private_key.sign(
                message.encode("utf-8"),
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
            return base64.b64encode(sig).decode("utf-8")
        except Exception as e:
            logger.error("RSA sign failed: %s", e)
            return "sign_error"


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

        result = await self.provider.create_refund(
            trade_no=original_pay.trade_no or "",
            refund_id=refund_number,
            total_yuan=original_amount,
            refund_yuan=refund_amount,
        )

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
