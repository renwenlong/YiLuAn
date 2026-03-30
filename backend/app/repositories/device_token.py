from typing import Sequence
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device_token import DeviceToken
from app.repositories.base import BaseRepository


class DeviceTokenRepository(BaseRepository[DeviceToken]):
    def __init__(self, session: AsyncSession):
        super().__init__(DeviceToken, session)

    async def get_by_user_and_token(
        self, user_id: UUID, token: str
    ) -> DeviceToken | None:
        stmt = select(DeviceToken).where(
            DeviceToken.user_id == user_id, DeviceToken.token == token
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_token(self, token: str) -> DeviceToken | None:
        stmt = select(DeviceToken).where(DeviceToken.token == token)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_user(self, user_id: UUID) -> Sequence[DeviceToken]:
        stmt = select(DeviceToken).where(DeviceToken.user_id == user_id)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def delete_by_token(self, user_id: UUID, token: str) -> bool:
        existing = await self.get_by_user_and_token(user_id, token)
        if existing:
            await self.delete(existing)
            return True
        return False
