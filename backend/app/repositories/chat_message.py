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
