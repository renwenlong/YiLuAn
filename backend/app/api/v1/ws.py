import json
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.security import decode_token
from app.database import async_session
from app.models.chat_message import ChatMessage, MessageType
from app.repositories.chat_message import ChatMessageRepository
from app.repositories.order import OrderRepository
from app.repositories.user import UserRepository
from app.ws.pubsub import WsPubSubBroker, get_ws_broker_from_app

router = APIRouter()

# Chat room connections remain in-process（每房间都是 order 维度，无跨副本需求：
# 聊天 WS 通过订单 id 路由，后续如果要多副本也可以复用 broker 的模式，这里先保持
# 现状以缩小 D-019 改动面）。
_connections: dict[str, list[WebSocket]] = {}


# ---------------------------------------------------------------------------
# Fallback broker：启动失败或未开启时使用（单机内存模式），确保业务总是有 broker 可用
# ---------------------------------------------------------------------------
_fallback_broker: WsPubSubBroker | None = None


def _get_or_create_broker(app) -> WsPubSubBroker:
    broker = get_ws_broker_from_app(app)
    if broker is not None:
        return broker
    # lifespan 未启动（例如测试场景通过 ASGITransport 不走 startup）→ 退化为进程内 broker
    global _fallback_broker
    if _fallback_broker is None:
        _fallback_broker = WsPubSubBroker(redis_client=None, enabled=False)
        # 无 Redis，start() 立即进入单机模式；为避免 await，这里不 start，直接标记
        _fallback_broker._started = True  # type: ignore[attr-defined]
    return _fallback_broker


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
    await broker.register(user_id, websocket)

    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)
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

    room_key = str(order_id)
    if room_key not in _connections:
        _connections[room_key] = []
    _connections[room_key].append(websocket)

    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)

            # Handle heartbeat
            if data.get("type") == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
                continue

            content = data.get("content", "").strip()
            if not content:
                continue

            msg_type = MessageType(data.get("type", "text"))

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

                broadcast_data = json.dumps({
                    "id": str(message.id),
                    "order_id": str(order_id),
                    "sender_id": str(user_id),
                    "type": msg_type.value,
                    "content": content,
                    "is_read": False,
                    "created_at": message.created_at.isoformat(),
                })

            # Broadcast to all connections in the room
            for ws in _connections.get(room_key, []):
                try:
                    await ws.send_text(broadcast_data)
                except Exception:
                    pass

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        if room_key in _connections:
            _connections[room_key] = [
                ws for ws in _connections[room_key] if ws != websocket
            ]
            if not _connections[room_key]:
                del _connections[room_key]
