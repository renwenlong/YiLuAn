"""
Payment provider adapters.

This package implements the provider abstraction described in the P0-1
architecture refactor. The goal is to keep ``payment_service.py`` agnostic
of any specific PSP (Payment Service Provider) and to allow swapping the
real WeChat Pay implementation in via configuration only
(``settings.payment_provider`` = ``"mock"`` | ``"wechat"``).

Usage
-----

    from app.services.providers.payment import get_payment_provider

    provider = get_payment_provider()  # honours settings.payment_provider
    await provider.create_order(order_dto)
    await provider.verify_callback(headers, body)
    await provider.refund(order_dto)
    await provider.query(order_dto)

The new high-level API (``create_order``/``verify_callback``/``refund``/
``query``) is the long-term contract. The legacy methods
(``create_prepay``/``create_refund``) are kept on the base class for
backward compatibility with the existing ``PaymentService`` orchestration
code and tests; they delegate to the new methods.
"""

from app.services.providers.payment.base import (
    OrderDTO,
    PaymentProvider,
    RefundDTO,
)
from app.services.providers.payment.factory import get_payment_provider
from app.services.providers.payment.mock import MockPaymentProvider
from app.services.providers.payment.wechat import WechatPaymentProvider

__all__ = [
    "OrderDTO",
    "RefundDTO",
    "PaymentProvider",
    "MockPaymentProvider",
    "WechatPaymentProvider",
    "get_payment_provider",
]
