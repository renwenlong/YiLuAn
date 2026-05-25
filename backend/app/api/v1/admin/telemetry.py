"""Admin telemetry — read-only list of telemetry events.

Routes: /api/v1/admin/telemetry/events
Auth:   require_admin (JWT or legacy X-Admin-Token)

Filters: event_type (exact), since/until (created_at range), user_id.
Default page_size=50, hard-capped at 200.
"""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.core.admin_jwt import require_admin
from app.dependencies import DBSession
from app.models.telemetry_event import TelemetryEvent
from app.schemas.telemetry import TelemetryEventListResponse, TelemetryEventRead

router = APIRouter(
    prefix="/telemetry",
    tags=["admin-telemetry"],
    dependencies=[Depends(require_admin)],
)


@router.get(
    "/events",
    response_model=TelemetryEventListResponse,
    summary="埋点事件列表（admin）",
    description=(
        "分页查询 `telemetry_events`。支持按 event_type 精确匹配、时间区间、"
        "user_id 过滤。默认按 created_at 倒序。"
    ),
)
async def list_events(
    session: DBSession,
    event_type: str | None = Query(None, description="精确匹配 event_type"),
    user_id: UUID | None = Query(None, description="按上报用户过滤"),
    since: datetime | None = Query(None, description="created_at >= since"),
    until: datetime | None = Query(None, description="created_at < until"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> TelemetryEventListResponse:
    base = select(TelemetryEvent)
    count_stmt = select(func.count()).select_from(TelemetryEvent)

    if event_type is not None:
        base = base.where(TelemetryEvent.event_type == event_type)
        count_stmt = count_stmt.where(TelemetryEvent.event_type == event_type)
    if user_id is not None:
        base = base.where(TelemetryEvent.user_id == user_id)
        count_stmt = count_stmt.where(TelemetryEvent.user_id == user_id)
    if since is not None:
        base = base.where(TelemetryEvent.created_at >= since)
        count_stmt = count_stmt.where(TelemetryEvent.created_at >= since)
    if until is not None:
        base = base.where(TelemetryEvent.created_at < until)
        count_stmt = count_stmt.where(TelemetryEvent.created_at < until)

    stmt = (
        base.order_by(TelemetryEvent.created_at.desc(), TelemetryEvent.id.desc())
        .limit(limit)
        .offset(offset)
    )

    rows = (await session.execute(stmt)).scalars().all()
    total = (await session.execute(count_stmt)).scalar_one()
    items = [TelemetryEventRead.model_validate(r) for r in rows]
    return TelemetryEventListResponse(
        items=items, total=int(total), limit=limit, offset=offset
    )
