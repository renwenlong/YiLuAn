"""ChatService — 单一聊天业务入口（C-12 / TD-MSG-04 后）。

所有写路径（HTTP `/chats/{order_id}/messages` 与 `WS /ws/chat/{order_id}`）
统一走本服务，避免 ws handler 直接操作 Model 造成的双轨权限/校验/幂等代码。

核心方法：
- `send_message`            ：HTTP 兜底入口，需要 `User` 对象
- `send_message_via_ws`     ：WS 入口，按 `user_id` 直接落库 + nonce 幂等去重
- `list_messages`           ：分页查询
- `mark_read`               ：批量已读
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import ForbiddenException, NotFoundException
from app.models.chat_message import ChatMessage, MessageType
from app.models.order import Order
from app.models.user import User
from app.repositories.chat_message import ChatMessageRepository
from app.repositories.order import OrderRepository
from app.repositories.user import UserRepository
from app.schemas.chat import SendMessageRequest
from app.services.notification import NotificationService

logger = logging.getLogger(__name__)


# Redis key for client nonce idempotency (TD-MSG-01).
# TTL 300s = 5min, matches client-side LRU window.
NONCE_KEY_TPL = "chat:nonce:{user_id}:{nonce}"
NONCE_TTL_SECONDS = 300

# Max content length aligned with WS path & SendMessageRequest schema.
MAX_CONTENT_LEN = 4000


class ChatService:
    def __init__(self, session: AsyncSession):
        self.chat_repo = ChatMessageRepository(session)
        self.order_repo = OrderRepository(session)
        self.user_repo = UserRepository(session)
        self.notification_svc = NotificationService(session)
        self.session = session

    # ------------------------------------------------------------------
    # HTTP entrypoint (existing contract preserved)
    # ------------------------------------------------------------------
    async def send_message(
        self, order_id: uuid.UUID, user: User, data: SendMessageRequest
    ) -> ChatMessage:
        order = await self._get_order_and_validate(order_id, user.id)

        message = ChatMessage(
            order_id=order_id,
            sender_id=user.id,
            type=MessageType(data.type),
            content=data.content,
        )
        message = await self.chat_repo.create(message)

        recipient_id = (
            order.companion_id if order.patient_id == user.id else order.patient_id
        )
        if recipient_id:
            await self.notification_svc.notify_new_message(
                order_id=order_id,
                sender_name=user.display_name or user.phone,
                recipient_id=recipient_id,
            )

        return message

    # ------------------------------------------------------------------
    # WebSocket entrypoint — used by app/api/v1/ws.py (C-12)
    # ------------------------------------------------------------------
    async def send_message_via_ws(
        self,
        order_id: uuid.UUID,
        sender_id: uuid.UUID,
        content: str,
        msg_type: MessageType,
        *,
        nonce: Optional[str] = None,
        redis: Any = None,
    ) -> tuple[Optional[ChatMessage], dict[str, Any], bool]:
        """Persist + return (message, broadcast_payload, is_duplicate).

        * Authorization (participant check) ＆ content trimming consolidated here.
        * If `nonce` + `redis` provided, run Redis SETNX dedup against
          `chat:nonce:{sender_id}:{nonce}` with TTL=300s. Repeat hits return
          (None, {}, True) — caller should *not* re-broadcast.
        * Returns the persisted message + a JSON-safe payload for broadcasting.
        """
        # ---- permission ----
        await self._get_order_and_validate(order_id, sender_id)

        # ---- normalise content ----
        text = (content or "").strip()
        if not text:
            return None, {}, False
        if len(text) > MAX_CONTENT_LEN:
            text = text[:MAX_CONTENT_LEN]

        # ---- nonce dedup (TD-MSG-01) ----
        if nonce and redis is not None:
            key = NONCE_KEY_TPL.format(user_id=sender_id, nonce=nonce)
            try:
                # Prefer SETNX-equivalent: SET key val NX EX 300.
                # Falls back to plain `set + ttl` for FakeRedis.
                existed = None
                if hasattr(redis, "set"):
                    try:
                        existed = await redis.set(  # type: ignore[call-arg]
                            key, "1", ex=NONCE_TTL_SECONDS, nx=True
                        )
                    except TypeError:
                        # FakeRedis without `nx=` kwarg → emulate with get/setex
                        prev = await redis.get(key)
                        if prev is not None:
                            existed = None  # treated as duplicate
                        else:
                            await redis.setex(key, NONCE_TTL_SECONDS, "1")
                            existed = True
                if existed is None:
                    logger.info(
                        "ws.nonce.dedup",
                        extra={"sender_id": str(sender_id), "nonce": nonce},
                    )
                    return None, {}, True
            except Exception as exc:  # pragma: no cover - never fail message on Redis hiccup
                logger.warning("nonce dedup skipped (redis error): %s", exc)

        # ---- persist ----
        message = ChatMessage(
            order_id=order_id,
            sender_id=sender_id,
            type=msg_type,
            content=text,
        )
        message = await self.chat_repo.create(message)
        await self.session.commit()

        payload = {
            "id": str(message.id),
            "order_id": str(order_id),
            "sender_id": str(sender_id),
            "type": msg_type.value,
            "content": text,
            "is_read": False,
            "created_at": message.created_at.isoformat(),
        }
        if nonce:
            payload["nonce"] = nonce

        return message, payload, False

    async def list_messages(
        self,
        order_id: uuid.UUID,
        user: User,
        *,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list, int]:
        await self._get_order_and_validate(order_id, user.id)
        skip = (page - 1) * page_size
        return await self.chat_repo.list_by_order(
            order_id, skip=skip, limit=page_size
        )

    async def mark_read(self, order_id: uuid.UUID, user: User) -> int:
        await self._get_order_and_validate(order_id, user.id)
        return await self.chat_repo.mark_as_read(order_id, user.id)

    # ------------------------------------------------------------------
    # internal
    # ------------------------------------------------------------------
    async def _get_order_and_validate(
        self, order_id: uuid.UUID, user_id: uuid.UUID
    ) -> Order:
        order = await self.order_repo.get_by_id(order_id)
        if order is None:
            raise NotFoundException("Order not found")

        is_patient = order.patient_id == user_id
        is_companion = order.companion_id == user_id
        if not is_patient and not is_companion:
            raise ForbiddenException("Not a participant of this order")

        return order
