"""Provider factory — selects implementation by ``settings.payment_provider``."""

from __future__ import annotations

from app.config import settings
from app.services.providers.payment.base import PaymentProvider
from app.services.providers.payment.mock import MockPaymentProvider
from app.services.providers.payment.wechat import WechatPaymentProvider


def get_payment_provider() -> PaymentProvider:
    """
    Return a payment provider instance honouring ``settings.payment_provider``.

    Recognised values:
        * ``"mock"``   (default) — instant-success ``MockPaymentProvider``
        * ``"wechat"``           — WeChat Pay v3 ``WechatPaymentProvider``

    Unknown values fall back to mock with a warning logged at the call site.
    """
    name = getattr(settings, "payment_provider", "mock")
    if name == "wechat":
        return WechatPaymentProvider()
    return MockPaymentProvider()
