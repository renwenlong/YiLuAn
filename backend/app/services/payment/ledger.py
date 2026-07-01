"""
PaymentService ledger mixin — wallet_ledger append helpers +
companion resolution.

ADR-0060 §4: ``_PaymentLedgerMixin`` owns the wallet_ledger side-effect
helpers (``_append_pay_ledger_safe`` / ``_append_refund_ledger_safe``)
and the companion-user resolver (``_resolve_companion_user_id``). All
are best-effort (log-only failure) since ledger append must not break
the payment write path. Behaviour is bit-identical to the pre-split
``payment_service.py`` (pure structural move).
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select

from app.models.order import Order
from app.models.payment import Payment
from app.services.payment._base import _PaymentServiceBase

logger = logging.getLogger(__name__)


class _PaymentLedgerMixin(_PaymentServiceBase):
    """Wallet_ledger append helpers + companion-user resolver."""

    async def _resolve_companion_user_id(self, order_id: uuid.UUID | None) -> uuid.UUID | None:
        """查订单 companion_id。None = 订单不存在 / 尚未匹配陪诊师。

        钱包账本是以**陪诊师**为主体的。payer (患者) 付钱、陪诊师收钱，
        所以 ledger.user_id 要写 companion，不是 payment.user_id (患者)。
        订单还没接单者 → 跳过 ledger（预付还没产生收入归属）。
        """
        if order_id is None:
            return None
        order = (
            await self.session.execute(
                select(Order).where(Order.id == order_id)
            )
        ).scalar_one_or_none()
        if order is None:
            return None
        return order.companion_id

    async def _append_pay_ledger_safe(self, payment: Payment) -> None:
        """支付成功 → 追加 ledger。失败不抛（不能拖累主业务），只 log。

        ``user_id`` = 订单的 companion_id（陪诊师），不是 payer。
        订单未接单 → 跳过（收入还没归属）。
        """
        companion_user_id = await self._resolve_companion_user_id(payment.order_id)
        if companion_user_id is None:
            logger.info(
                "wallet_ledger pay-skip: order=%s has no companion yet",
                payment.order_id,
            )
            return
        provider_txn_id = payment.trade_no or str(payment.id)
        try:
            await self.ledger_writer.record_pay_success(
                user_id=companion_user_id,
                order_id=payment.order_id,
                provider_txn_id=provider_txn_id,
                amount=payment.amount,
                occurred_at=payment.created_at,
            )
        except Exception as exc:  # pragma: no cover - defence only
            logger.error(
                "wallet_ledger pay-append failed (non-fatal) payment=%s err=%s",
                payment.id,
                exc,
                exc_info=True,
            )

    async def _append_refund_ledger_safe(self, refund: Payment) -> None:
        """退款成功 → 追加 ledger。失败不抛，只 log。

        ``user_id`` = 陪诊师。退款意味着陪诊师账本出账。
        ``provider_txn_id`` 优先用 ``refund_id``，与原支付 ledger 不冲突。
        """
        companion_user_id = await self._resolve_companion_user_id(refund.order_id)
        if companion_user_id is None:
            logger.info(
                "wallet_ledger refund-skip: order=%s has no companion",
                refund.order_id,
            )
            return
        if refund.refund_id:
            provider_txn_id = refund.refund_id
        elif refund.trade_no:
            provider_txn_id = f"{refund.trade_no}:refund"
        else:
            provider_txn_id = f"{refund.id}:refund"
        try:
            await self.ledger_writer.record_refund_success(
                user_id=companion_user_id,
                order_id=refund.order_id,
                provider_txn_id=provider_txn_id,
                amount=refund.amount,
                occurred_at=refund.created_at,
            )
        except Exception as exc:  # pragma: no cover - defence only
            logger.error(
                "wallet_ledger refund-append failed (non-fatal) refund=%s err=%s",
                refund.id,
                exc,
                exc_info=True,
            )
