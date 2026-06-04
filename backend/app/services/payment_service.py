"""
Payment Service — unified payment entry point.

Supports pluggable providers selected by ``settings.payment_provider``:

  * ``mock``   — instant success, for dev/test (default)
  * ``wechat`` — WeChat Pay v3 JSAPI (production)

Provider implementations live in :mod:`app.services.providers.payment`.
This module is the **orchestration layer**: it owns the ``Payment`` model
and the cross-provider concerns (idempotency, refund bookkeeping, etc.).

Backwards-compatibility re-exports
----------------------------------
Existing tests import ``MockPaymentProvider``, ``WechatPaymentProvider``
and ``PaymentProvider`` from this module. To avoid touching call-sites
during the P0-1 refactor, those names are re-exported below.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import (
    settings,  # noqa: F401  (re-exported for legacy tests using monkeypatch on payment_service.settings)
)
from app.exceptions import BadRequestException
from app.models.order import Order, PaymentState, RefundState
from app.models.payment import Payment
from app.models.payment_callback_log import PaymentCallbackLog
from app.repositories.payment import PaymentRepository
from app.services.providers.payment import (
    MockPaymentProvider,
    PaymentProvider,
    WechatPaymentProvider,
    get_payment_provider,
)
from app.services.providers.payment.base import _to_decimal
from app.services.providers.payment.wechat import (
    _platform_cert_cache,  # noqa: F401  (re-exported for legacy tests)
)
from app.services.wallet_ledger_writer import WalletLedgerWriter

logger = logging.getLogger(__name__)


__all__ = [
    "PrepayResult",
    "RefundResult",
    "PaymentService",
    # legacy re-exports (don't remove without migrating tests)
    "PaymentProvider",
    "MockPaymentProvider",
    "WechatPaymentProvider",
]


# ---------------------------------------------------------------------------
# Data transfer objects
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# PaymentService
# ---------------------------------------------------------------------------

class PaymentService:
    """
    Orchestrates payment lifecycle: prepay → callback → refund.

    Owns ``Payment`` + ``PaymentCallbackLog`` persistence; OrderService
    delegates here.
    """

    def __init__(self, session: AsyncSession):
        self.repo = PaymentRepository(session)
        self.session = session
        self.provider = get_payment_provider()
        # [TD-MONEY-01 M1 finishing] 钱包账本写入器
        self.ledger_writer = WalletLedgerWriter(session)

    # -- prepay ---------------------------------------------------------------

    async def create_prepay(
        self,
        order_id: uuid.UUID,
        order_number: str,
        user_id: uuid.UUID,
        amount: Decimal | int | float | str,
        description: str = "医路安陪诊服务",
        openid: str | None = None,
    ) -> PrepayResult:
        """Create a prepay order. Returns signing params for the client."""

        amount_dec = _to_decimal(amount).quantize(Decimal("0.01"))

        existing = await self.repo.get_by_order_and_type(order_id, "pay")
        if existing and existing.status == "success":
            raise BadRequestException("订单已支付，请勿重复操作")

        # D-058 F2: same-order retry while a prepay is still ``pending`` and
        # we already have a cached sign payload -> return it verbatim,
        # **without** re-hitting the PSP. Avoids wasted RPCs and keeps the
        # client's signing payload stable across retries.
        if (
            existing
            and existing.status == "pending"
            and existing.sign_params_cache
        ):
            is_mock_replay = isinstance(self.provider, MockPaymentProvider)
            try:
                cached_params = json.loads(existing.sign_params_cache)
            except json.JSONDecodeError:
                logger.warning(
                    "sign_params_cache corrupt for payment=%s — falling back to provider",
                    existing.id,
                )
            else:
                return PrepayResult(
                    payment_id=existing.id,
                    provider="mock" if is_mock_replay else "wechat",
                    prepay_id=existing.prepay_id,
                    sign_params=cached_params,
                    mock_success=False,
                )

        result = await self.provider.create_prepay(
            order_number=order_number,
            amount_yuan=amount_dec,
            description=description,
            openid=openid,
        )

        trade_no = result.get("trade_no", "")
        prepay_id = result.get("prepay_id")
        is_mock = isinstance(self.provider, MockPaymentProvider)

        payment = Payment(
            order_id=order_id,
            user_id=user_id,
            amount=amount_dec,
            payment_type="pay",
            status="success" if is_mock else "pending",
            trade_no=trade_no,
            prepay_id=prepay_id,
        )

        if existing and existing.status == "pending":
            existing.trade_no = trade_no
            existing.prepay_id = prepay_id
            existing.sign_params_cache = json.dumps(
                result.get("sign_params") or {}, default=str
            )
            if is_mock:
                existing.status = "success"
            await self.session.flush()
            payment = existing
        else:
            payment.sign_params_cache = json.dumps(
                result.get("sign_params") or {}, default=str
            )
            payment = await self.repo.create(payment)

        # H2-be: surface fund-side state on the order so the UI can show
        # “支付中 / 已付款” without coupling to OrderStatus.
        await self._set_payment_state(
            order_id,
            PaymentState.paid if payment.status == "success" else PaymentState.paying,
        )

        # Mock provider 即时成功 → 同步追加 ledger（生产 wechat 等回调）
        if is_mock and payment.status == "success":
            await self._append_pay_ledger_safe(payment)

        return PrepayResult(
            payment_id=payment.id,
            provider="mock" if is_mock else "wechat",
            prepay_id=prepay_id,
            sign_params=result.get("sign_params"),
            mock_success=is_mock,
        )

    # -- callback idempotency -------------------------------------------------

    async def record_callback_or_skip(
        self,
        *,
        provider: str,
        transaction_id: str,
        callback_type: str = "pay",
        out_trade_no: str | None = None,
        raw_body: bytes | str | None = None,
    ) -> bool:
        """
        Insert a PaymentCallbackLog row keyed by (provider, transaction_id).

        Returns
        -------
        ``True`` if this is a **new** callback and the caller should proceed
        with business processing.
        ``False`` if the same notification was already accepted previously
        (duplicate); the caller must NOT re-apply state changes.
        """
        if not transaction_id:
            # [ADR-0035 §3 P0-C / W19-P0-06] No transaction_id == no idempotency
            # key. Previously we defaulted to ``True`` (let caller proceed)
            # which lets a misbehaving PSP poison the ledger via repeated
            # "new" callbacks. Reject + count metric so on-call sees it.
            from app.observability.payment_metrics import (
                PAYMENT_CALLBACK_EMPTY_TXN_TOTAL,
            )

            PAYMENT_CALLBACK_EMPTY_TXN_TOTAL.labels(
                provider=provider or "unknown",
                callback_type=callback_type or "unknown",
            ).inc()
            logger.warning(
                "Rejecting payment callback with empty transaction_id: "
                "provider=%s callback_type=%s",
                provider,
                callback_type,
            )
            return False

        body_str: str | None
        if isinstance(raw_body, bytes):
            body_str = raw_body.decode(errors="replace")[:4000]
        elif isinstance(raw_body, str):
            body_str = raw_body[:4000]
        else:
            body_str = None

        log = PaymentCallbackLog(
            provider=provider,
            transaction_id=transaction_id,
            callback_type=callback_type,
            out_trade_no=out_trade_no,
            status="processed",
            raw_body=body_str,
        )

        # Use a SAVEPOINT so a uniqueness violation does not poison the
        # outer session (FastAPI dependency holds an open transaction).
        try:
            async with self.session.begin_nested():
                self.session.add(log)
                await self.session.flush()
        except IntegrityError:
            logger.info(
                "Duplicate callback ignored: provider=%s txn=%s",
                provider,
                transaction_id,
            )
            return False
        return True

    async def is_callback_processed(
        self, provider: str, transaction_id: str
    ) -> bool:
        """Cheap pre-check used by tests / monitoring."""
        if not transaction_id:
            return False
        stmt = select(PaymentCallbackLog.id).where(
            PaymentCallbackLog.provider == provider,
            PaymentCallbackLog.transaction_id == transaction_id,
        )
        result = await self.session.execute(stmt)
        return result.first() is not None

    # -- callback -------------------------------------------------------------

    async def handle_pay_callback(
        self,
        trade_no: str,
        order_number: str,
        success: bool,
    ) -> Payment | None:
        """
        Process payment callback from WeChat.

        This method is **state-mutating only**; the endpoint MUST first
        call ``record_callback_or_skip`` and only invoke this when the
        callback is genuinely new.

        Even so, we still defensively short-circuit if the Payment row is
        already in a terminal state (success / failed) — this matters for
        the ``订单已关闭后回调`` scenario where the order was cancelled and
        the Payment record may already have been closed out.

        TD-PAY-01 defense: if the order is already in a terminal state
        (expired / cancelled / rejected) and the callback is SUCCESS,
        we still flip the pay row to ``success`` for accounting honesty,
        then issue an automatic refund in the same transaction. This
        guarantees the user never has money parked against a dead order.
        """
        from app.models.order import Order, OrderStatus

        payment = await self.repo.get_by_trade_no(trade_no)
        if payment and payment.status in ("success", "failed"):
            logger.info(
                "Callback already processed for trade_no=%s status=%s",
                trade_no,
                payment.status,
            )
            return payment

        if payment is None:
            logger.warning("No payment found for trade_no=%s", trade_no)
            return None

        # Look up the linked order BEFORE mutating, so the defense
        # decision is made against authoritative state.
        order = (
            await self.session.execute(
                select(Order).where(Order.id == payment.order_id)
            )
        ).scalar_one_or_none()
        order_terminal = order is not None and order.status in (
            OrderStatus.expired,
            OrderStatus.cancelled_by_patient,
            OrderStatus.cancelled_by_companion,
            OrderStatus.rejected_by_companion,
        )

        payment.status = "success" if success else "failed"
        await self.session.flush()

        # H2-be: mirror callback outcome onto the order's payment_state.
        await self._set_payment_state(
            payment.order_id,
            PaymentState.paid if success else PaymentState.failed,
        )

        from app.utils.metrics import order_paid_total, payment_callback_received_total
        payment_callback_received_total.labels(status=payment.status).inc()
        if payment.status == "success":
            order_paid_total.labels(service_type="unknown").inc()
            # [TD-MONEY-01 M1 finishing / D-050]
            # 支付成功 → 追加 wallet_ledger（in / pay）。
            # 幂等键：(trade_no, in)；当 trade_no 缺失时 fallback 到 payment.id。
            await self._append_pay_ledger_safe(payment)
        logger.info(
            "Payment callback processed: trade_no=%s status=%s",
            trade_no,
            payment.status,
        )

        # TD-PAY-01: late SUCCESS callback against a terminal order
        # → immediate auto-refund (idempotent; skipped if a refund row
        # already exists thanks to the unique (order_id, payment_type)
        # constraint surfaced as BadRequestException by create_refund).
        if success and order_terminal and payment.status == "success":
            logger.warning(
                "late_callback_after_terminal: order=%s status=%s "
                "trade_no=%s — auto-refunding",
                order.id,
                order.status.value,
                trade_no,
            )
            try:
                await self.create_refund(
                    order_id=order.id,
                    user_id=payment.user_id,
                    original_amount=order.service_price_snapshot or order.price,
                    refund_amount=order.service_price_snapshot or order.price,
                )
            except BadRequestException as e:
                # Already refunded — idempotent ok.
                logger.info(
                    "late_callback_refund_skip order=%s reason=%s",
                    order.id,
                    e.detail,
                )
            except Exception as e:  # pragma: no cover - safety net
                logger.error(
                    "late_callback_refund_error order=%s err=%s",
                    order.id,
                    e,
                    exc_info=True,
                )

        # [ADR-0032 / TD-MONEY-01 M3 / D-044] 增量对账事件：回调落盘后丢进进程
        # 内队列，供 5min sweeper 拉走对账 + autofix。
        # Fire-and-forget：入队失败不能影响主业务 — sweeper 还会走
        # payment_callback_log lookback 兑底。
        try:
            from app.services.reconciliation.incremental import (
                enqueue_incremental_event,
            )
            await enqueue_incremental_event(
                order_id=payment.order_id,
                provider=getattr(payment, "provider", None) or "unknown",
                transaction_id=trade_no,
            )
        except Exception as exc:  # pragma: no cover - defence only
            logger.warning(
                "reconciliation enqueue failed (non-fatal) trade_no=%s err=%s",
                trade_no,
                exc,
            )

        return payment

    # -- close order -----------------------------------------------------------

    async def close_pending_payment(
        self,
        order_id: uuid.UUID,
    ) -> None:
        """
        Close a pending payment at the PSP and mark it CLOSED locally.

        Raises BadRequestException if the PSP rejects the close (e.g. already paid).
        """
        payment = await self.repo.get_by_order_and_type(order_id, "pay")
        if payment is None or payment.status != "pending":
            return  # nothing to close

        try:
            await self.provider.close_order(payment.trade_no or "")
        except Exception as e:
            logger.error(
                "close_order failed for order=%s trade_no=%s: %s",
                order_id,
                payment.trade_no,
                e,
                exc_info=True,
            )
            raise BadRequestException(
                f"无法关闭支付单，可能用户已完成支付: {e}"
            ) from e

        payment.status = "closed"
        await self.session.flush()
        logger.info(
            "Payment closed: order=%s trade_no=%s",
            order_id,
            payment.trade_no,
        )

    # -- refund ---------------------------------------------------------------

    async def create_refund(
        self,
        order_id: uuid.UUID,
        user_id: uuid.UUID,
        original_amount: Decimal | int | float | str,
        refund_amount: Decimal | int | float | str,
    ) -> RefundResult:
        """Create a refund for an order."""

        original_dec = _to_decimal(original_amount).quantize(Decimal("0.01"))
        refund_dec = _to_decimal(refund_amount).quantize(Decimal("0.01"))

        existing_refund = await self.repo.get_by_order_and_type(
            order_id, "refund"
        )
        if existing_refund:
            raise BadRequestException("该订单已退款，请勿重复操作")

        original_pay = await self.repo.get_by_order_and_type(order_id, "pay")
        if not original_pay or original_pay.status != "success":
            raise BadRequestException("原订单未支付成功，无法退款")

        refund_number = f"R{uuid.uuid4().hex[:16].upper()}"
        is_mock = isinstance(self.provider, MockPaymentProvider)

        try:
            result = await self.provider.create_refund(
                trade_no=original_pay.trade_no or "",
                refund_id=refund_number,
                total_yuan=original_dec,
                refund_yuan=refund_dec,
            )
        except BadRequestException:
            # Provider explicitly rejected — propagate to caller as-is so
            # the API surface returns a 400 with the underlying reason.
            raise
        except Exception as e:
            # Provider hard-failure (network, etc.). Surface as 400 so the
            # request is rolled back cleanly; do NOT persist a partial
            # success record. Operators can replay the request once the
            # provider recovers; the unique (order_id, payment_type=refund)
            # constraint still protects against double-refund.
            logger.error(
                "Refund provider call failed for order=%s: %s",
                order_id,
                e,
                exc_info=True,
            )
            raise BadRequestException(f"退款渠道异常: {e}") from e

        refund = Payment(
            order_id=order_id,
            user_id=user_id,
            amount=refund_dec,
            payment_type="refund",
            status="success" if is_mock else "pending",
            trade_no=original_pay.trade_no,
            refund_id=result.get("refund_id", refund_number),
        )
        refund = await self.repo.create(refund)

        # H2-be: refund_state → refunding (mock-success will be flipped
        # to ``refunded`` immediately below).
        _refund_target = (
            RefundState.refunded
            if (is_mock and refund.status == "success")
            else RefundState.refunding
        )
        await self._set_refund_state(
            order_id,
            _refund_target,
        )

        # Mock provider 即时成功 → 同步追加 ledger（生产走 refund callback）
        if is_mock and refund.status == "success":
            await self._append_refund_ledger_safe(refund)

        return RefundResult(
            payment_id=refund.id,
            provider="mock" if is_mock else "wechat",
            refund_id=refund.refund_id,
            mock_success=is_mock,
        )

    async def handle_refund_callback(
        self,
        refund_id: str,
        refund_status: str,
        raw_body: str | None = None,
    ) -> Payment | None:
        """
        Process refund callback from WeChat.

        Must be called AFTER ``record_callback_or_skip`` confirms this is
        a new (non-duplicate) notification.

        Returns the updated Payment, or ``None`` if the refund_id is unknown.
        """
        payment = await self.repo.get_by_refund_id(refund_id)

        if payment is None:
            logger.warning(
                "Refund callback for unknown refund_id=%s — ignoring",
                refund_id,
            )
            return None

        # Already terminal — idempotent success
        if payment.status in ("success", "failed"):
            logger.info(
                "Refund already terminal: refund_id=%s status=%s",
                refund_id,
                payment.status,
            )
            return payment

        if refund_status == "SUCCESS":
            payment.status = "success"
            logger.info(
                "Refund succeeded: refund_id=%s amount=%s",
                refund_id,
                payment.amount,
            )
        else:
            # CHANGE / REFUNDCLOSE / ABNORMAL or any non-SUCCESS
            payment.status = "failed"
            logger.error(
                "Refund FAILED: refund_id=%s wechat_status=%s — "
                "manual intervention may be required",
                refund_id,
                refund_status,
            )

        if raw_body:
            payment.callback_raw = raw_body[:4000]

        await self.session.flush()

        # H2-be: mirror refund outcome on the order's refund_state.
        await self._set_refund_state(
            payment.order_id,
            RefundState.refunded if payment.status == "success" else RefundState.failed,
        )

        # [TD-MONEY-01 M1 finishing / D-050]
        # 退款成功 → 追加 wallet_ledger（out / refund）。
        if payment.status == "success":
            await self._append_refund_ledger_safe(payment)

        return payment

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
