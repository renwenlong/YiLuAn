"""
Wallet Ledger Writer
====================

[ADR-0032 §3.5 / TD-MONEY-01 M1 finishing] 钱包账本**写入**入口。

历史背景
--------
M1 阶段（PR #54）落地了 ``wallet_ledger`` 表 + ``WalletService`` 读取路径
+ 一个**离线** ``backfill_wallet_ledger.py`` 脚本。当时设计意图：
后续在支付/退款成功路径接通生产写入。但 M2/M3 直接跳到对账，
**写入路径一直缺失**，导致：

  - 生产环境 wallet_ledger 永远是空表（除非手动跑 backfill）
  - WalletService 永远走 fallback 到旧 OrderRepository 聚合
  - M3 增量对账如果 ledger 为空，会把 **每一笔成功支付都判定为
    MISSING_PAYMENT 差异** → 大量误报 → autofix 队列被冲爆

本模块补齐 3 个生产入口的写入：

  1. **支付成功** — ``record_pay_success`` 由 PaymentService 在 callback
     真正成功时调用（``handle_pay_callback`` + provider mock 即时成功）
  2. **退款成功** — ``record_refund_success`` 由 PaymentService 在
     refund callback 标记成功时调用
  3. **人工调整** — ``record_manual_adjustment`` 由 admin API 调用，
     带强制审计字段（operator + reason）

幂等保证
--------
- 数据库层：``UniqueConstraint(provider_txn_id, direction)`` 兜底，
  写入冲突 → 静默 skip，不当成错误
- 应用层：写入前先 ``SELECT 1`` 探针，避免触发无意义的 IntegrityError
  污染 outer session（FastAPI 依赖持有的事务）
- 所有写入用 ``begin_nested`` SAVEPOINT 包裹，一个 ledger row 异常
  不能影响主业务（支付成功不能因为账本写入失败而回滚）

人工调整规则
------------
- ``adjust`` 类型必须带非空 ``operator`` + ``reason``
- ``provider_txn_id`` 由调用方约定（建议格式
  ``ADJ-{operator}-{uuid}``），落 ``payload`` 的 audit log
- 不接受 amount=0 的"占位"调整（那是 noop，不应该污染账本）
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.wallet_ledger import (
    WalletLedger,
    WalletLedgerDirection,
    WalletLedgerReason,
)

logger = logging.getLogger(__name__)


__all__ = [
    "WalletLedgerWriter",
    "LedgerWriteResult",
]


class LedgerWriteResult:
    """轻量返回类型，避免引入 dataclass 开销。"""

    __slots__ = ("written", "ledger_id", "skipped_reason")

    def __init__(
        self,
        *,
        written: bool,
        ledger_id: Optional[uuid.UUID] = None,
        skipped_reason: Optional[str] = None,
    ):
        self.written = written
        self.ledger_id = ledger_id
        self.skipped_reason = skipped_reason

    def __repr__(self) -> str:  # pragma: no cover - debug only
        if self.written:
            return f"<LedgerWriteResult written id={self.ledger_id}>"
        return f"<LedgerWriteResult skipped reason={self.skipped_reason}>"


class WalletLedgerWriter:
    """
    单一职责：把"已经成功的钱"追加到 ``wallet_ledger``。

    *不*持有事务边界——caller 决定 ``commit`` 时机。本类内部用
    ``begin_nested`` SAVEPOINT 隔离失败，但**不 commit**。
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    async def record_pay_success(
        self,
        *,
        user_id: uuid.UUID,
        order_id: uuid.UUID | None,
        provider_txn_id: str,
        amount: Decimal,
        occurred_at: datetime | None = None,
    ) -> LedgerWriteResult:
        """[支付成功] 入账方向 = ``in``，原因 = ``pay``。"""
        return await self._append(
            user_id=user_id,
            order_id=order_id,
            provider_txn_id=provider_txn_id,
            amount=amount,
            direction=WalletLedgerDirection.in_,
            reason=WalletLedgerReason.pay,
            occurred_at=occurred_at,
        )

    async def record_refund_success(
        self,
        *,
        user_id: uuid.UUID,
        order_id: uuid.UUID | None,
        provider_txn_id: str,
        amount: Decimal,
        occurred_at: datetime | None = None,
    ) -> LedgerWriteResult:
        """[退款成功] 出账方向 = ``out``，原因 = ``refund``。"""
        return await self._append(
            user_id=user_id,
            order_id=order_id,
            provider_txn_id=provider_txn_id,
            amount=amount,
            direction=WalletLedgerDirection.out,
            reason=WalletLedgerReason.refund,
            occurred_at=occurred_at,
        )

    async def record_manual_adjustment(
        self,
        *,
        user_id: uuid.UUID,
        order_id: uuid.UUID | None,
        amount: Decimal,
        direction: WalletLedgerDirection,
        operator: str,
        reason: str,
        provider_txn_id: str | None = None,
        occurred_at: datetime | None = None,
    ) -> LedgerWriteResult:
        """[人工调整] direction 由 caller 指定；强制 operator + reason。

        Parameters
        ----------
        operator : str
            非空 1-64 字符。落 admin_audit_log + ledger.provider_txn_id 后缀。
        reason : str
            非空 1-500 字符（业务理由，比如"客诉补偿 / 财务对账修复"）。
        provider_txn_id : str | None
            可选；若为空，自动生成 ``ADJ-{operator}-{uuid8}``。

        Notes
        -----
        - **不**接受 amount=0
        - 调用方必须**已经**做过权限校验和 admin_audit_log 记录；
          本方法只负责 ledger 落盘
        """
        if amount <= 0:
            raise ValueError("manual adjustment amount must be > 0")
        if not operator or not operator.strip():
            raise ValueError("manual adjustment requires non-empty operator")
        if not reason or not reason.strip():
            raise ValueError("manual adjustment requires non-empty reason")
        if len(operator) > 64:
            raise ValueError("operator must be <= 64 chars")
        if len(reason) > 500:
            raise ValueError("reason must be <= 500 chars")

        if not provider_txn_id:
            provider_txn_id = f"ADJ-{operator.strip()}-{uuid.uuid4().hex[:8]}"

        return await self._append(
            user_id=user_id,
            order_id=order_id,
            provider_txn_id=provider_txn_id,
            amount=amount,
            direction=direction,
            reason=WalletLedgerReason.adjust,
            occurred_at=occurred_at,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _append(
        self,
        *,
        user_id: uuid.UUID,
        order_id: uuid.UUID | None,
        provider_txn_id: str,
        amount: Decimal,
        direction: WalletLedgerDirection,
        reason: WalletLedgerReason,
        occurred_at: datetime | None,
    ) -> LedgerWriteResult:
        """统一追加入口（idempotent + non-fatal）。"""
        if not provider_txn_id:
            return LedgerWriteResult(
                written=False, skipped_reason="empty_provider_txn_id"
            )
        if amount is None:
            return LedgerWriteResult(
                written=False, skipped_reason="null_amount"
            )

        # 量化到 0.01 避免精度漂移
        if not isinstance(amount, Decimal):
            amount = Decimal(str(amount))
        amount_q = amount.quantize(Decimal("0.01"))

        # 应用层探针：避免触发无谓 IntegrityError 污染 outer session
        existing_stmt = select(WalletLedger.id).where(
            WalletLedger.provider_txn_id == provider_txn_id,
            WalletLedger.direction == direction,
        )
        existing = (await self.session.execute(existing_stmt)).scalar_one_or_none()
        if existing is not None:
            logger.debug(
                "wallet_ledger duplicate skip: provider_txn_id=%s direction=%s",
                provider_txn_id,
                direction.value,
            )
            return LedgerWriteResult(
                written=False,
                ledger_id=existing,
                skipped_reason="duplicate",
            )

        row = WalletLedger(
            id=uuid.uuid4(),
            user_id=user_id,
            order_id=order_id,
            provider_txn_id=provider_txn_id,
            amount=amount_q,
            direction=direction,
            reason=reason,
            occurred_at=occurred_at or datetime.now(timezone.utc),
        )
        try:
            async with self.session.begin_nested():
                self.session.add(row)
                await self.session.flush()
        except IntegrityError:
            # 极小概率：探针 → flush 之间另一并发 worker 抢先写入
            logger.info(
                "wallet_ledger race-condition duplicate: provider_txn_id=%s "
                "direction=%s",
                provider_txn_id,
                direction.value,
            )
            return LedgerWriteResult(
                written=False, skipped_reason="race_duplicate"
            )

        logger.info(
            "wallet_ledger appended: id=%s user=%s amount=%s direction=%s "
            "reason=%s txn=%s",
            row.id,
            user_id,
            amount_q,
            direction.value,
            reason.value,
            provider_txn_id,
        )
        return LedgerWriteResult(written=True, ledger_id=row.id)
