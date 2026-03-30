from uuid import UUID

from fastapi import APIRouter, Query

from app.dependencies import CurrentUser, DBSession
from app.schemas.notification import (
    NotificationListResponse,
    NotificationResponse,
    UnreadCountResponse,
)
from app.services.notification import NotificationService

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    current_user: CurrentUser,
    session: DBSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    service = NotificationService(session)
    items, total = await service.list_notifications(
        current_user, page=page, page_size=page_size
    )
    return NotificationListResponse(
        items=[NotificationResponse.model_validate(n) for n in items],
        total=total,
    )


@router.get("/unread-count", response_model=UnreadCountResponse)
async def unread_count(
    current_user: CurrentUser,
    session: DBSession,
):
    service = NotificationService(session)
    count = await service.count_unread(current_user)
    return UnreadCountResponse(count=count)


@router.post("/{notification_id}/read")
async def mark_notification_read(
    notification_id: UUID,
    current_user: CurrentUser,
    session: DBSession,
):
    service = NotificationService(session)
    success = await service.mark_read(notification_id, current_user)
    return {"success": success}


@router.post("/read-all")
async def mark_all_read(
    current_user: CurrentUser,
    session: DBSession,
):
    service = NotificationService(session)
    count = await service.mark_all_read(current_user)
    return {"marked_read": count}
