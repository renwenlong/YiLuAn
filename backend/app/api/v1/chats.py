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


@router.get("/{order_id}/messages", response_model=ChatMessageListResponse)
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


@router.post("/{order_id}/messages", response_model=ChatMessageResponse, status_code=201)
async def send_message(
    order_id: UUID,
    body: SendMessageRequest,
    current_user: CurrentUser,
    session: DBSession,
):
    service = ChatService(session)
    return await service.send_message(order_id, current_user, body)


@router.post("/{order_id}/read")
async def mark_read(
    order_id: UUID,
    current_user: CurrentUser,
    session: DBSession,
):
    service = ChatService(session)
    count = await service.mark_read(order_id, current_user)
    return {"marked_read": count}
