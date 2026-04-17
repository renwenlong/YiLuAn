import json
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import settings
from app.core.security import decode_token
from app.database import async_session
from app.models.chat_message import ChatMessage, MessageType
from app.repositories.chat_message import ChatMessageRepository
from app.repositories.order import OrderRepository
from app.repositories.user import UserRepository
from app.ws.pubsub import (
    WsPubSubBroker,
    get_ws_broker_from_app,
    get_ws_chat_broker_from_app,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Fallback broker：启动失败或未开启时使用（单机内存模式），确保业务总是有 broker 可用
# ---------------------------------------------------------------------------
# 通知广播 fallback（user_id 维度）
_fallback_broker: WsPubSubBroker | None = None
# 聊天房间 fallback（order_id 维度）
_fallback_chat_broker: WsPubSubBroker | None = None


def _get_or_create_broker(app) -> WsPubSubBroker:
    broker = get_ws_broker_from_app(app)
    if broker is not None:
        return broker
    # lifespan 未启动（例如测试场景通过 ASGITransport 不走 startup）→ 退化为进程内 broker
    global _fallback_broker
    if _fallback_broker is None:
        _fallback_broker = WsPubSubBroker(
            redis_client=None, enabled=False, key_field="user_id"
        )
        # 无 Redis，start() 立即进入单机模式；为避免 await，这里不 start，直接标记
        _fallback_broker._started = True  # type: ignore[attr-defined]
    return _fallback_broker


def _get_or_create_chat_broker(app) -> WsPubSubBroker:
    broker = get_ws_chat_broker_from_app(app)
    if broker is not None:
        return broker
    global _fallback_chat_broker
    if _fallback_chat_broker is None:
        _fallback_chat_broker = WsPubSubBroker(
            redis_client=None, enabled=False, key_field="order_id"
        )
        _fallback_chat_broker._started = True  # type: ignore[attr-defined]
    return _fallback_chat_broker


async def push_notification_to_user(app, user_id: UUID, notification_data: dict) -> None:
    """Push a notification to a connected user via WebSocket broker.

    Kept as a module-level helper so NotificationService 可以用统一入口；
    broker 内部处理本地投递 + Redis Pub/Sub 跨副本 fanout。
    """
    broker = _get_or_create_broker(app)
    await broker.push_to_user(user_id, notification_data)


@router.websocket("/ws/notifications")
async def websocket_notifications(websocket: WebSocket):
    """Global notification WebSocket. Connect with ?token=<jwt>."""
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4001, reason="Missing token")
        return

    payload = decode_token(token)
    if payload is None or payload.get("type") != "access":
        await websocket.close(code=4001, reason="Invalid token")
        return

    user_id_str = payload.get("sub")
    if not user_id_str:
        await websocket.close(code=4001, reason="Invalid token")
        return

    try:
        user_id = UUID(user_id_str)
    except ValueError:
        await websocket.close(code=4001, reason="Invalid token")
        return

    await websocket.accept()

    broker = _get_or_create_broker(websocket.app)
    # D-020：同用户并发连接数上限 → 超限踢最老。Pub/Sub 架构下本地表限制即可，
    # 其他副本的连接独立计数（多副本场景用户实际上限 ≈ N × replicas，可接受）。
    cap = settings.ws_max_connections_per_user
    if cap and cap > 0:
        evicted = await broker.register_with_cap(user_id, websocket, cap)
        for old_ws in evicted:
            try:
                await old_ws.close(code=4008, reason="Replaced by newer connection")
            except Exception:
                pass
    else:
        await broker.register(user_id, websocket)

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except (TypeError, ValueError):
                # 非法 JSON 直接忽略，避免单条脏消息把连接打掉
                continue
            if data.get("type") == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await broker.unregister(user_id, websocket)


@router.websocket("/ws/chat/{order_id}")
async def websocket_chat(websocket: WebSocket, order_id: UUID):
    """Order-scoped chat WebSocket. 按订单分房间；Redis Pub/Sub fanout 到多副本。"""
    # Authenticate via query param
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4001, reason="Missing token")
        return

    payload = decode_token(token)
    if payload is None or payload.get("type") != "access":
        await websocket.close(code=4001, reason="Invalid token")
        return

    user_id_str = payload.get("sub")
    if not user_id_str:
        await websocket.close(code=4001, reason="Invalid token")
        return

    try:
        user_id = UUID(user_id_str)
    except ValueError:
        await websocket.close(code=4001, reason="Invalid token")
        return

    # Validate user is participant of the order
    async with async_session() as session:
        order_repo = OrderRepository(session)
        order = await order_repo.get_by_id(order_id)
        if order is None:
            await websocket.close(code=4004, reason="Order not found")
            return
        if order.patient_id != user_id and order.companion_id != user_id:
            await websocket.close(code=4003, reason="Not a participant")
            return

        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        if user is None:
            await websocket.close(code=4001, reason="User not found")
            return

    await websocket.accept()

    chat_broker = _get_or_create_chat_broker(websocket.app)
    await chat_broker.register(order_id, websocket)

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except (TypeError, ValueError):
                # 非法 JSON：忽略一条，不断连接
                continue

            # Handle heartbeat
            if data.get("type") == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
                continue

            content = (data.get("content") or "").strip()
            if not content:
                continue

            # 消息体长度上限：防止大 payload 压垮连接 / DB
            if len(content) > 4000:
                content = content[:4000]

            try:
                msg_type = MessageType(data.get("type", "text"))
            except ValueError:
                msg_type = MessageType.text

            # Persist message
            async with async_session() as session:
                chat_repo = ChatMessageRepository(session)
                message = ChatMessage(
                    order_id=order_id,
                    sender_id=user_id,
                    type=msg_type,
                    content=content,
                )
                message = await chat_repo.create(message)
                await session.commit()

                broadcast_payload = {
                    "id": str(message.id),
                    "order_id": str(order_id),
                    "sender_id": str(user_id),
                    "type": msg_type.value,
                    "content": content,
                    "is_read": False,
                    "created_at": message.created_at.isoformat(),
                }

            # Broadcast via pubsub broker：本地 + Redis fanout 到其他副本
            await chat_broker.publish_to_room(order_id, broadcast_payload)

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await chat_broker.unregister(order_id, websocket)
