from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.followup_reminder import FollowupReminder, FollowupReminderStatus
from app.repositories.base import BaseRepository


class FollowupReminderRepository(BaseRepository[FollowupReminder]):
    def __init__(self, session: AsyncSession):
        super().__init__(FollowupReminder, session)

    async def list_by_user(self, user_id: UUID) -> list[FollowupReminder]:
        stmt = (
            select(FollowupReminder)
            .where(FollowupReminder.user_id == user_id)
            .order_by(FollowupReminder.remind_at.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_for_user(
        self, reminder_id: UUID, user_id: UUID
    ) -> FollowupReminder | None:
        stmt = select(FollowupReminder).where(
            FollowupReminder.id == reminder_id,
            FollowupReminder.user_id == user_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_due(self, now, *, limit: int = 100) -> list[FollowupReminder]:
        """cron 使用：返回到点应派发的 pending 提醒。"""
        stmt = (
            select(FollowupReminder)
            .where(
                FollowupReminder.status == FollowupReminderStatus.pending,
                FollowupReminder.remind_at <= now,
            )
            .order_by(FollowupReminder.remind_at.asc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
