from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.family_member import FamilyMember
from app.repositories.base import BaseRepository


class FamilyMemberRepository(BaseRepository[FamilyMember]):
    """Soft-delete aware repository for `family_members`.

    All "live" reads exclude `deleted_at IS NOT NULL`; historical orders
    that reference a deleted member can still resolve via `get_by_id`
    (which intentionally bypasses the filter).
    """

    def __init__(self, session: AsyncSession):
        super().__init__(FamilyMember, session)

    async def list_active_by_user(self, user_id: UUID) -> list[FamilyMember]:
        stmt = (
            select(FamilyMember)
            .where(
                FamilyMember.user_id == user_id,
                FamilyMember.deleted_at.is_(None),
            )
            .order_by(FamilyMember.created_at.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_active_for_user(
        self, member_id: UUID, user_id: UUID
    ) -> FamilyMember | None:
        """Owner-scoped active fetch — returns None for soft-deleted or
        cross-user reads. Used by API handlers to enforce isolation."""
        stmt = select(FamilyMember).where(
            FamilyMember.id == member_id,
            FamilyMember.user_id == user_id,
            FamilyMember.deleted_at.is_(None),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
