"""
PaymentService package — mixin-composed orchestration layer.

ADR-0060: PaymentService is composed from 5 mixins:

  * :class:`_PaymentServiceBase`      -- ``__init__``, ``_set_payment_state``,
                                          ``_set_refund_state``
  * :class:`_PaymentLifecycleMixin`   -- ``create_prepay``, ``close_pending_payment``
  * :class:`_PaymentCallbackMixin`    -- ``record_callback_or_skip``,
                                          ``is_callback_processed``,
                                          ``handle_pay_callback``,
                                          ``handle_refund_callback``
  * :class:`_PaymentRefundMixin`      -- ``create_refund``
  * :class:`_PaymentLedgerMixin`      -- ``_resolve_companion_user_id``,
                                          ``_append_pay_ledger_safe``,
                                          ``_append_refund_ledger_safe``

MRO (ADR-0060 §5, 雷区2): ``PaymentService(callback, lifecycle, refund,
ledger, _base)`` — callback comes first so ``handle_pay_callback``'s
cross-mixin ``self.create_refund`` call (L388-style late-callback
auto-refund) resolves via the MRO into ``_PaymentRefundMixin``.

Module-level re-exports (ADR-0060 §5, 雷区1): ``settings`` /
``MockPaymentProvider`` / ``WechatPaymentProvider`` / ``PaymentProvider``
/ ``_platform_cert_cache`` are re-exported so that existing tests using
``monkeypatch.setattr("app.services.payment_service.settings.XXX", ...)``
keep hitting the real ``app.config.settings`` object (15 patch targets in
``tests/test_wechat_verify_callback.py``). The old
``app.services.payment_service`` module is retained as a re-export shim
of this package.
"""

from __future__ import annotations

# --- module-level re-exports (雷区1: patch target compatibility) ---
from app.config import (
    settings,  # noqa: F401  (re-exported for legacy tests using monkeypatch on payment_service.settings)
)

# --- mixin building blocks ---
from app.services.payment._base import _PaymentServiceBase

# --- DTO (defined in _dto.py to avoid circular imports with mixins) ---
from app.services.payment._dto import PrepayResult, RefundResult
from app.services.payment.callback import _PaymentCallbackMixin
from app.services.payment.ledger import _PaymentLedgerMixin
from app.services.payment.lifecycle import _PaymentLifecycleMixin
from app.services.payment.refund import _PaymentRefundMixin
from app.services.providers.payment import (
    MockPaymentProvider,
    PaymentProvider,
    WechatPaymentProvider,
    get_payment_provider,  # noqa: F401  (re-exported for legacy imports)
)
from app.services.providers.payment.wechat import (
    _platform_cert_cache,  # noqa: F401  (re-exported for legacy tests)
)

# ---------------------------------------------------------------------------
# PaymentService — composed via MRO
# ---------------------------------------------------------------------------

class PaymentService(
    _PaymentCallbackMixin,
    _PaymentLifecycleMixin,
    _PaymentRefundMixin,
    _PaymentLedgerMixin,
    _PaymentServiceBase,
):
    """
    Orchestrates payment lifecycle: prepay → callback → refund.

    Owns ``Payment`` + ``PaymentCallbackLog`` persistence; OrderService
    delegates here.
    """


__all__ = [
    "PrepayResult",
    "RefundResult",
    "PaymentService",
    # legacy re-exports (don't remove without migrating tests)
    "PaymentProvider",
    "MockPaymentProvider",
    "WechatPaymentProvider",
]
