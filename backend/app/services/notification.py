import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification, NotificationType
from app.models.user import User
from app.repositories.notification import NotificationRepository


class NotificationService:
    def __init__(self, session: AsyncSession):
        self.notification_repo = NotificationRepository(session)
        self.session = session

    async def list_notifications(
        self, user: User, *, page: int = 1, page_size: int = 20
    ) -> tuple[list, int]:
        skip = (page - 1) * page_size
        return await self.notification_repo.list_by_user(
            user.id, skip=skip, limit=page_size
        )

    async def count_unread(self, user: User) -> int:
        return await self.notification_repo.count_unread(user.id)

    async def mark_read(self, notification_id: uuid.UUID, user: User) -> bool:
        return await self.notification_repo.mark_as_read(notification_id, user.id)

    async def mark_all_read(self, user: User) -> int:
        return await self.notification_repo.mark_all_read(user.id)

    async def create_notification(
        self,
        user_id: uuid.UUID,
        type: NotificationType,
        title: str,
        body: str,
        reference_id: str | None = None,
    ) -> Notification:
        notification = Notification(
            user_id=user_id,
            type=type,
            title=title,
            body=body,
            reference_id=reference_id,
        )
        return await self.notification_repo.create(notification)
