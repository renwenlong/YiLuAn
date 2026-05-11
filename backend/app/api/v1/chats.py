from uuid import UUID

from fastapi import APIRouter, Query

from app.api.v1.openapi_meta import err
from app.dependencies import CurrentUser, DBSession
from app.schemas.chat import (
    ChatMessageBackfillResponse,
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


@router.get(
    "/{order_id}/messages/backfill",
    response_model=ChatMessageBackfillResponse,
    summary="WS 重连后增量回灌聊天消息",
    description=(
        "基于游标的增量回灌接口，配合 WebSocket 重连场景使用。\n\n"
        "- ``after_id`` 为客户端本地最后一条消息 ID；缺省时返回最早 ``limit`` 条。\n"
        "- 返回顺序严格 ``(created_at ASC, id ASC)``，与 WS 推送顺序一致。\n"
        "- ``after_id`` 不属于该订单或已被清理时，等价于全量回灌（不报 404）。\n"
        "- ``limit`` 由服务端硬上限 200。"
    ),
    responses={**err(401, 403, 404, 500)},
)
async def backfill_messages(
    order_id: UUID,
    current_user: CurrentUser,
    session: DBSession,
    after_id: UUID | None = Query(
        None, description="上次最后一条消息 ID；为空则从头开始"
    ),
    limit: int = Query(100, ge=1, le=200, description="单次最多返回条数 1~200"),
):
    service = ChatService(session)
    items = await service.list_messages_since(
        order_id, current_user, after_message_id=after_id, limit=limit
    )
    has_more = len(items) >= limit
    next_after_id = items[-1].id if items and has_more else None
    return ChatMessageBackfillResponse(
        items=[ChatMessageResponse.model_validate(m) for m in items],
        next_after_id=next_after_id,
        has_more=has_more,
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
