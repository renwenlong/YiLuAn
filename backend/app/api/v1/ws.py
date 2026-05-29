"""WebSocket endpoints (C-12 / TD-MSG-04 / WS-AUTH-HANDSHAKE).

所有写路径统一走 `ChatService`，handler 只负责：
1. accept 后通过首帧 ``{type: "auth", token: "<jwt>"}`` 鉴权
   （5s 超时 → close 4011；旧客户端的 ``?token=`` 查询参数仍兼容，但会
   打 deprecated metric / warning log，将在客户端全量升级后下线）
2. 参与方校验（chat 通道）
3. asyncio idle timeout（默认 90s，超时主动关闭并打 metric）
4. nonce 透传到 ChatService（TD-MSG-01 客户端幂等）
5. broker fanout（本地 + Redis Pub/Sub）

不破坏现有 frame 契约：
- 上行：``{type: "auth", token: "..."}``                ← 新增，必须为首帧
- 上行：``{type: "ping"}`` → 下行 ``{type: "pong"}``
- 上行：``{type: "text"|"image"|"system", content: "...", nonce?: "..."}``
- 下行：``{type: "auth_ok"}`` 立刻回，便于客户端区分鉴权完成
- 下行（broadcast）：``{id, order_id, sender_id, type, content, is_read,
   created_at, nonce?}``

Close codes:
- 4001  invalid token (任一路径)
- 4003  not a participant (chat)
- 4004  order not found (chat)
- 4008  evicted by newer connection (per-user cap)
- 4011  auth handshake timeout / invalid auth frame
- 4012  family-share viewer sent an upstream write frame (ADR-0036 §2.4)
- 4013  family-share token revoked while connection was live
- 4014  per-share-token connection cap exceeded
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
from app.utils.metrics import ws_auth_handshake_total, ws_idle_timeout_total
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

# Server-side timeout for the auth handshake (first frame after accept()).
# Generous enough for poor mobile networks but short enough to thwart
# squatting connections.
WS_AUTH_HANDSHAKE_TIMEOUT_SECONDS = 5


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


def _user_id_from_token(token: str | None) -> UUID | None:
    """Decode an access JWT and return the bound user_id, or None on failure."""
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


async def _authenticate(websocket: WebSocket, channel: str) -> UUID | None:
    """Resolve user_id for an inbound WS connection.

    Order of resolution:
      1. Legacy ``?token=<jwt>`` query param — kept for the migration
         window so already-released miniprogram builds keep working. Marked
         with ``ws_auth_handshake_total{result="legacy_query"}`` and a
         WARNING log so we can confirm rollout before removal.
      2. First-frame handshake ``{type:"auth", token:"..."}`` — preferred
         path. Token never leaves the WS payload, so it does not land in
         nginx access logs / proxy traces.

    On any failure the websocket is closed with an appropriate code and
    ``None`` is returned. Caller must early-return on ``None``.
    """
    # ---- (1) Legacy query path -------------------------------------------
    # Resolve BEFORE accept(): if the legacy token is invalid we can reject
    # with the historical 4001 code and skip the handshake entirely.
    legacy_token = websocket.query_params.get("token")
    if legacy_token:
        user_id = _user_id_from_token(legacy_token)
        if user_id is None:
            ws_auth_handshake_total.labels(channel=channel, result="invalid_token").inc()
            await websocket.close(code=4001, reason="Invalid token")
            return None
        await websocket.accept()
        ws_auth_handshake_total.labels(channel=channel, result="legacy_query").inc()
        logger.warning(
            "ws.auth.legacy_query",
            extra={"channel": channel, "user_id": str(user_id)},
        )
        return user_id

    # ---- (2) First-frame handshake ---------------------------------------
    await websocket.accept()
    try:
        raw = await asyncio.wait_for(
            websocket.receive_text(),
            timeout=WS_AUTH_HANDSHAKE_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        ws_auth_handshake_total.labels(channel=channel, result="timeout").inc()
        logger.info("ws.auth.timeout", extra={"channel": channel})
        try:
            await websocket.close(code=4011, reason="auth_timeout")
        except Exception:
            pass
        return None
    except WebSocketDisconnect:
        ws_auth_handshake_total.labels(channel=channel, result="invalid_frame").inc()
        return None

    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        data = None
    if not isinstance(data, dict) or data.get("type") != "auth":
        ws_auth_handshake_total.labels(channel=channel, result="invalid_frame").inc()
        try:
            await websocket.close(code=4011, reason="auth_required")
        except Exception:
            pass
        return None

    user_id = _user_id_from_token(data.get("token"))
    if user_id is None:
        ws_auth_handshake_total.labels(channel=channel, result="invalid_token").inc()
        try:
            await websocket.close(code=4001, reason="Invalid token")
        except Exception:
            pass
        return None

    ws_auth_handshake_total.labels(channel=channel, result="success").inc()
    # Tell the client auth is done so it can flush any queued frames.
    try:
        await websocket.send_text(json.dumps({"type": "auth_ok"}))
    except Exception:
        # Connection closed mid-handshake; treat as failed.
        return None
    return user_id


@router.websocket("/ws/notifications")
async def websocket_notifications(websocket: WebSocket):
    """Global notification WebSocket.

    Auth: first frame ``{type:"auth", token:"<jwt>"}`` (preferred) OR
    legacy ``?token=<jwt>`` query param (deprecated, see _authenticate).
    """
    user_id = await _authenticate(websocket, channel="notifications")
    if user_id is None:
        return

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
    """Order-scoped chat WebSocket. 全部走 ChatService。

    Auth: same handshake-or-legacy contract as ``/ws/notifications``.
    Pre-flight authorisation (order exists + user is participant) runs
    AFTER auth completes, so we can return a precise close code.
    """
    user_id = await _authenticate(websocket, channel="chat")
    if user_id is None:
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


# ---------------------------------------------------------------------------
# ADR-0036 §2.4 family-share WebSocket
# ---------------------------------------------------------------------------

SHARE_LOC_CACHE_KEY = "share:loc:{order_id}"


def _get_or_create_share_broker(app) -> WsPubSubBroker:
    from app.ws.pubsub import get_ws_share_broker_from_app

    broker = get_ws_share_broker_from_app(app)
    if broker is not None:
        return broker
    # Local fallback for tests / single-instance dev: in-memory only, no
    # Redis fanout. Mirrors the chat broker fallback pattern above.
    global _fallback_share_broker
    try:
        _fallback_share_broker  # type: ignore[name-defined]
    except NameError:
        _fallback_share_broker = None  # type: ignore[assignment]
    if _fallback_share_broker is None:  # type: ignore[name-defined]
        _fallback_share_broker = WsPubSubBroker(  # type: ignore[assignment]
            redis_client=None, enabled=False, key_field="order_id"
        )
        _fallback_share_broker._started = True  # type: ignore[attr-defined]
    return _fallback_share_broker  # type: ignore[return-value]


async def _share_auth_handshake(websocket: WebSocket) -> dict | None:
    """Wait for the first ``{type: 'share_auth', session: <JWT>}`` frame.

    Returns the decoded JWT payload on success, else closes the socket
    with the appropriate ``4011`` and returns ``None``.
    """
    from app.services.share import decode_share_session
    from app.exceptions import UnauthorizedException

    try:
        raw = await asyncio.wait_for(
            websocket.receive_text(),
            timeout=WS_AUTH_HANDSHAKE_TIMEOUT_SECONDS,
        )
    except (asyncio.TimeoutError, WebSocketDisconnect):
        try:
            await websocket.close(code=4011, reason="auth_timeout")
        except Exception:
            pass
        return None

    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        await websocket.close(code=4011, reason="invalid_auth_frame")
        return None

    if data.get("type") != "share_auth":
        await websocket.close(code=4011, reason="invalid_auth_frame")
        return None

    session_jwt = data.get("session")
    if not session_jwt or not isinstance(session_jwt, str):
        await websocket.close(code=4001, reason="missing_session")
        return None

    try:
        payload = decode_share_session(session_jwt)
    except UnauthorizedException:
        await websocket.close(code=4001, reason="invalid_session")
        return None

    return payload


@router.websocket("/ws/share/{token}")
async def websocket_share(websocket: WebSocket, token: str):
    """Family-share read-only WebSocket (ADR-0036 §2.4).

    Auth: first frame ``{type: "share_auth", session: "<share_session_jwt>"}``.
    Server-to-client only — any upstream non-ping frame closes with 4012.
    """
    await websocket.accept()
    payload = await _share_auth_handshake(websocket)
    if payload is None:
        return

    from app.repositories.order_share_token import OrderShareTokenRepository

    # Re-validate the underlying token row server-side: even with a valid
    # JWT the row might be revoked or expired in the meantime.
    async with async_session() as session:
        row_repo = OrderShareTokenRepository(session)
        token_row = await row_repo.get_by_token(token)
        if token_row is None or not token_row.is_active:
            await websocket.close(code=4013, reason="token_revoked_or_expired")
            return
        # The JWT was minted for *this* token id — defend against a stolen
        # JWT being re-bound to a different token in the URL.
        if str(token_row.id) != payload.get("tid"):
            await websocket.close(code=4001, reason="token_mismatch")
            return
        # S2-DEV-006: record this WS access into the audit log so the anomaly
        # scanner's 24h distinct-accessor count sees family viewers who only
        # ever connect over WS (live tracking) and never re-hit the REST
        # session endpoint.
        accessor = payload.get("acc")
        if accessor:
            try:
                await row_repo.record_access(
                    token_row, accessor_openid=str(accessor)
                )
                await session.commit()
            except Exception:  # never block the connection on audit write
                logger.debug("share ws record_access failed", exc_info=True)

    order_id = token_row.order_id
    share_broker = _get_or_create_share_broker(websocket.app)

    # Per-token connection cap (ADR-0036 §2.4: ≤ 3). We key by the *token*
    # value here so different tokens for the same order don't collide.
    cap = settings.ws_share_max_connections_per_token
    if cap and cap > 0:
        # We piggy-back on register_with_cap's "evict oldest" semantics but
        # close with 4014 instead of 4008 because the contract is different
        # (cap-exceeded, not user-replaced).
        evicted = await share_broker.register_with_cap(
            f"token:{token}", websocket, cap
        )
        for old_ws in evicted:
            try:
                await old_ws.close(code=4014, reason="per_token_cap_exceeded")
            except Exception:
                pass

    # Subscribe to share:{order_id} via the same broker for fanout.
    await share_broker.register(order_id, websocket)

    # Replay the cached last-known position so a reconnect doesn't show
    # a blank map (ADR-0036 §2.4 断线重连补偿).
    redis = getattr(websocket.app.state, "redis", None)
    if redis is not None:
        try:
            cached = await redis.get(
                SHARE_LOC_CACHE_KEY.format(order_id=order_id)
            )
            if cached:
                cached_str = (
                    cached.decode("utf-8") if isinstance(cached, bytes) else cached
                )
                await websocket.send_text(
                    json.dumps({"type": "location_replay", "data": json.loads(cached_str)})
                )
        except Exception:  # pragma: no cover — best effort
            logger.debug("share loc cache replay failed", exc_info=True)

    await websocket.send_text(json.dumps({"type": "share_auth_ok"}))

    try:
        while True:
            try:
                raw = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=WS_IDLE_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                ws_idle_timeout_total.labels(channel="share").inc()
                try:
                    await websocket.close(code=4002, reason="idle_timeout")
                except Exception:
                    pass
                break

            try:
                data = json.loads(raw)
            except (TypeError, ValueError):
                # 仅 ping 允许上行；非 JSON 直接当违规 close 4012
                await websocket.close(code=4012, reason="upstream_write_forbidden")
                break

            if data.get("type") == "ping":
                # Re-validate token liveness on every heartbeat so a token
                # revoked mid-session (manual revoke OR the S2-DEV-006 anomaly
                # scanner) gets the live socket kicked with 4013 within one
                # ping interval, not just at next connect.
                async with async_session() as recheck_session:
                    fresh = await OrderShareTokenRepository(
                        recheck_session
                    ).get_by_token(token)
                if fresh is None or not fresh.is_active:
                    await websocket.close(
                        code=4013, reason="token_revoked_or_expired"
                    )
                    break
                await websocket.send_text(json.dumps({"type": "pong"}))
                continue

            # 任意非 ping 上行都是禁止的写入尝试 (§2.4 + §3.5 #6)
            await websocket.close(code=4012, reason="upstream_write_forbidden")
            break
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await share_broker.unregister(order_id, websocket)
        if cap and cap > 0:
            await share_broker.unregister(f"token:{token}", websocket)
