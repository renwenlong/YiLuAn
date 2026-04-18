"""
SMS provider adapters (P0-2, Action #2).

Mirrors ``app.services.providers.payment``:

    from app.services.providers.sms import get_sms_provider

    provider = get_sms_provider()  # honours settings.sms_provider
    result = await provider.send_otp(phone, code)
    if not result.ok:
        ...

Concrete providers
------------------
* :class:`MockSMSProvider` — dev/test, no network.
* :class:`AliyunSMSProvider` — Aliyun Dysmsapi placeholder
  (raises ``NotImplementedError`` until activation).

The legacy module ``app.services.sms`` keeps its old class names
exported for backward compatibility with existing call sites and
tests; new code should import from this package.
"""

from app.services.providers.sms.aliyun import (
    REQUIRED_PRODUCTION_SETTINGS as ALIYUN_REQUIRED_PRODUCTION_SETTINGS,
    AliyunSMSProvider,
)
from app.services.providers.sms.base import (
    SMSProvider,
    SMSResult,
    mask_phone_sms,
)
from app.services.providers.sms.factory import get_sms_provider
from app.services.providers.sms.mock import MockSMSProvider
from app.services.providers.sms.rate_limit import (
    RateLimitDecision,
    SMSRateLimiter,
    reset_inproc_store,
)

__all__ = [
    "SMSProvider",
    "SMSResult",
    "MockSMSProvider",
    "AliyunSMSProvider",
    "ALIYUN_REQUIRED_PRODUCTION_SETTINGS",
    "get_sms_provider",
    "SMSRateLimiter",
    "RateLimitDecision",
    "mask_phone_sms",
    "reset_inproc_store",
]
