from uuid import UUID

from fastapi import APIRouter, Query

from app.dependencies import CurrentUser, DBSession
from app.schemas.chat import (
    ChatMessageListResponse,
    ChatMessageResponse,
    SendMessageRequest,
)
from app.services.chat import ChatService

router = APIRouter(prefix="/chats", tags=["chats"])


@router.get("/{order_id}/messages", response_model=ChatMessageListResponse, summary="获取聊天消息列表", description="分页查询指定订单的聊天消息记录。")
async def list_messages(
    order_id: UUID,
    current_user: CurrentUser,
    session: DBSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
):
    service = ChatService(session)
    items, total = await service.list_messages(
        order_id, current_user, page=page, page_size=page_size
    )
    return ChatMessageListResponse(
        items=[ChatMessageResponse.model_validate(m) for m in items],
        total=total,
    )


@router.post("/{order_id}/messages", response_model=ChatMessageResponse, status_code=201, summary="发送聊天消息", description="在指定订单的聊天中发送一条新消息。")
async def send_message(
    order_id: UUID,
    body: SendMessageRequest,
    current_user: CurrentUser,
    session: DBSession,
):
    service = ChatService(session)
    return await service.send_message(order_id, current_user, body)


@router.post("/{order_id}/read", summary="标记消息已读", description="将指定订单聊天中的未读消息全部标记为已读。")
async def mark_read(
    order_id: UUID,
    current_user: CurrentUser,
    session: DBSession,
):
    service = ChatService(session)
    count = await service.mark_read(order_id, current_user)
    return {"marked_read": count}
