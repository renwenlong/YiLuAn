import json
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.security import decode_token
from app.database import async_session
from app.models.chat_message import ChatMessage, MessageType
from app.repositories.chat_message import ChatMessageRepository
from app.repositories.order import OrderRepository
from app.repositories.user import UserRepository

router = APIRouter()

# Simple in-memory connection manager (single-instance; use Redis pub/sub for multi-instance)
_connections: dict[str, list[WebSocket]] = {}

# Global notification connections: user_id -> list[WebSocket]
_notification_connections: dict[str, list[WebSocket]] = {}


async def push_notification_to_user(user_id: UUID, notification_data: dict) -> None:
    """Push a notification to a connected user via WebSocket."""
    key = str(user_id)
    for ws in _notification_connections.get(key, []):
        try:
            await ws.send_text(json.dumps(notification_data))
        except Exception:
            pass


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

    key = str(user_id)
    if key not in _notification_connections:
        _notification_connections[key] = []
    _notification_connections[key].append(websocket)

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
        if key in _notification_connections:
            _notification_connections[key] = [
                ws for ws in _notification_connections[key] if ws != websocket
            ]
            if not _notification_connections[key]:
                del _notification_connections[key]


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
