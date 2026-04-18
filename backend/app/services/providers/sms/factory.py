"""Provider factory — selects implementation by ``settings.sms_provider``."""

from __future__ import annotations

import logging

from app.config import settings
from app.services.providers.sms.aliyun import AliyunSMSProvider
from app.services.providers.sms.base import SMSProvider
from app.services.providers.sms.mock import MockSMSProvider

logger = logging.getLogger(__name__)


def get_sms_provider() -> SMSProvider:
    """
    Return an SMS provider instance honouring ``settings.sms_provider``.

    Recognised values:
        * ``"mock"``   (default) — :class:`MockSMSProvider`, no network
        * ``"aliyun"``           — :class:`AliyunSMSProvider`, real Dysmsapi
                                   (currently a strict NotImplementedError
                                   placeholder; see module docstring).

    Unknown values fall back to the mock provider with a warning log.
    """
    name = getattr(settings, "sms_provider", "mock")
    if name == "aliyun":
        return AliyunSMSProvider()
    if name == "mock":
        return MockSMSProvider()
    logger.warning(
        "[sms] unknown sms_provider=%r, falling back to mock. Configure one of: mock, aliyun.",
        name,
    )
    return MockSMSProvider()
