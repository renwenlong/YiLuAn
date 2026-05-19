"""Admin Audit Logs — read-only listing of admin_audit_logs (C).

Routes: /api/v1/admin/audit-logs
Auth: same double-track admin auth.

Endpoints
---------
GET /
    Paginated, filterable list. Filters: operator, target_type, action,
    created_at range. Default page_size=50, hard-capped at 200.

Read-only on purpose — writes happen inline in the routes that perform
the audited action (force-status, refund, disable, reveal_pii, etc.).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select

from app.core.admin_jwt import require_admin
from app.dependencies import DBSession
from app.models.admin_audit_log import AdminAuditLog

router = APIRouter(
    prefix="/audit-logs",
    tags=["admin-audit-logs"],
    dependencies=[Depends(require_admin)],
)


class AuditLogItem(BaseModel):
    id: UUID
    target_type: str
    target_id: UUID
    action: str
    operator: str
    reason: str | None
    created_at: datetime


class PaginatedAuditLogs(BaseModel):
    items: list[AuditLogItem]
    total: int
    page: int
    page_size: int


@router.get(
    "",
    response_model=PaginatedAuditLogs,
    summary="后台：审计日志列表",
    description="按操作员 / 目标类型 / 目标 id / 动作 / 时间窗口过滤后台审计日志，分页返回。",
)
async def list_audit_logs(
    session: DBSession,
    operator: str | None = Query(None, description="按操作员精确匹配"),
    target_type: str | None = Query(None, description="按目标类型，如 order/user/companion"),
    target_id: UUID | None = Query(None, description="按具体目标 id 精确匹配"),
    action: str | None = Query(None, description="按动作类型精确匹配"),
    since: datetime | None = Query(None, description="created_at >= since"),
    until: datetime | None = Query(None, description="created_at < until"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> PaginatedAuditLogs:
    stmt = select(AdminAuditLog)
    count_stmt = select(func.count(AdminAuditLog.id))

    conditions = []
    if operator:
        conditions.append(AdminAuditLog.operator == operator)
    if target_type:
        conditions.append(AdminAuditLog.target_type == target_type)
    if target_id:
        conditions.append(AdminAuditLog.target_id == target_id)
    if action:
        conditions.append(AdminAuditLog.action == action)
    if since:
        conditions.append(AdminAuditLog.created_at >= since)
    if until:
        conditions.append(AdminAuditLog.created_at < until)

    for c in conditions:
        stmt = stmt.where(c)
        count_stmt = count_stmt.where(c)

    total = (await session.execute(count_stmt)).scalar_one()

    rows = (
        await session.execute(
            stmt.order_by(AdminAuditLog.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()

    return PaginatedAuditLogs(
        items=[
            AuditLogItem(
                id=r.id,
                target_type=r.target_type,
                target_id=r.target_id,
                action=r.action,
                operator=r.operator,
                reason=r.reason,
                created_at=r.created_at,
            )
            for r in rows
        ],
        total=int(total),
        page=page,
        page_size=page_size,
    )
