"""
PaymentService DTOs — data-transfer objects returned by the service.

Kept in a small standalone module so both :mod:`app.services.payment`
(the package ``__init__``, re-exports for callers) and the internal
mixins (``lifecycle`` / ``refund`` which construct these results)
can import them without a circular ``payment.__init__ -> mixin ->
payment.__init__`` cycle.

Behaviour is bit-identical to the pre-split ``payment_service.py``
(pure structural move).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any


@dataclass
class PrepayResult:
    """Returned to the caller after creating a prepay order."""

    payment_id: uuid.UUID
    provider: str  # "mock" | "wechat"
    prepay_id: str | None = None
    sign_params: dict[str, Any] | None = None
    mock_success: bool = False


@dataclass
class RefundResult:
    payment_id: uuid.UUID
    provider: str
    refund_id: str | None = None
    mock_success: bool = False
