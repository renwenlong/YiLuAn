"""F-05 service: family member CRUD with soft-delete + owner-scope."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import NotFoundException
from app.models.family_member import FamilyGender, FamilyMember, FamilyRelation
from app.repositories.family_member import FamilyMemberRepository
from app.schemas.family_member import (
    CreateFamilyMemberRequest,
    UpdateFamilyMemberRequest,
)


class FamilyMemberService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = FamilyMemberRepository(session)

    async def list_for_user(self, user_id: UUID) -> list[FamilyMember]:
        return await self.repo.list_active_by_user(user_id)

    async def create(
        self, user_id: UUID, data: CreateFamilyMemberRequest
    ) -> FamilyMember:
        member = FamilyMember(
            user_id=user_id,
            name=data.name,
            relation=FamilyRelation(data.relation),
            phone=data.phone,
            gender=FamilyGender(data.gender),
            age=data.age,
            medical_notes=data.medical_notes,
        )
        return await self.repo.create(member)

    async def update(
        self,
        user_id: UUID,
        member_id: UUID,
        data: UpdateFamilyMemberRequest,
    ) -> FamilyMember:
        member = await self.repo.get_active_for_user(member_id, user_id)
        if member is None:
            raise NotFoundException("Family member not found")
        payload = data.model_dump(exclude_unset=True)
        if "relation" in payload and payload["relation"] is not None:
            payload["relation"] = FamilyRelation(payload["relation"])
        if "gender" in payload and payload["gender"] is not None:
            payload["gender"] = FamilyGender(payload["gender"])
        if not payload:
            return member
        return await self.repo.update(member, payload)

    async def delete(self, user_id: UUID, member_id: UUID) -> None:
        member = await self.repo.get_active_for_user(member_id, user_id)
        if member is None:
            raise NotFoundException("Family member not found")
        await self.repo.update(
            member, {"deleted_at": datetime.now(timezone.utc)}
        )

    async def get_active_for_user(
        self, member_id: UUID, user_id: UUID
    ) -> FamilyMember | None:
        return await self.repo.get_active_for_user(member_id, user_id)
