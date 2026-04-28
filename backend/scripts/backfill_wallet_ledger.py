"""[ADR-0032 §3.5 / TD-MONEY-01 M1] wallet_ledger 历史回填脚本。

用法（**只在 maintenance window 手动跑，本 PR 不在线上跑**）：

    python -m scripts.backfill_wallet_ledger --dry-run
    python -m scripts.backfill_wallet_ledger          # 实际写入

策略：
- 从 ``payments`` 表里把 ``status='success'`` 且尚未在 ``wallet_ledger`` 出现的流水
  按 ``(provider_txn_id, direction)`` 唯一键追加进账本
- ``payment_type='pay'``  → direction=in,  reason=pay
- ``payment_type='refund'`` → direction=out, reason=refund
- **``user_id`` 取订单的 ``companion_id``（陪诊师），不是 ``payments.user_id``（payer/患者）**。
  钱包账本以陪诊师为收益主体；订单尚未接单（无 companion）→ 跳过该笔流水（视作
  收入归属未定，等接单后由 cron/对账层自行追加，或在维护窗口手动二次回填）。

幂等：靠 ``(provider_txn_id, direction)`` 唯一索引兜底，重复跑不会写脏数据。
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker  # type: ignore[attr-defined]
from app.models.order import Order
from app.models.payment import Payment
from app.models.wallet_ledger import (
    WalletLedger,
    WalletLedgerDirection,
    WalletLedgerReason,
)


logger = logging.getLogger("backfill_wallet_ledger")


def _direction_for(payment_type: str) -> WalletLedgerDirection:
    return (
        WalletLedgerDirection.in_
        if payment_type == "pay"
        else WalletLedgerDirection.out
    )


def _reason_for(payment_type: str) -> WalletLedgerReason:
    if payment_type == "pay":
        return WalletLedgerReason.pay
    if payment_type == "refund":
        return WalletLedgerReason.refund
    return WalletLedgerReason.adjust


async def backfill(session: AsyncSession, *, dry_run: bool) -> dict[str, int]:
    """主流程。返回 ``{scanned, written, skipped, no_companion}``。"""
    stmt = select(Payment).where(Payment.status == "success")
    rows = (await session.execute(stmt)).scalars().all()
    written = 0
    skipped = 0
    no_companion = 0
    # 缓存 order -> companion_id 避免每行 N+1
    order_cache: dict[uuid.UUID, uuid.UUID | None] = {}
    for p in rows:
        if p.order_id is None:
            no_companion += 1
            continue
        if p.order_id in order_cache:
            companion_user_id = order_cache[p.order_id]
        else:
            order = (
                await session.execute(
                    select(Order).where(Order.id == p.order_id)
                )
            ).scalar_one_or_none()
            companion_user_id = order.companion_id if order else None
            order_cache[p.order_id] = companion_user_id
        if companion_user_id is None:
            no_companion += 1
            continue

        provider_txn_id = p.trade_no or p.refund_id or str(p.id)
        direction = _direction_for(p.payment_type)
        reason = _reason_for(p.payment_type)
        # 唯一键查重
        exists_stmt = select(WalletLedger.id).where(
            WalletLedger.provider_txn_id == provider_txn_id,
            WalletLedger.direction == direction,
        )
        if (await session.execute(exists_stmt)).scalar_one_or_none() is not None:
            skipped += 1
            continue
        if dry_run:
            written += 1
            continue
        try:
            session.add(
                WalletLedger(
                    id=uuid.uuid4(),
                    user_id=companion_user_id,
                    order_id=p.order_id,
                    provider_txn_id=provider_txn_id,
                    amount=p.amount,
                    direction=direction,
                    reason=reason,
                    occurred_at=p.created_at or datetime.now(timezone.utc),
                )
            )
            await session.commit()
            written += 1
        except IntegrityError:
            await session.rollback()
            skipped += 1
    return {
        "scanned": len(rows),
        "written": written,
        "skipped": skipped,
        "no_companion": no_companion,
    }


async def _amain(dry_run: bool) -> None:
    async with async_session_maker() as session:  # type: ignore[misc]
        report = await backfill(session, dry_run=dry_run)
    logger.info("backfill report: %s (dry_run=%s)", report, dry_run)
    print(report)


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill wallet_ledger from payments")
    parser.add_argument("--dry-run", action="store_true", help="print only, no write")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(_amain(dry_run=args.dry_run))


if __name__ == "__main__":  # pragma: no cover
    main()
