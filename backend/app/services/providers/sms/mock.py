"""Mock SMS provider for dev / test (P0-2).

Behaviour
---------
* Never makes a network call.
* Always returns ``SMSResult(ok=True)``.
* Prints the OTP to stdout in ``settings.environment == "development"``
  to keep the existing local-dev workflow working.
* Logs use the masked phone form (``138****0001``).

The "万能 OTP 000000" convention is enforced upstream in
``AuthService.verify_otp`` (it bypasses the Redis-stored code only when
``environment == "development"`` AND the user types ``000000``).
The mock provider deliberately does NOT pin any specific code — it
simply echoes whatever the caller generated, so the upstream randomness
contract is preserved.
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


class MockSMSProvider(SMSProvider):
    name = "mock"

    async def send_otp(
        self,
        phone: str,
        code: str,
        template_id: str | None = None,
    ) -> SMSResult:
        masked = mask_phone_sms(phone)
        logger.info("[mock-sms] OTP queued for %s (template=%s)", masked, template_id or "default")
        if settings.environment == "development":
            # Local-dev convenience print. Never executed in prod
            # (and prod would never select the mock provider anyway).
            print(f"[DEV] OTP for {phone}: {code}")
        return SMSResult(ok=True, provider=self.name, extra={"masked_phone": masked})

    async def send_notification(
        self,
        phone: str,
        template_id: str,
        params: dict[str, Any] | None = None,
    ) -> SMSResult:
        masked = mask_phone_sms(phone)
        logger.info(
            "[mock-sms] notification queued for %s template=%s params=%s",
            masked,
            template_id,
            list((params or {}).keys()),
        )
        return SMSResult(
            ok=True,
            provider=self.name,
            extra={"masked_phone": masked, "template_id": template_id},
        )
