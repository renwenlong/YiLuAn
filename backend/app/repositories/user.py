from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    def __init__(self, session: AsyncSession):
        super().__init__(User, session)

    async def get_by_phone(self, phone: str) -> User | None:
        stmt = select(User).where(User.phone == phone)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_wechat_openid(self, openid: str) -> User | None:
        stmt = select(User).where(User.wechat_openid == openid)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(
        self, *, skip: int = 0, limit: int = 20
    ) -> tuple[Sequence[User], int]:
        """Admin: list all users."""
        total = (
            await self.session.execute(
                select(func.count()).select_from(User)
            )
        ).scalar_one()
        stmt = (
            select(User)
            .order_by(User.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all(), total
