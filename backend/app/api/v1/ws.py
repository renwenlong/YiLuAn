"""WebSocket endpoints (C-12 / TD-MSG-04 重构后).

所有写路径统一走 `ChatService`，handler 只负责：
1. JWT 鉴权 + 参与方校验
2. asyncio idle timeout（默认 90s，超时主动关闭并打 metric）
3. nonce 透传到 ChatService（TD-MSG-01 客户端幂等）
4. broker fanout（本地 + Redis Pub/Sub）

不破坏现有 frame 契约：
- 上行：`{type: "ping"}` → 下行 `{type: "pong"}`
- 上行：`{type: "text"|"image"|"system", content: "...", nonce?: "..."}`
- 下行（broadcast）：`{id, order_id, sender_id, type, content, is_read,
   created_at, nonce?}`
"""
import asyncio
import json
import logging
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import settings
from app.core.security import decode_token
from app.database import async_session
from app.models.chat_message import MessageType
from app.repositories.user import UserRepository
from app.services.chat import ChatService
from app.utils.metrics import ws_idle_timeout_total
from app.ws.pubsub import (
    WsPubSubBroker,
    get_ws_broker_from_app,
    get_ws_chat_broker_from_app,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Server-side idle timeout for WS connections (TD-MSG-04).
# Client sends PING every 30s; we tolerate ~3 misses.
WS_IDLE_TIMEOUT_SECONDS = 90


# ---------------------------------------------------------------------------
# Fallback broker：启动失败或未开启时使用（单机内存模式）
# ---------------------------------------------------------------------------
_fallback_broker: WsPubSubBroker | None = None
_fallback_chat_broker: WsPubSubBroker | None = None


def _get_or_create_broker(app) -> WsPubSubBroker:
    broker = get_ws_broker_from_app(app)
    if broker is not None:
        return broker
    global _fallback_broker
    if _fallback_broker is None:
        _fallback_broker = WsPubSubBroker(
            redis_client=None, enabled=False, key_field="user_id"
        )
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
    """Push a notification to a connected user via WebSocket broker."""
    broker = _get_or_create_broker(app)
    await broker.push_to_user(user_id, notification_data)


def _decode_user(websocket: WebSocket) -> UUID | None:
    """Return user_id parsed from ?token=, or None on invalid."""
    token = websocket.query_params.get("token")
    if not token:
        return None
    payload = decode_token(token)
    if payload is None or payload.get("type") != "access":
        return None
    sub = payload.get("sub")
    if not sub:
        return None
    try:
        return UUID(sub)
    except (TypeError, ValueError):
        return None


@router.websocket("/ws/notifications")
async def websocket_notifications(websocket: WebSocket):
    """Global notification WebSocket. Connect with ?token=<jwt>."""
    user_id = _decode_user(websocket)
    if user_id is None:
        await websocket.close(code=4001, reason="Invalid token")
        return

    await websocket.accept()

    broker = _get_or_create_broker(websocket.app)
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
            try:
                raw = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=WS_IDLE_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                ws_idle_timeout_total.labels(channel="notifications").inc()
                logger.info(
                    "ws.idle_timeout",
                    extra={"channel": "notifications", "user_id": str(user_id)},
                )
                try:
                    await websocket.close(code=4002, reason="idle_timeout")
                except Exception:
                    pass
                break

            try:
                data = json.loads(raw)
            except (TypeError, ValueError):
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
    """Order-scoped chat WebSocket. 全部走 ChatService。"""
    user_id = _decode_user(websocket)
    if user_id is None:
        await websocket.close(code=4001, reason="Invalid token")
        return

    # Pre-flight authorisation: order exists + user is participant.
    async with async_session() as session:
        from app.repositories.order import OrderRepository

        order = await OrderRepository(session).get_by_id(order_id)
        if order is None:
            await websocket.close(code=4004, reason="Order not found")
            return
        if order.patient_id != user_id and order.companion_id != user_id:
            await websocket.close(code=4003, reason="Not a participant")
            return
        user = await UserRepository(session).get_by_id(user_id)
        if user is None:
            await websocket.close(code=4001, reason="User not found")
            return

    await websocket.accept()

    chat_broker = _get_or_create_chat_broker(websocket.app)
    await chat_broker.register(order_id, websocket)

    redis = getattr(websocket.app.state, "redis", None)

    try:
        while True:
            try:
                raw = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=WS_IDLE_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                ws_idle_timeout_total.labels(channel="chat").inc()
                logger.info(
                    "ws.idle_timeout",
                    extra={
                        "channel": "chat",
                        "order_id": str(order_id),
                        "user_id": str(user_id),
                    },
                )
                try:
                    await websocket.close(code=4002, reason="idle_timeout")
                except Exception:
                    pass
                break

            try:
                data = json.loads(raw)
            except (TypeError, ValueError):
                continue

            if data.get("type") == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
                continue

            try:
                msg_type = MessageType(data.get("type", "text"))
            except ValueError:
                msg_type = MessageType.text

            content = data.get("content") or ""
            nonce = data.get("nonce") or data.get("client_nonce")

            # Route through ChatService — no direct model writes here.
            async with async_session() as session:
                svc = ChatService(session)
                _msg, payload, is_dup = await svc.send_message_via_ws(
                    order_id=order_id,
                    sender_id=user_id,
                    content=content,
                    msg_type=msg_type,
                    nonce=nonce,
                    redis=redis,
                )

            if is_dup or not payload:
                continue

            await chat_broker.publish_to_room(order_id, payload)

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await chat_broker.unregister(order_id, websocket)
