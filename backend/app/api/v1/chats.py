from uuid import UUID

from fastapi import APIRouter, Query

from app.api.v1.openapi_meta import err
from app.dependencies import CurrentUser, DBSession
from app.schemas.chat import (
    ChatMessageListResponse,
    ChatMessageResponse,
    SendMessageRequest,
)
from app.services.chat import ChatService

router = APIRouter(prefix="/chats", tags=["chats"])


@router.get(
    "/{order_id}/messages",
    response_model=ChatMessageListResponse,
    summary="获取订单聊天历史",
    description=(
        "分页查询指定订单的聊天消息记录。仅订单参与方（患者 / 陪诊师）可访问。\n\n"
        "实时双向通信请使用 `WS /api/v1/ws/chat/{order_id}?token=<jwt>`。"
    ),
    responses={**err(401, 403, 404, 500)},
)
async def list_messages(
    order_id: UUID,
    current_user: CurrentUser,
    session: DBSession,
    page: int = Query(1, ge=1, description="页码（从 1 开始）"),
    page_size: int = Query(50, ge=1, le=100, description="每页条数 1~100"),
):
    service = ChatService(session)
    items, total = await service.list_messages(
        order_id, current_user, page=page, page_size=page_size
    )
    return ChatMessageListResponse(
        items=[ChatMessageResponse.model_validate(m) for m in items],
        total=total,
    )


@router.post(
    "/{order_id}/messages",
    response_model=ChatMessageResponse,
    status_code=201,
    summary="发送一条聊天消息（HTTP 兜底）",
    description=(
        "在指定订单的聊天会话中发送一条消息。"
        "推荐通过 WebSocket 发送以获得实时性，HTTP 接口主要作为离线 / 弱网兜底。"
    ),
    responses={**err(400, 401, 403, 404, 422, 500)},
)
async def send_message(
    order_id: UUID,
    body: SendMessageRequest,
    current_user: CurrentUser,
    session: DBSession,
):
    service = ChatService(session)
    return await service.send_message(order_id, current_user, body)


@router.post(
    "/{order_id}/read",
    summary="批量标记订单消息为已读",
    description="将当前用户在该订单聊天中的全部未读消息标记为已读，返回标记数量。",
    responses={
        200: {
            "description": "标记成功",
            "content": {"application/json": {"example": {"marked_read": 3}}},
        },
        **err(401, 403, 404, 500),
    },
)
async def mark_read(
    order_id: UUID,
    current_user: CurrentUser,
    session: DBSession,
):
    service = ChatService(session)
    count = await service.mark_read(order_id, current_user)
    return {"marked_read": count}
