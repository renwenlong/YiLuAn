"""[D-046] Provider abstract API contract tests.

These tests **freeze** the public abstract interface of the payment and
SMS providers. Any signature drift — added arg, renamed kwarg, dropped
async — fails the test immediately.

Why this exists: provider stubs are widely mocked across ~16 service-layer
tests; if the abstract contract drifts, mocks no longer match real
implementations, but the suite stays green because mocks happily accept
anything. See DECISION_LOG.md D-046.

If you genuinely need to change the contract:
1. Update the ADR / DECISION_LOG with rationale.
2. Update both real (``WechatPaymentProvider`` / ``AliyunSMSProvider``)
   and mock implementations.
3. Update this test in the same PR.
"""
from __future__ import annotations

import inspect

import pytest

from app.services.providers.payment.base import (
    OrderDTO,
    PaymentProvider,
    RefundDTO,
)
from app.services.providers.sms.base import SMSProvider, SMSResult


# ---------------------------------------------------------------------------
# PaymentProvider
# ---------------------------------------------------------------------------
def _signature_params(fn) -> dict[str, str]:
    """Return ``{name: kind_name}`` for a callable's signature.

    Strips type-annotation noise; stable enough to detect drift while
    tolerating the ``Any`` / ``dict[str, Any]`` swap.
    """
    sig = inspect.signature(fn)
    return {name: param.kind.name for name, param in sig.parameters.items()}


def test_payment_provider_method_set_is_frozen():
    """The set of methods on the abstract base is intentionally narrow."""
    expected = {
        "create_order",
        "verify_callback",
        "refund",
        "query",
        "close_order",
        # Legacy delegates kept for backward compat with PaymentService.
        "create_prepay",
        "create_refund",
    }
    actual = {
        n
        for n, m in inspect.getmembers(PaymentProvider, predicate=inspect.isfunction)
        if not n.startswith("_")
    }
    missing = expected - actual
    extra = actual - expected
    assert not missing, f"PaymentProvider lost methods: {missing}"
    assert not extra, (
        f"PaymentProvider gained methods without updating D-046 contract: {extra}"
    )


def test_payment_provider_create_order_signature():
    assert _signature_params(PaymentProvider.create_order) == {
        "self": "POSITIONAL_OR_KEYWORD",
        "order": "POSITIONAL_OR_KEYWORD",
    }
    assert inspect.iscoroutinefunction(PaymentProvider.create_order)


def test_payment_provider_verify_callback_signature():
    assert _signature_params(PaymentProvider.verify_callback) == {
        "self": "POSITIONAL_OR_KEYWORD",
        "headers": "POSITIONAL_OR_KEYWORD",
        "body": "POSITIONAL_OR_KEYWORD",
    }
    assert inspect.iscoroutinefunction(PaymentProvider.verify_callback)


def test_payment_provider_refund_signature():
    assert _signature_params(PaymentProvider.refund) == {
        "self": "POSITIONAL_OR_KEYWORD",
        "refund": "POSITIONAL_OR_KEYWORD",
    }
    assert inspect.iscoroutinefunction(PaymentProvider.refund)


def test_payment_provider_query_signature():
    assert _signature_params(PaymentProvider.query) == {
        "self": "POSITIONAL_OR_KEYWORD",
        "order": "POSITIONAL_OR_KEYWORD",
    }
    assert inspect.iscoroutinefunction(PaymentProvider.query)


def test_payment_provider_close_order_signature():
    assert _signature_params(PaymentProvider.close_order) == {
        "self": "POSITIONAL_OR_KEYWORD",
        "out_trade_no": "POSITIONAL_OR_KEYWORD",
    }


def test_order_dto_fields_frozen():
    fields = {f.name for f in OrderDTO.__dataclass_fields__.values()}
    assert fields == {"order_number", "amount_yuan", "description", "openid"}


def test_refund_dto_fields_frozen():
    fields = {f.name for f in RefundDTO.__dataclass_fields__.values()}
    assert fields == {"trade_no", "refund_id", "total_yuan", "refund_yuan"}


# ---------------------------------------------------------------------------
# SMSProvider
# ---------------------------------------------------------------------------
def test_sms_provider_method_set_is_frozen():
    expected = {"send_otp", "send_notification"}
    actual = {
        n
        for n, m in inspect.getmembers(SMSProvider, predicate=inspect.isfunction)
        if not n.startswith("_")
    }
    missing = expected - actual
    extra = actual - expected
    assert not missing, f"SMSProvider lost methods: {missing}"
    assert not extra, (
        f"SMSProvider gained methods without updating D-046 contract: {extra}"
    )


def test_sms_provider_send_otp_signature():
    assert _signature_params(SMSProvider.send_otp) == {
        "self": "POSITIONAL_OR_KEYWORD",
        "phone": "POSITIONAL_OR_KEYWORD",
        "code": "POSITIONAL_OR_KEYWORD",
        "template_id": "POSITIONAL_OR_KEYWORD",
    }
    assert inspect.iscoroutinefunction(SMSProvider.send_otp)


def test_sms_provider_send_notification_signature():
    assert _signature_params(SMSProvider.send_notification) == {
        "self": "POSITIONAL_OR_KEYWORD",
        "phone": "POSITIONAL_OR_KEYWORD",
        "template_id": "POSITIONAL_OR_KEYWORD",
        "params": "POSITIONAL_OR_KEYWORD",
    }
    assert inspect.iscoroutinefunction(SMSProvider.send_notification)


def test_sms_result_fields_frozen():
    fields = {f.name for f in SMSResult.__dataclass_fields__.values()}
    assert fields == {"ok", "code", "message", "provider", "extra"}


@pytest.mark.parametrize(
    "method",
    [
        PaymentProvider.create_order,
        PaymentProvider.verify_callback,
        PaymentProvider.refund,
        PaymentProvider.query,
        PaymentProvider.close_order,
        SMSProvider.send_otp,
        SMSProvider.send_notification,
    ],
)
def test_abstract_methods_raise_not_implemented(method):
    """The abstract methods must remain pure abstract (or raise) on the base.

    Subclasses are expected to override; calling the base directly should
    not silently return None.
    """
    src = inspect.getsource(method)
    assert "NotImplementedError" in src, (
        f"{method.__qualname__} no longer raises NotImplementedError on the base"
    )
