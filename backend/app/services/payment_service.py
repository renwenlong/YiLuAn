"""
Payment Service — legacy shim.

ADR-0060: The real implementation lives in :mod:`app.services.payment`
(a package with 5 mixins). This module is retained purely as a
re-export shim so that:

  * Existing imports ``from app.services.payment_service import
    PaymentService`` (and the DTO + legacy provider names) keep working
    without any call-site changes.

  * Existing tests using ``monkeypatch.setattr(
    "app.services.payment_service.settings.XXX", ...)`` keep hitting the
    real :data:`app.config.settings` object (15 patch targets in
    ``tests/test_wechat_verify_callback.py``). This works because we
    re-export the same ``settings`` module attribute at package init +
    here — both point at the identical ``app.config.settings`` object,
    so ``monkeypatch`` on either path mutates the real settings.

Do NOT add new logic here — extend the mixins in :mod:`app.services.payment`
instead. Behaviour is bit-identical to the pre-split single-file version
(pure structural move).
"""

from __future__ import annotations

# Re-export the whole package's public + legacy surface.
# The concrete objects (settings, providers, DTOs, PaymentService,
# _platform_cert_cache) are all defined in / re-exported by
# ``app.services.payment.__init__``; importing them here keeps
# ``app.services.payment_service.<name>`` as a stable module attribute.
from app.services.payment import (  # noqa: F401
    MockPaymentProvider,
    PaymentProvider,
    PaymentService,
    PrepayResult,
    RefundResult,
    WechatPaymentProvider,
    _platform_cert_cache,
    get_payment_provider,
    settings,
)

__all__ = [
    "PrepayResult",
    "RefundResult",
    "PaymentService",
    # legacy re-exports (don't remove without migrating tests)
    "PaymentProvider",
    "MockPaymentProvider",
    "WechatPaymentProvider",
]
