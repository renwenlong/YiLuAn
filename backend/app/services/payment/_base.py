"""
PaymentService base mixin — shared init + cross-domain state mirrors.

ADR-0060 §4: ``_PaymentServiceBase`` owns ``__init__`` (repo/session/
provider/ledger_writer) and the order state-mirror helpers
(``_set_payment_state`` / ``_set_refund_state``) that are shared across
the pay + refund paths. All other mixins inherit from this base so that
``self.session/repo/provider/ledger_writer`` and the shared private
state-mirror methods stay reachable across the MRO.

Behaviour is bit-identical to the pre-split ``payment_service.py``
(pure structural move, no logic changes).
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Order, PaymentState, RefundState
from app.repositories.payment import PaymentRepository
from app.services.wallet_ledger_writer import WalletLedgerWriter

logger = logging.getLogger(__name__)


class _PaymentServiceBase:
    """Shared state + order sub-state mirror helpers for PaymentService mixins."""

    def __init__(self, session: AsyncSession):
        self.repo = PaymentRepository(session)
        self.session = session
        # ADR-0060 雷区1: attribute-lookup on ``payment_service`` shim so
        # tests' ``monkeypatch.setattr("app.services.payment_service.get_payment_provider", ...)``
        # is honoured. Local ``from ... import get_payment_provider`` here
        # would freeze the reference and bypass the patch. Import is done
        # inside ``__init__`` to avoid the ``payment._base -> payment_service
        # -> payment.__init__ -> payment._base`` cycle at module load.
        from app.services import payment_service as _ps_module
        self.provider = _ps_module.get_payment_provider()
        # [TD-MONEY-01 M1 finishing] 钱包账本写入器
        self.ledger_writer = WalletLedgerWriter(session)

    # -- wallet_ledger helpers (TD-MONEY-01 M1 finishing) --------------------

    # -- H2-be sub-state helpers ---------------------------------------------

    async def _set_payment_state(
        self, order_id: uuid.UUID | None, state: PaymentState
    ) -> None:
        """Best-effort write of ``orders.payment_state``.

        Never raises — fund-side state is auxiliary; missing orders or
        DB hiccups must not break the payment write path.
        """
        if order_id is None:
            return
        try:
            order = (
                await self.session.execute(
                    select(Order).where(Order.id == order_id)
                )
            ).scalar_one_or_none()
            if order is None:
                return
            if order.payment_state != state:
                order.payment_state = state
                await self.session.flush()
        except Exception as exc:  # pragma: no cover - defence only
            logger.warning(
                "payment_state update failed (non-fatal) order=%s state=%s err=%s",
                order_id,
                state,
                exc,
            )

    async def _set_refund_state(
        self, order_id: uuid.UUID | None, state: RefundState
    ) -> None:
        """Best-effort write of ``orders.refund_state`` (mirror of the helper above)."""
        if order_id is None:
            return
        try:
            order = (
                await self.session.execute(
                    select(Order).where(Order.id == order_id)
                )
            ).scalar_one_or_none()
            if order is None:
                return
            if order.refund_state != state:
                order.refund_state = state
                await self.session.flush()
        except Exception as exc:  # pragma: no cover - defence only
            logger.warning(
                "refund_state update failed (non-fatal) order=%s state=%s err=%s",
                order_id,
                state,
                exc,
            )
