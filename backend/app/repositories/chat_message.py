from typing import Sequence
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat_message import ChatMessage
from app.repositories.base import BaseRepository


class ChatMessageRepository(BaseRepository[ChatMessage]):
    def __init__(self, session: AsyncSession):
        super().__init__(ChatMessage, session)

    async def list_by_order(
        self,
        order_id: UUID,
        *,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[Sequence[ChatMessage], int]:
        base = select(ChatMessage).where(ChatMessage.order_id == order_id)
        count_stmt = select(func.count()).select_from(base.subquery())
        total = (await self.session.execute(count_stmt)).scalar() or 0

        stmt = base.order_by(ChatMessage.created_at.asc()).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all(), total

    async def list_before(
        self,
        order_id: UUID,
        *,
        before_id: UUID | None,
        limit: int = 50,
    ) -> tuple[Sequence[ChatMessage], int]:
        """Pull-up history pagination.

        Returns the most recent ``limit`` messages strictly older than
        ``before_id`` (or the tail of the conversation when ``before_id``
        is ``None``). Result is returned in ascending
        ``(created_at, id)`` order so the client can simply prepend the
        batch to the top of its existing message list.

        Also returns the total message count for the order so the caller
        can decide whether more pages are available.
        """
        base = select(ChatMessage).where(ChatMessage.order_id == order_id)
        count_stmt = select(func.count()).select_from(base.subquery())
        total = (await self.session.execute(count_stmt)).scalar() or 0

        anchor_created_at = None
        if before_id is not None:
            row = (
                await self.session.execute(
                    select(ChatMessage.created_at, ChatMessage.id)
                    .where(ChatMessage.id == before_id)
                    .where(ChatMessage.order_id == order_id)
                )
            ).first()
            if row is not None:
                anchor_created_at = row[0]
            else:
                before_id = None

        stmt = select(ChatMessage).where(ChatMessage.order_id == order_id)
        if anchor_created_at is not None and before_id is not None:
            stmt = stmt.where(
                (ChatMessage.created_at < anchor_created_at)
                | (
                    (ChatMessage.created_at == anchor_created_at)
                    & (ChatMessage.id < before_id)
                )
            )
        stmt = stmt.order_by(
            ChatMessage.created_at.desc(), ChatMessage.id.desc()
        ).limit(limit)
        rows = (await self.session.execute(stmt)).scalars().all()
        return list(reversed(rows)), total

    async def list_since(
        self,
        order_id: UUID,
        *,
        after_id: UUID | None,
        limit: int = 100,
    ) -> Sequence[ChatMessage]:
        """H3-be: incremental backfill after a known message id.

        Ordering: ``(created_at ASC, id ASC)`` so reconnect/backfill is
        deterministic even when two messages share a millisecond.

        If ``after_id`` is None, returns the earliest ``limit`` messages
        for the order — i.e. behaves like a forward-paginated cursor seeded
        at the head, useful for clients that lost their entire local cache.

        ``limit`` is hard-capped at 200 by the caller (see the API layer).
        """
        anchor_created_at = None
        if after_id is not None:
            row = (
                await self.session.execute(
                    select(ChatMessage.created_at, ChatMessage.id)
                    .where(ChatMessage.id == after_id)
                    .where(ChatMessage.order_id == order_id)
                )
            ).first()
            if row is None:
                # Unknown anchor for this order — treat as "give me everything"
                # rather than 404 so a client with stale cursor still recovers.
                anchor_created_at = None
                after_id = None
            else:
                anchor_created_at = row[0]

        stmt = select(ChatMessage).where(ChatMessage.order_id == order_id)
        if anchor_created_at is not None and after_id is not None:
            stmt = stmt.where(
                (ChatMessage.created_at > anchor_created_at)
                | (
                    (ChatMessage.created_at == anchor_created_at)
                    & (ChatMessage.id > after_id)
                )
            )
        stmt = stmt.order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc()).limit(
            limit
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def mark_as_read(self, order_id: UUID, reader_id: UUID) -> int:
        stmt = (
            update(ChatMessage)
            .where(
                ChatMessage.order_id == order_id,
                ChatMessage.sender_id != reader_id,
                ChatMessage.is_read == False,
            )
            .values(is_read=True)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount
