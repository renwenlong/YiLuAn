"""
WeChat Pay v3 provider.

Status
------
This module implements the v3 JSAPI signing / signature verification /
AES-GCM decryption skeleton, but it is **not enabled by default**:

  * If ``settings.payment_provider != "wechat"`` it is never instantiated.
  * Even when instantiated, if the merchant credentials are not configured,
    the provider falls back to mock-style responses that mirror the real
    API response structure. This lets the small program client be wired
    against realistic shapes without a real merchant account.
  * To go to production, the ``_has_credentials`` branch will issue real
    HTTP calls to ``api.mch.weixin.qq.com`` — but production roll-out
    requires **all** the credentials listed below in
    ``REQUIRED_PRODUCTION_SETTINGS``. Missing any of them must be treated
    as a configuration error.

Required production settings (see ``app.config.Settings``)
---------------------------------------------------------
* ``WECHAT_PAY_MCH_ID``               商户号
* ``WECHAT_PAY_API_KEY_V3``           APIv3 32-byte 密钥
* ``WECHAT_PAY_CERT_SERIAL``          商户证书序列号
* ``WECHAT_PAY_PRIVATE_KEY_PATH``     商户私钥 PEM 路径
* ``WECHAT_PAY_NOTIFY_URL``           回调通知 URL（公网 HTTPS）
* ``WECHAT_PAY_PLATFORM_CERT_PATH``   微信平台证书 PEM 路径
* ``WECHAT_APP_ID``                   小程序 AppID

These are also tracked in ``docs/TODO_CREDENTIALS.md``.

TODO (real production hardening)
--------------------------------
* Auto-rotate platform certificates via /v3/certificates endpoint
* Refund result callback handling (signature verify is shared, but
  refund Payment record status update is not yet implemented in
  ``payment_callback.py::wechat_refund_callback``).
* Add metrics (latency / success rate) per provider call.
"""

from __future__ import annotations

import base64
import json
import logging
import threading
import time
import uuid
from decimal import ROUND_HALF_UP, Decimal  # noqa: F401  (Decimal used via type hints)
from typing import Any

from app.config import settings
from app.exceptions import BadRequestException
from app.services.providers.payment.base import (
    OrderDTO,
    PaymentProvider,
    RefundDTO,
)
from app.utils.outbound import outbound_call

logger = logging.getLogger(__name__)


# Configuration items that MUST be present before this provider can be
# considered production-ready. Surfaced as a constant so ops tooling and
# tests can introspect the contract without parsing this docstring.
REQUIRED_PRODUCTION_SETTINGS: tuple[str, ...] = (
    "WECHAT_APP_ID",
    "WECHAT_PAY_MCH_ID",
    "WECHAT_PAY_API_KEY_V3",
    "WECHAT_PAY_CERT_SERIAL",
    "WECHAT_PAY_PRIVATE_KEY_PATH",
    "WECHAT_PAY_NOTIFY_URL",
    "WECHAT_PAY_PLATFORM_CERT_PATH",
)


# Module-level platform-certificate cache (thread-safe).
_platform_cert_cache: dict[str, Any] = {}
_cert_cache_lock = threading.Lock()


class WechatPaymentProvider(PaymentProvider):
    """WeChat Pay v3 JSAPI provider."""

    name = "wechat"

    def __init__(self):
        self.mch_id = settings.wechat_pay_mch_id
        self.api_key_v3 = settings.wechat_pay_api_key_v3
        self.cert_serial = settings.wechat_pay_cert_serial
        self.private_key_path = settings.wechat_pay_private_key_path
        self.notify_url = settings.wechat_pay_notify_url
        self.app_id = settings.wechat_app_id
        self.platform_cert_path = settings.wechat_pay_platform_cert_path
        self._has_credentials = bool(self.mch_id and self.api_key_v3)

    # ------------------------------------------------------------------ API

    @outbound_call(provider="wechat_pay", timeout=5.0, max_retries=2)
    async def create_order(self, order: OrderDTO) -> dict[str, Any]:
        # ADR-0030: amount_yuan is Decimal — convert to fen exactly.
        amount_fen = int(
            (order.amount_yuan * 100).to_integral_value(rounding=ROUND_HALF_UP)
        )

        if not self._has_credentials:
            # Mirror real response shape with mock data.
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

        import httpx

        url = "https://api.mch.weixin.qq.com/v3/pay/transactions/jsapi"
        body = {
            "appid": self.app_id,
            "mchid": self.mch_id,
            "description": order.description,
            "out_trade_no": order.order_number,
            "notify_url": self.notify_url,
            "amount": {"total": amount_fen, "currency": "CNY"},
            "payer": {"openid": order.openid or ""},
        }

        headers = self._build_auth_header(
            "POST", "/v3/pay/transactions/jsapi", body
        )

        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=body, headers=headers, timeout=30)

        if resp.status_code != 200:
            logger.error(
                "WeChat prepay failed: %s %s", resp.status_code, resp.text
            )
            raise BadRequestException(f"微信支付下单失败: {resp.status_code}")

        data = resp.json()
        prepay_id = data.get("prepay_id", "")
        timestamp = str(int(time.time()))
        nonce = uuid.uuid4().hex[:32]

        sign_str = (
            f"{self.app_id}\n{timestamp}\n{nonce}\nprepay_id={prepay_id}\n"
        )
        pay_sign = self._rsa_sign(sign_str)

        return {
            "trade_no": order.order_number,
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

    @outbound_call(provider="wechat_pay", timeout=5.0, max_retries=2)
    async def refund(self, refund: RefundDTO) -> dict[str, Any]:
        # ADR-0030: amounts are Decimal — convert to fen exactly.
        total_fen = int(
            (refund.total_yuan * 100).to_integral_value(rounding=ROUND_HALF_UP)
        )
        refund_fen = int(
            (refund.refund_yuan * 100).to_integral_value(rounding=ROUND_HALF_UP)
        )

        if not self._has_credentials:
            return {
                "refund_id": refund.refund_id,
                "status": "success",
            }

        import httpx

        url = "https://api.mch.weixin.qq.com/v3/refund/domestic/refunds"
        body = {
            "out_trade_no": refund.trade_no,
            "out_refund_no": refund.refund_id,
            "amount": {
                "refund": refund_fen,
                "total": total_fen,
                "currency": "CNY",
            },
            "notify_url": (
                f"{self.notify_url.rstrip('/')}-refund"
                if self.notify_url
                else ""
            ),
        }

        headers = self._build_auth_header(
            "POST", "/v3/refund/domestic/refunds", body
        )

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url, json=body, headers=headers, timeout=30
            )

        if resp.status_code not in (200, 201):
            logger.error(
                "WeChat refund failed: %s %s", resp.status_code, resp.text
            )
            raise BadRequestException(f"微信退款失败: {resp.status_code}")

        data = resp.json()
        return {
            "refund_id": data.get("out_refund_no", refund.refund_id),
            "status": data.get("status", "PROCESSING").lower(),
        }

    @outbound_call(provider="wechat_pay", timeout=5.0, max_retries=2)
    async def verify_callback(
        self, headers: dict, body: bytes
    ) -> dict[str, Any]:
        if not self._has_credentials:
            try:
                return json.loads(body)
            except Exception:
                return {
                    "verified": True,
                    "raw": body.decode(errors="replace"),
                }

        self._verify_signature(headers, body)

        payload = json.loads(body)
        resource = payload.get("resource")
        if resource:
            payload["resource"] = self._decrypt_resource(resource)
        return payload

    @outbound_call(provider="wechat_pay", timeout=5.0, max_retries=2)
    async def query(self, order: OrderDTO) -> dict[str, Any]:
        # Real implementation would call:
        #   GET /v3/pay/transactions/out-trade-no/{out_trade_no}?mchid={mch_id}
        # Not yet wired; raise so callers know this is a TODO.
        raise NotImplementedError(
            "WechatPaymentProvider.query() not implemented yet — "
            "see docs/TODO_CREDENTIALS.md and the module docstring."
        )

    async def close_order(self, out_trade_no: str) -> dict[str, Any]:
        # Real implementation would call:
        #   POST /v3/pay/transactions/out-trade-no/{out_trade_no}/close
        #   body: {"mchid": self.mch_id}
        # For now, fall back to mock-style success when credentials are absent.
        if not self._has_credentials:
            return {"status": "success"}
        raise NotImplementedError(
            "WechatPaymentProvider.close_order() production path not "
            "implemented yet — see docs/TODO_CREDENTIALS.md."
        )

    # ------------------------------------------------- signature / crypto

    def _verify_signature(self, headers: dict, body: bytes) -> None:
        timestamp = headers.get("wechatpay-timestamp", "")
        nonce = headers.get("wechatpay-nonce", "")
        signature_b64 = headers.get("wechatpay-signature", "")
        serial = headers.get("wechatpay-serial", "")

        if not all([timestamp, nonce, signature_b64, serial]):
            missing = [
                name
                for name, val in [
                    ("Wechatpay-Timestamp", timestamp),
                    ("Wechatpay-Nonce", nonce),
                    ("Wechatpay-Signature", signature_b64),
                    ("Wechatpay-Serial", serial),
                ]
                if not val
            ]
            raise BadRequestException(
                f"微信回调缺少必要 header: {', '.join(missing)}"
            )

        try:
            ts = int(timestamp)
        except (ValueError, TypeError):
            raise BadRequestException("微信回调时间戳格式无效")
        if abs(time.time() - ts) > 300:
            raise BadRequestException("微信回调时间戳过期，可能为重放攻击")

        verify_str = f"{timestamp}\n{nonce}\n{body.decode()}\n"
        public_key = self._load_platform_cert(serial)

        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding

        signature = base64.b64decode(signature_b64)
        try:
            public_key.verify(
                signature,
                verify_str.encode("utf-8"),
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
        except Exception as e:
            logger.warning(
                "WeChat callback signature verification failed: %s", e
            )
            raise BadRequestException("微信回调签名验证失败") from e

    def _decrypt_resource(self, resource: dict) -> dict[str, Any]:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        ciphertext_b64 = resource.get("ciphertext", "")
        nonce = resource.get("nonce", "")
        associated_data = resource.get("associated_data", "")

        if not ciphertext_b64:
            raise BadRequestException("微信回调 resource 缺少 ciphertext")

        key = self.api_key_v3.encode("utf-8")
        if len(key) != 32:
            raise BadRequestException("api_key_v3 长度必须为 32 字节")

        ciphertext = base64.b64decode(ciphertext_b64)
        aesgcm = AESGCM(key)
        try:
            plaintext = aesgcm.decrypt(
                nonce.encode("utf-8"),
                ciphertext,
                associated_data.encode("utf-8") if associated_data else None,
            )
        except Exception as e:
            logger.warning(
                "WeChat callback AES-GCM decryption failed: %s", e
            )
            raise BadRequestException("微信回调解密失败") from e
        return json.loads(plaintext)

    def _load_platform_cert(self, serial: str) -> Any:
        cert_path = self.platform_cert_path
        if not cert_path:
            raise BadRequestException(
                "未配置微信平台证书路径 (WECHAT_PAY_PLATFORM_CERT_PATH)"
            )

        cache_key = f"{cert_path}:{serial}"
        with _cert_cache_lock:
            if cache_key in _platform_cert_cache:
                return _platform_cert_cache[cache_key]

        from cryptography import x509

        try:
            with open(cert_path, "rb") as f:
                cert = x509.load_pem_x509_certificate(f.read())
        except FileNotFoundError:
            raise BadRequestException(
                f"微信平台证书文件不存在: {cert_path}"
            )
        except Exception as e:
            raise BadRequestException(
                f"微信平台证书加载失败: {e}"
            ) from e

        public_key = cert.public_key()
        with _cert_cache_lock:
            _platform_cert_cache[cache_key] = public_key
        return public_key

    def _build_auth_header(
        self, method: str, path: str, body: Any
    ) -> dict[str, str]:
        timestamp = str(int(time.time()))
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
        if not self.private_key_path:
            return "mock_rsa_signature"
        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import padding

            with open(self.private_key_path, "rb") as f:
                private_key = serialization.load_pem_private_key(
                    f.read(), password=None
                )
            sig = private_key.sign(
                message.encode("utf-8"),
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
            return base64.b64encode(sig).decode("utf-8")
        except Exception as e:
            logger.error("RSA sign failed: %s", e)
            return "sign_error"
