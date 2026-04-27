"""OrderService — composed via mixins (SP-01).

Original `app/services/order.py` (708 LOC) was split into 5 mixins
to honour single-responsibility per file. The composed `OrderService`
class exposed here is bit-compatible with the legacy module:

  - same import path: `from app.services.order import OrderService`
  - same constructor signature
  - same public method set
  - same module-level names (`logger`, `PaymentService`, `SERVICE_PRICES`,
    `generate_order_number`, `ORDER_EXPIRY_HOURS`) so existing test
    `patch("app.services.order.<X>")` calls keep working unchanged.

See `_base.py`, `query.py`, `lifecycle.py`, `cancel.py`, `payment.py`,
`expiry.py` for the per-domain implementations.
"""
from __future__ import annotations

# Re-export module-level names that tests / other modules reach into.
from app.models.order import SERVICE_PRICES  # noqa: F401  (public re-export)
from app.services.payment_service import PaymentService  # noqa: F401  (test patch target)

from ._base import (  # noqa: F401  (public re-exports)
    ORDER_EXPIRY_HOURS,
    _OrderServiceBase,
    generate_order_number,
    logger,
)
from .cancel import _OrderCancelMixin
from .expiry import _OrderExpiryMixin
from .lifecycle import _OrderLifecycleMixin
from .payment import _OrderPaymentMixin
from .query import _OrderQueryMixin


class OrderService(
    _OrderQueryMixin,
    _OrderLifecycleMixin,
    _OrderCancelMixin,
    _OrderPaymentMixin,
    _OrderExpiryMixin,
    _OrderServiceBase,
):
    """Façade combining all domain mixins.

    MRO order matters only when methods overlap — current mixins do not
    overlap, so any order works. Listed query → lifecycle → cancel →
    payment → expiry roughly mirrors the order surface from the API.
    """

    pass


__all__ = [
    "OrderService",
    "PaymentService",
    "SERVICE_PRICES",
    "ORDER_EXPIRY_HOURS",
    "generate_order_number",
    "logger",
]
