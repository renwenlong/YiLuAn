"""
Admin Wallet Ledger endpoints — D-050 manual adjustment (TD-MONEY-01 M1 finishing).

Why a separate router?
----------------------
``wallet_ledger`` is the single source of truth for companion balance after
M3. We need a curated, auditable way for ops to push corrections into it
when a real-world incident requires it (refund the user can't get from
provider, supplemental payout, demo reset, etc.).

Endpoints
---------
- ``POST /api/v1/admin/wallet-ledger/adjustments`` — append one ledger row
  with ``reason=adjust``. Requires ``X-Admin-Token`` + ``X-Admin-Operator``;
  body ``{user_id, direction, amount, reason, order_id?}``. Writes
  ``admin_audit_logs`` row before and after the ledger append.
- ``GET  /api/v1/admin/wallet-ledger/{user_id}`` — list a user's ledger
  entries (newest first, paged). Read-only diagnostics.

Constraints
-----------
- Adjustments cannot be reversed by the same endpoint — to undo, post
  a new adjustment in the opposite direction (so audit chain stays linear).
- ``amount > 0`` strictly; signed direction encoded by ``direction`` field.
- ``reason`` is required free-text 1-500 chars (e.g. "客诉补偿 ORDER-1234").
"""

from __future__ import annotations

import uuid
from decimal import Decimal, InvalidOperation
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.admin_auth import require_admin_operator, require_admin_token
from app.database import get_db
from app.exceptions import BadRequestException
from app.models.admin_audit_log import AdminAuditLog
from app.models.wallet_ledger import (
    WalletLedger,
    WalletLedgerDirection,
    WalletLedgerReason,
)
from app.services.wallet_ledger_writer import WalletLedgerWriter

router = APIRouter(prefix="/wallet-ledger", tags=["admin-wallet-ledger"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ManualAdjustmentRequest(BaseModel):
    user_id: uuid.UUID
    direction: Literal["in", "out"] = Field(
        description="in = 入账（给用户加钱）, out = 出账（扣用户的钱）"
    )
    amount: str = Field(
        description="金额，字符串形式避免浮点漂移；> 0 严格"
    )
    reason: str = Field(min_length=1, max_length=500)
    order_id: uuid.UUID | None = None
    # provider_txn_id 由 server 自动生成 (ADJ-{operator}-{uuid8})


class LedgerRowResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    order_id: uuid.UUID | None
    provider_txn_id: str
    amount: str
    direction: str
    reason: str
    occurred_at: str
    created_at: str

    @classmethod
    def from_row(cls, row: WalletLedger) -> "LedgerRowResponse":
        return cls(
            id=row.id,
            user_id=row.user_id,
            order_id=row.order_id,
            provider_txn_id=row.provider_txn_id,
            amount=str(row.amount),
            direction=row.direction.value,
            reason=row.reason.value,
            occurred_at=row.occurred_at.isoformat(),
            created_at=row.created_at.isoformat(),
        )


class AdjustmentResponse(BaseModel):
    ledger_id: uuid.UUID
    operator: str
    direction: str
    amount: str
    provider_txn_id: str


class LedgerListResponse(BaseModel):
    items: list[LedgerRowResponse]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/adjustments",
    response_model=AdjustmentResponse,
    dependencies=[Depends(require_admin_token)],
)
async def create_manual_adjustment(
    body: ManualAdjustmentRequest,
    operator: str = Depends(require_admin_operator),
    session: AsyncSession = Depends(get_db),
) -> AdjustmentResponse:
    """
    人工记一笔调账。强制 ``X-Admin-Operator``；落 admin_audit_log + ledger。
    """
    try:
        amount = Decimal(body.amount)
    except (InvalidOperation, ValueError) as exc:
        raise BadRequestException(f"invalid amount: {body.amount}") from exc

    if amount <= 0:
        raise BadRequestException("amount must be > 0")

    direction = (
        WalletLedgerDirection.in_
        if body.direction == "in"
        else WalletLedgerDirection.out
    )

    writer = WalletLedgerWriter(session)
    try:
        result = await writer.record_manual_adjustment(
            user_id=body.user_id,
            order_id=body.order_id,
            amount=amount,
            direction=direction,
            operator=operator,
            reason=body.reason,
        )
    except ValueError as exc:
        raise BadRequestException(str(exc)) from exc

    if not result.written:
        # extremely rare (random uuid8 collision) — surface so ops can retry
        raise BadRequestException(
            f"ledger append skipped: {result.skipped_reason}"
        )

    # Audit log — has to be its own row, *after* ledger write succeeded
    import json
    session.add(
        AdminAuditLog(
            operator=operator,
            action="wallet_ledger_manual_adjust",
            target_type="wallet_ledger",
            target_id=result.ledger_id,
            reason=json.dumps(
                {
                    "user_id": str(body.user_id),
                    "order_id": str(body.order_id) if body.order_id else None,
                    "direction": direction.value,
                    "amount": str(amount),
                    "reason": body.reason,
                },
                ensure_ascii=False,
            ),
        )
    )
    await session.commit()

    # Re-fetch to return the canonical provider_txn_id
    row = (
        await session.execute(
            select(WalletLedger).where(WalletLedger.id == result.ledger_id)
        )
    ).scalar_one()
    return AdjustmentResponse(
        ledger_id=row.id,
        operator=operator,
        direction=row.direction.value,
        amount=str(row.amount),
        provider_txn_id=row.provider_txn_id,
    )


@router.get(
    "/{user_id}",
    response_model=LedgerListResponse,
    dependencies=[Depends(require_admin_token)],
)
async def list_user_ledger(
    user_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    reason: Literal["pay", "refund", "adjust"] | None = Query(None),
    session: AsyncSession = Depends(get_db),
) -> LedgerListResponse:
    """诊断用：查看某 user 的账本流水。"""
    base = select(WalletLedger).where(WalletLedger.user_id == user_id)
    count_q = select(func.count()).select_from(WalletLedger).where(
        WalletLedger.user_id == user_id
    )
    if reason:
        reason_enum = WalletLedgerReason(reason)
        base = base.where(WalletLedger.reason == reason_enum)
        count_q = count_q.where(WalletLedger.reason == reason_enum)

    total = (await session.execute(count_q)).scalar_one()
    offset = (page - 1) * page_size
    rows = (
        await session.execute(
            base.order_by(desc(WalletLedger.occurred_at))
            .offset(offset)
            .limit(page_size)
        )
    ).scalars().all()

    return LedgerListResponse(
        items=[LedgerRowResponse.from_row(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )
