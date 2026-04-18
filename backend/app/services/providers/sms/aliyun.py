"""
Aliyun (Alibaba Cloud) SMS provider — production placeholder (P0-2).

Status
------
This module is a **strict placeholder**. Unlike the legacy
``app.services.sms.AliyunSMSProvider`` (which silently fell back to a
mock when credentials were missing — dangerous in prod), this provider
**raises NotImplementedError** until a real Dysmsapi integration lands.

Activation requires:

1. ALL settings in :data:`REQUIRED_PRODUCTION_SETTINGS` populated.
2. ``settings.sms_provider = "aliyun"``.
3. The TODO marked at the bottom of this module to be addressed
   (real SDK call + signature + structured error mapping).

Refusing to "soft fail" is intentional — silent fallback to the mock
provider in production would mean OTP login appears to work but no
SMS is actually delivered, locking users out and corrupting metrics.

See also
--------
* ``docs/TODO_CREDENTIALS.md`` — credential checklist (Aliyun SMS section)
* ``docs/DECISION_LOG.md`` — D-024 (this provider abstraction)
"""

from __future__ import annotations

import logging
from typing import Any

from app.config import settings
from app.services.providers.sms.base import (
    SMSProvider,
    SMSResult,
    mask_phone_sms,
)

logger = logging.getLogger(__name__)


# Configuration items that MUST be present before this provider can be
# considered production-ready. Surfaced as a constant so ops tooling
# and tests can introspect the contract without parsing this docstring.
REQUIRED_PRODUCTION_SETTINGS: tuple[str, ...] = (
    "SMS_ACCESS_KEY",            # 阿里云 AccessKey ID
    "SMS_ACCESS_SECRET",         # 阿里云 AccessKey Secret
    "SMS_REGION",                # SMS API region, e.g. cn-hangzhou (default ok)
    "SMS_SIGN_NAME",             # 短信签名（控制台已审核通过）
    "SMS_TEMPLATE_CODE",         # OTP 模板 ID（如 SMS_123456789）
    "SMS_NOTIFY_TEMPLATE_CODE",  # 通用通知模板 ID
    "SMS_RATE_LIMIT_PER_MINUTE", # 单号 60s 限频阈值（推荐 1）
    "SMS_RATE_LIMIT_PER_HOUR",   # 单号 1h 限额阈值（推荐 5）
)


class AliyunSMSProvider(SMSProvider):
    """Aliyun Dysmsapi SMS provider — placeholder."""

    name = "aliyun"

    def __init__(self) -> None:
        self.access_key = settings.sms_access_key
        self.access_secret = settings.sms_access_secret
        self.sign_name = settings.sms_sign_name
        self.template_code = settings.sms_template_code

    # ------------------------------------------------------------------ API

    async def send_otp(
        self,
        phone: str,
        code: str,
        template_id: str | None = None,
    ) -> SMSResult:
        return self._not_implemented(phone, kind="otp", template=template_id or self.template_code)

    async def send_notification(
        self,
        phone: str,
        template_id: str,
        params: dict[str, Any] | None = None,
    ) -> SMSResult:
        return self._not_implemented(phone, kind="notification", template=template_id)

    # --------------------------------------------------------------- helpers

    def _not_implemented(self, phone: str, *, kind: str, template: str | None) -> SMSResult:
        masked = mask_phone_sms(phone)
        missing = [n for n in REQUIRED_PRODUCTION_SETTINGS if not getattr(settings, n.lower(), "")]
        # Always emit a structured error log so ops can trace activation.
        logger.error(
            "[aliyun-sms] real provider not implemented yet (kind=%s phone=%s template=%s). "
            "Required production settings: %s. Missing: %s",
            kind,
            masked,
            template,
            list(REQUIRED_PRODUCTION_SETTINGS),
            missing,
        )
        raise NotImplementedError(
            f"AliyunSMSProvider.{kind} is a placeholder. "
            f"Required production settings: {list(REQUIRED_PRODUCTION_SETTINGS)}. "
            f"See docs/TODO_CREDENTIALS.md (Aliyun SMS section) and DECISION_LOG.md D-024."
        )


# TODO (real Aliyun SMS hardening):
#   * Replace _not_implemented with HMAC-SHA1 signed GET to dysmsapi.aliyuncs.com
#     (see legacy implementation in app/services/sms.py for a reference skeleton —
#     it must be hardened: no silent fallback, structured SMSResult on every code path,
#     retry with exponential backoff on 5xx / network).
#   * Map Aliyun BizCode → SMSResult.code (rate_limited / provider_error / ok).
#   * Wire metrics: per-template send count, latency p95, success rate.
#   * Auto-rotate AccessKey via Azure Key Vault (rotate every 90d).
