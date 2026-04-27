"""
Admin Users — user management (B4).

Routes: /api/v1/admin/users
Auth: X-Admin-Token header (token-based; v2 will migrate to JWT).

Endpoints
---------
GET    /                       list users, filters: role / is_active / phone
GET    /{user_id}              user detail
POST   /{user_id}/disable      body {reason} — set is_active=False (audited)
POST   /{user_id}/enable       set is_active=True (audited)

Self-protection note
--------------------
Under token-based auth there is no concept of a "current admin user",
so we cannot block "admin disables themselves". This rule is deferred
to the v2 JWT migration; once a real authenticated admin identity
exists, add a check in :func:`disable_user` that compares ``user_id``
against the caller's ``sub`` claim and rejects with 403.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.core.admin_auth import require_admin_token
from app.dependencies import DBSession
from app.exceptions import NotFoundException
from app.models.admin_audit_log import AdminAuditLog
from app.models.user import User
from app.repositories.user import UserRepository

router = APIRouter(
    prefix="/users",
    tags=["admin-users"],
    dependencies=[Depends(require_admin_token)],
)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class UserItem(BaseModel):
    id: str
    phone: str | None
    role: str | None
    roles: str | None
    display_name: str | None
    is_active: bool
    created_at: str | None


class PaginatedUsers(BaseModel):
    items: list[UserItem]
    total: int
    page: int
    page_size: int


class DisableBody(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500, description="停用原因")


class UserStatusResponse(BaseModel):
    user_id: str
    is_active: bool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_item(u: User) -> dict:
    return {
        "id": str(u.id),
        "phone": u.phone,
        "role": u.role.value if u.role else None,
        "roles": u.roles,
        "display_name": u.display_name,
        "is_active": u.is_active,
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=PaginatedUsers,
    summary="后台：用户列表",
    description="分页查询用户，支持按 role / is_active / phone 模糊过滤。",
)
async def list_users(
    session: DBSession,
    role: str | None = Query(None, description="角色 tag，如 patient / companion / admin"),
    is_active: bool | None = Query(None),
    phone: str | None = Query(None, description="手机号模糊匹配"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    repo = UserRepository(session)
    skip = (page - 1) * page_size
    items, total = await repo.list_all(
        role=role,
        is_active=is_active,
        phone=phone,
        skip=skip,
        limit=page_size,
    )
    return {
        "items": [_to_item(u) for u in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get(
    "/{user_id}",
    response_model=UserItem,
    summary="后台：用户详情",
)
async def get_user(user_id: UUID, session: DBSession):
    repo = UserRepository(session)
    user = await repo.get_by_id(user_id)
    if user is None:
        raise NotFoundException("User not found")
    return _to_item(user)


@router.post(
    "/{user_id}/disable",
    response_model=UserStatusResponse,
    summary="后台：停用用户",
    description="将指定用户置为 is_active=False。操作必须给出原因，写入 admin_audit_log。",
)
async def disable_user(
    user_id: UUID,
    body: DisableBody,
    session: DBSession,
):
    """Disable a user.

    TODO(v2-jwt): once admin auth uses JWT, reject if ``user_id`` matches
    the caller's own UUID to prevent self-lockout.
    """
    repo = UserRepository(session)
    user = await repo.get_by_id(user_id)
    if user is None:
        raise NotFoundException("User not found")

    user.is_active = False

    log = AdminAuditLog(
        target_type="user",
        target_id=user_id,
        action="disable",
        operator="admin-token",
        reason=body.reason,
    )
    session.add(log)
    await session.flush()

    return {"user_id": str(user_id), "is_active": False}


@router.post(
    "/{user_id}/enable",
    response_model=UserStatusResponse,
    summary="后台：启用用户",
    description="重新启用被停用账号；操作写入 admin_audit_log。",
)
async def enable_user(user_id: UUID, session: DBSession):
    repo = UserRepository(session)
    user = await repo.get_by_id(user_id)
    if user is None:
        raise NotFoundException("User not found")

    user.is_active = True

    log = AdminAuditLog(
        target_type="user",
        target_id=user_id,
        action="enable",
        operator="admin-token",
    )
    session.add(log)
    await session.flush()

    return {"user_id": str(user_id), "is_active": True}
