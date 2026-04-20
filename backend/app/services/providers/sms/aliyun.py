"""
Aliyun (Alibaba Cloud) SMS provider — production implementation (C5).

Uses httpx to call Aliyun Dysmsapi via HMAC-SHA1 signed HTTP requests.
No heavy alibabacloud-* SDK dependency required.

Configuration
-------------
Reads from ``app.config.settings``:
- ``sms_access_key``   — Aliyun AccessKey ID
- ``sms_access_secret`` — Aliyun AccessKey Secret
- ``sms_sign_name``    — SMS signature (审核通过)
- ``sms_template_code`` — OTP template ID

Error handling
--------------
- Aliyun ``Code == "OK"`` → success
- Business errors (e.g. ``isv.MOBILE_NUMBER_ILLEGAL``) → ``NonRetryableError``
- Network / 5xx → ``RetryableError`` (outbound decorator retries)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
import uuid
from typing import Any
from urllib.parse import quote_plus

import httpx

from app.config import settings
from app.services.providers.sms.base import (
    SMSProvider,
    SMSResult,
    mask_phone_sms,
)
from app.utils.outbound import NonRetryableError, RetryableError, outbound_call

logger = logging.getLogger(__name__)


# Configuration items that MUST be present before this provider can be
# considered production-ready.
REQUIRED_PRODUCTION_SETTINGS: tuple[str, ...] = (
    "SMS_ACCESS_KEY",
    "SMS_ACCESS_SECRET",
    "SMS_SIGN_NAME",
    "SMS_TEMPLATE_CODE",
)

# Aliyun business error codes that should NOT be retried.
_NON_RETRYABLE_CODES: frozenset[str] = frozenset({
    "isv.MOBILE_NUMBER_ILLEGAL",
    "isv.TEMPLATE_MISSING_PARAMETERS",
    "isv.INVALID_PARAMETERS",
    "isv.BUSINESS_LIMIT_CONTROL",
    "isv.DENY_IP_RANGE",
    "isv.SMS_SIGN_ILLEGAL",
    "isv.SMS_TEMPLATE_ILLEGAL",
    "isv.ACCOUNT_ABNORMAL",
    "isv.ACCOUNT_NOT_EXISTS",
    "isv.AMOUNT_NOT_ENOUGH",
})

DYSMSAPI_ENDPOINT = "https://dysmsapi.aliyuncs.com/"


class AliyunSMSProvider(SMSProvider):
    """Aliyun Dysmsapi SMS provider."""

    name = "aliyun"

    def __init__(self) -> None:
        self.access_key = settings.sms_access_key
        self.access_secret = settings.sms_access_secret
        self.sign_name = settings.sms_sign_name
        self.template_code = settings.sms_template_code
        if not self.access_key or not self.access_secret:
            raise ValueError(
                "AliyunSMSProvider requires SMS_ACCESS_KEY and SMS_ACCESS_SECRET. "
                "Set SMS_PROVIDER=mock for development without credentials."
            )

    # ------------------------------------------------------------------ API

    @outbound_call(provider="aliyun_sms", timeout=5.0, max_retries=2)
    async def send_otp(
        self,
        phone: str,
        code: str,
        template_id: str | None = None,
    ) -> SMSResult:
        tpl = template_id or self.template_code
        template_param = json.dumps({"code": code})
        return await self._send_sms(phone, tpl, template_param)

    @outbound_call(provider="aliyun_sms", timeout=5.0, max_retries=2)
    async def send_notification(
        self,
        phone: str,
        template_id: str,
        params: dict[str, Any] | None = None,
    ) -> SMSResult:
        template_param = json.dumps(params or {})
        return await self._send_sms(phone, template_id, template_param)

    # --------------------------------------------------------------- internal

    async def _send_sms(
        self, phone: str, template_code: str, template_param: str
    ) -> SMSResult:
        masked = mask_phone_sms(phone)
        params = self._build_params(phone, template_code, template_param)
        signature = self._sign(params)
        params["Signature"] = signature

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    DYSMSAPI_ENDPOINT,
                    params=params,
                    timeout=10,
                )
        except (httpx.TimeoutException, httpx.ConnectError, OSError) as exc:
            logger.error(
                "[aliyun-sms] network error phone=%s: %s", masked, exc
            )
            raise RetryableError(f"Aliyun SMS network error: {exc}") from exc

        if resp.status_code >= 500:
            logger.error(
                "[aliyun-sms] server error phone=%s status=%d",
                masked,
                resp.status_code,
            )
            raise RetryableError(
                f"Aliyun SMS server error: HTTP {resp.status_code}"
            )

        data = resp.json()
        aliyun_code = data.get("Code", "")
        biz_id = data.get("BizId", "")

        if aliyun_code == "OK":
            logger.info("[aliyun-sms] sent phone=%s biz_id=%s", masked, biz_id)
            return SMSResult(
                ok=True,
                provider=self.name,
                extra={"biz_id": biz_id, "masked_phone": masked},
            )

        # Business error
        message = data.get("Message", "")
        logger.error(
            "[aliyun-sms] biz error phone=%s code=%s message=%s",
            masked,
            aliyun_code,
            message,
        )

        if aliyun_code in _NON_RETRYABLE_CODES:
            raise NonRetryableError(
                f"Aliyun SMS rejected: {aliyun_code} — {message}"
            )

        # Unknown error code — treat as retryable
        raise RetryableError(
            f"Aliyun SMS error: {aliyun_code} — {message}"
        )

    def _build_params(
        self, phone: str, template_code: str, template_param: str
    ) -> dict[str, str]:
        return {
            "AccessKeyId": self.access_key,
            "Action": "SendSms",
            "Format": "JSON",
            "PhoneNumbers": phone,
            "RegionId": "cn-hangzhou",
            "SignName": self.sign_name,
            "SignatureMethod": "HMAC-SHA1",
            "SignatureNonce": str(uuid.uuid4()),
            "SignatureVersion": "1.0",
            "TemplateCode": template_code,
            "TemplateParam": template_param,
            "Timestamp": time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
            ),
            "Version": "2017-05-25",
        }

    def _sign(self, params: dict[str, str]) -> str:
        sorted_params = sorted(params.items())
        query_string = "&".join(
            f"{quote_plus(k)}={quote_plus(v)}" for k, v in sorted_params
        )
        sign_str = f"GET&{quote_plus('/')}&{quote_plus(query_string)}"
        signature = base64.b64encode(
            hmac.new(
                f"{self.access_secret}&".encode("utf-8"),
                sign_str.encode("utf-8"),
                hashlib.sha1,
            ).digest()
        ).decode("utf-8")
        return signature
