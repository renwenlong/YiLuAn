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

PII handling (W18 admin-h5 contract fix)
----------------------------------------
- ``phone`` is **masked by default** (`138******78`) on every list / detail
  response; the masked form is also exposed as ``phone_masked`` for UI
  binding.
- Pass ``?reveal=true`` to receive the full phone. Each reveal writes an
  ``AdminAuditLog`` row with ``action="reveal_pii"`` so a security
  reviewer can answer "who looked up which patient's phone" later.
- Every list / get also writes a lightweight ``view_*`` audit entry
  (single row per request; list endpoints record a summary, not per-item)
  so the read side is no longer a black box.

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
from app.core.pii import mask_phone
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


# Sentinel used for list-scoped audit rows (no single target).
_LIST_TARGET = UUID("00000000-0000-0000-0000-000000000000")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class UserItem(BaseModel):
    id: str
    phone: str | None = Field(
        None,
        description=(
            "手机号。默认脱敏（前3后2，中间 *）；?reveal=true 时返回完整号码并写"
            " reveal_pii 审计。"
        ),
    )
    phone_masked: str | None = Field(
        None, description="脱敏手机号；永远脱敏，可直接绑定 UI。"
    )
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


def _to_item(u: User, *, reveal: bool = False) -> dict:
    masked = mask_phone(u.phone) if u.phone else None
    return {
        "id": str(u.id),
        "phone": u.phone if reveal else masked,
        "phone_masked": masked,
        "role": u.role.value if u.role else None,
        "roles": u.roles,
        "display_name": u.display_name,
        "is_active": u.is_active,
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }


def _audit(
    session,
    *,
    target_type: str,
    target_id: UUID,
    action: str,
    reason: str | None = None,
) -> None:
    session.add(
        AdminAuditLog(
            target_type=target_type,
            target_id=target_id,
            action=action,
            operator="admin-token",
            reason=reason,
        )
    )


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
    reveal: bool = Query(
        False,
        description="是否返回明文手机号；置 true 会写入 reveal_pii 审计日志。",
    ),
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
    payload_items = [_to_item(u, reveal=reveal) for u in items]

    summary = (
        f"role={role} is_active={is_active} phone={phone} "
        f"page={page} limit={page_size} returned={len(payload_items)} "
        f"reveal={reveal}"
    )
    _audit(
        session,
        target_type="user",
        target_id=_LIST_TARGET,
        action="view_users_list",
        reason=summary,
    )
    if reveal:
        for u in items:
            if u.phone:
                _audit(
                    session,
                    target_type="user",
                    target_id=u.id,
                    action="reveal_pii",
                    reason="field=phone via=list",
                )
    await session.flush()

    return {
        "items": payload_items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get(
    "/{user_id}",
    response_model=UserItem,
    summary="后台：用户详情",
    description="返回单个用户详情；phone 默认脱敏，?reveal=true 返回明文并写 reveal_pii 审计；同时写入 view_user_detail 审计行。",
)
async def get_user(
    user_id: UUID,
    session: DBSession,
    reveal: bool = Query(
        False,
        description="是否返回明文手机号；置 true 会写入 reveal_pii 审计日志。",
    ),
):
    repo = UserRepository(session)
    user = await repo.get_by_id(user_id)
    if user is None:
        raise NotFoundException("User not found")

    _audit(
        session,
        target_type="user",
        target_id=user_id,
        action="view_user_detail",
        reason=f"reveal={reveal}",
    )
    if reveal and user.phone:
        _audit(
            session,
            target_type="user",
            target_id=user_id,
            action="reveal_pii",
            reason="field=phone via=detail",
        )
    await session.flush()

    return _to_item(user, reveal=reveal)


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
    _audit(
        session,
        target_type="user",
        target_id=user_id,
        action="disable",
        reason=body.reason,
    )
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
    _audit(
        session,
        target_type="user",
        target_id=user_id,
        action="enable",
    )
    await session.flush()

    return {"user_id": str(user_id), "is_active": True}
