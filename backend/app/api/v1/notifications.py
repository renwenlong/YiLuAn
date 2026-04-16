from uuid import UUID

from fastapi import APIRouter, Query

from app.dependencies import CurrentUser, DBSession
from app.models.device_token import DeviceToken
from app.repositories.device_token import DeviceTokenRepository
from app.schemas.device_token import (
    DeviceTokenResponse,
    RegisterDeviceRequest,
    UnregisterDeviceRequest,
)
from app.schemas.notification import (
    NotificationListResponse,
    NotificationResponse,
    UnreadCountResponse,
)
from app.services.notification import NotificationService

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=NotificationListResponse, summary="获取通知列表", description="分页查询当前用户的通知消息。")
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


@router.get("/unread-count", response_model=UnreadCountResponse, summary="获取未读通知数", description="返回当前用户的未读通知数量。")
async def unread_count(
    current_user: CurrentUser,
    session: DBSession,
):
    service = NotificationService(session)
    count = await service.count_unread(current_user)
    return UnreadCountResponse(count=count)


@router.post("/{notification_id}/read", summary="标记通知已读", description="将指定通知标记为已读状态。")
async def mark_notification_read(
    notification_id: UUID,
    current_user: CurrentUser,
    session: DBSession,
):
    service = NotificationService(session)
    success = await service.mark_read(notification_id, current_user)
    return {"success": success}


@router.post("/read-all", summary="全部标记已读", description="将当前用户的所有未读通知标记为已读。")
async def mark_all_read(
    current_user: CurrentUser,
    session: DBSession,
):
    service = NotificationService(session)
    count = await service.mark_all_read(current_user)
    return {"marked_read": count}


@router.post("/device-token", response_model=DeviceTokenResponse, summary="注册设备推送令牌", description="注册设备的推送通知令牌，用于接收推送消息。")
async def register_device_token(
    data: RegisterDeviceRequest,
    current_user: CurrentUser,
    session: DBSession,
):
    repo = DeviceTokenRepository(session)
    existing = await repo.get_by_user_and_token(current_user.id, data.token)
    if existing:
        return DeviceTokenResponse.model_validate(existing)

    device = DeviceToken(
        user_id=current_user.id,
        token=data.token,
        device_type=data.device_type,
    )
    device = await repo.create(device)
    return DeviceTokenResponse.model_validate(device)


@router.delete("/device-token", summary="注销设备推送令牌", description="移除设备的推送通知令牌，停止接收推送消息。")
async def unregister_device_token(
    data: UnregisterDeviceRequest,
    current_user: CurrentUser,
    session: DBSession,
):
    repo = DeviceTokenRepository(session)
    await repo.delete_by_token(current_user.id, data.token)
    return {"success": True}
