"""F-05 routes: `/api/v1/users/me/family-members` CRUD.

Hardcoded under `/users` to match the existing patient-profile prefix
style; access is always owner-scoped via CurrentUser.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter

from app.api.v1.openapi_meta import err
from app.dependencies import CurrentUser, DBSession
from app.schemas.family_member import (
    CreateFamilyMemberRequest,
    FamilyMemberListResponse,
    FamilyMemberResponse,
    UpdateFamilyMemberRequest,
)
from app.services.family_member import FamilyMemberService

router = APIRouter(prefix="/users", tags=["family-members"])


@router.get(
    "/me/family-members",
    response_model=FamilyMemberListResponse,
    summary="获取我的家人列表 (F-05)",
    description="按创建时间升序返回当前用户所有未软删除的家人/被陪诊人档案。",
    responses={**err(401, 500)},
)
async def list_family_members(current_user: CurrentUser, session: DBSession):
    service = FamilyMemberService(session)
    items = await service.list_for_user(current_user.id)
    return FamilyMemberListResponse(
        items=[FamilyMemberResponse.model_validate(m) for m in items],
        total=len(items),
    )


@router.post(
    "/me/family-members",
    response_model=FamilyMemberResponse,
    status_code=201,
    summary="新增一位家人 (F-05)",
    responses={**err(401, 422, 500)},
)
async def create_family_member(
    body: CreateFamilyMemberRequest,
    current_user: CurrentUser,
    session: DBSession,
):
    service = FamilyMemberService(session)
    member = await service.create(current_user.id, body)
    return FamilyMemberResponse.model_validate(member)


@router.patch(
    "/me/family-members/{member_id}",
    response_model=FamilyMemberResponse,
    summary="更新一位家人 (F-05)",
    responses={**err(401, 404, 422, 500)},
)
async def update_family_member(
    member_id: UUID,
    body: UpdateFamilyMemberRequest,
    current_user: CurrentUser,
    session: DBSession,
):
    service = FamilyMemberService(session)
    member = await service.update(current_user.id, member_id, body)
    return FamilyMemberResponse.model_validate(member)


@router.delete(
    "/me/family-members/{member_id}",
    status_code=204,
    summary="软删除一位家人 (F-05)",
    description="软删除：标记 deleted_at，历史订单仍可解析快照。",
    responses={**err(401, 404, 500)},
)
async def delete_family_member(
    member_id: UUID,
    current_user: CurrentUser,
    session: DBSession,
):
    service = FamilyMemberService(session)
    await service.delete(current_user.id, member_id)
    return None
