"""Admin DeadLetter — ops worklist for failed side-effects (W19).

Routes: ``/api/v1/admin/dead-letters``
Auth:   X-Admin-Token (via ``require_admin``)

Endpoints
---------
GET    /                   list dead-letter rows, filters: status / channel
GET    /{id}               row detail
POST   /{id}/resolve       body {note} \u2014 mark resolved, stamp operator

Background
----------
The cancel / force-cancel / refund pipelines record a ``DeadLetter`` when
a best-effort side-effect (e.g. provider refund call, push notification)
fails *after* the primary state transition has succeeded. Operators use
this queue to compensate manually; a future replay cron can also consume
it.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.core.admin_jwt import admin_operator_id, require_admin
from app.dependencies import DBSession
from app.exceptions import BadRequestException, NotFoundException
from app.models.admin_audit_log import AdminAuditLog
from app.models.dead_letter import DeadLetter, DeadLetterStatus


router = APIRouter(
    prefix="/dead-letters",
    tags=["admin-dead-letters"],
    dependencies=[Depends(require_admin)],
)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class DeadLetterItem(BaseModel):
    id: str = Field(..., description="DeadLetter UUID")
    channel: str = Field(..., description="\u9891\u9053\uff0c\u4f8b\uff1aorder_refund / notification")
    reason: str = Field(..., description="\u673a\u5668\u5212\u5206\u7684\u539f\u56e0 key")
    target_type: str | None = Field(None, description="\u76ee\u6807\u5b9e\u4f53\u7c7b\u578b\uff0c\u4f8b\uff1aorder")
    target_id: str | None = Field(None, description="\u76ee\u6807\u5b9e\u4f53 UUID")
    payload: dict[str, Any] | None = Field(None, description="\u5907\u4efd\u4e0a\u4e0b\u6587\uff08JSON\uff09")
    status: str = Field(..., description="pending / resolved")
    resolved_by: str | None = Field(None, description="\u89e3\u51b3\u4eba\uff08operator\uff09")
    resolution_note: str | None = Field(None, description="\u89e3\u51b3\u8bf4\u660e")
    created_at: str = Field(..., description="\u521b\u5efa\u65f6\u95f4 ISO8601")
    resolved_at: str | None = Field(None, description="\u89e3\u51b3\u65f6\u95f4 ISO8601")


class PaginatedDeadLetters(BaseModel):
    items: list[DeadLetterItem]
    total: int
    page: int
    page_size: int


class ResolveBody(BaseModel):
    note: str = Field(..., min_length=1, max_length=500, description="\u89e3\u51b3\u8bf4\u660e")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_item(row: DeadLetter) -> dict[str, Any]:
    status_val = (
        row.status.value if hasattr(row.status, "value") else str(row.status)
    )
    return {
        "id": str(row.id),
        "channel": row.channel,
        "reason": row.reason,
        "target_type": row.target_type,
        "target_id": str(row.target_id) if row.target_id else None,
        "payload": row.payload,
        "status": status_val,
        "resolved_by": row.resolved_by,
        "resolution_note": row.resolution_note,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=PaginatedDeadLetters,
    summary="\u540e\u53f0\uff1a\u6b7b\u4fe1\u961f\u5217\u8868",
    description="\u67e5\u8be2\u9700\u4eba\u5de5\u8865\u507f\u7684\u9057\u7559\u4efb\u52a1\uff0c\u9ed8\u8ba4\u6309\u65f6\u95f4\u5012\u5e8f\u3002",
)
async def list_dead_letters(
    session: DBSession,
    operator: str = Depends(admin_operator_id),  # noqa: ARG001 \u2014 audit-future hook
    status: str | None = Query(None, description="pending / resolved"),
    channel: str | None = Query(None, description="\u4f8b\uff1aorder_refund"),
    target_id: UUID | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    if status is not None:
        try:
            status_enum = DeadLetterStatus(status)
        except ValueError as exc:
            raise BadRequestException(f"Invalid status: {status}") from exc
    else:
        status_enum = None

    stmt = select(DeadLetter)
    count_stmt = select(func.count()).select_from(DeadLetter)
    if status_enum is not None:
        stmt = stmt.where(DeadLetter.status == status_enum)
        count_stmt = count_stmt.where(DeadLetter.status == status_enum)
    if channel:
        stmt = stmt.where(DeadLetter.channel == channel)
        count_stmt = count_stmt.where(DeadLetter.channel == channel)
    if target_id is not None:
        stmt = stmt.where(DeadLetter.target_id == target_id)
        count_stmt = count_stmt.where(DeadLetter.target_id == target_id)

    skip = (page - 1) * page_size
    stmt = stmt.order_by(DeadLetter.created_at.desc()).offset(skip).limit(page_size)

    rows = (await session.execute(stmt)).scalars().all()
    total = (await session.execute(count_stmt)).scalar_one()

    return {
        "items": [_to_item(r) for r in rows],
        "total": int(total),
        "page": page,
        "page_size": page_size,
    }


@router.get(
    "/{dl_id}",
    response_model=DeadLetterItem,
    summary="\u540e\u53f0\uff1a\u6b7b\u4fe1\u8be6\u60c5",
    description="\u8fd4\u56de\u6307\u5b9a dead_letter \u884c\u7684\u5168\u90e8\u5b57\u6bb5\uff08\u542b payload \u4e0e\u89e3\u51b3\u6001\uff09\u3002",
)
async def get_dead_letter(
    dl_id: UUID,
    session: DBSession,
    operator: str = Depends(admin_operator_id),  # noqa: ARG001
):
    row = await session.get(DeadLetter, dl_id)
    if row is None:
        raise NotFoundException("DeadLetter not found")
    return _to_item(row)


@router.post(
    "/{dl_id}/resolve",
    response_model=DeadLetterItem,
    summary="\u540e\u53f0\uff1a\u6807\u8bb0\u6b7b\u4fe1\u5df2\u89e3\u51b3",
    description="\u8bb0\u5f55\u89e3\u51b3\u4eba\u3001\u8bf4\u660e\u3001\u65f6\u95f4\uff1b\u540c\u65f6\u5199\u5165 admin_audit_logs\u3002",
)
async def resolve_dead_letter(
    dl_id: UUID,
    body: ResolveBody,
    session: DBSession,
    operator: str = Depends(admin_operator_id),
):
    row = await session.get(DeadLetter, dl_id)
    if row is None:
        raise NotFoundException("DeadLetter not found")
    if row.status == DeadLetterStatus.resolved:
        raise BadRequestException("DeadLetter already resolved")

    row.status = DeadLetterStatus.resolved
    row.resolved_by = operator
    row.resolution_note = body.note
    row.resolved_at = datetime.now(timezone.utc)

    session.add(
        AdminAuditLog(
            target_type="dead_letter",
            target_id=dl_id,
            action="dead_letter_resolve",
            operator=operator,
            reason=body.note,
        )
    )
    await session.flush()
    return _to_item(row)
