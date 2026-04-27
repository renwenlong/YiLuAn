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

    async def get_by_apple_sub(self, apple_sub: str) -> User | None:
        stmt = select(User).where(User.apple_sub == apple_sub)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(
        self,
        *,
        role: str | None = None,
        is_active: bool | None = None,
        phone: str | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> tuple[Sequence[User], int]:
        """Admin: list users with optional filters.

        Filters:
          * ``role``: matches comma-separated User.roles (substring match
            on a single role tag).
          * ``is_active``: ``True`` to include only enabled accounts,
            ``False`` to include only disabled.
          * ``phone``: substring match (LIKE %x%) on phone column.
        """
        where_clause = []
        if role:
            where_clause.append(User.roles.ilike(f"%{role}%"))
        if is_active is not None:
            where_clause.append(User.is_active == is_active)
        if phone:
            where_clause.append(User.phone.ilike(f"%{phone}%"))

        count_stmt = select(func.count()).select_from(User)
        if where_clause:
            count_stmt = count_stmt.where(*where_clause)
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = select(User)
        if where_clause:
            stmt = stmt.where(*where_clause)
        stmt = stmt.order_by(User.created_at.desc()).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all(), total
