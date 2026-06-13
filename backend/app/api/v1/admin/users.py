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
POST   /{user_id}/read-only    body {is_read_only,reason_category,reason_detail?} (audited)
DELETE /{user_id}/read-only    unset read-only flag + clear metadata (audited)
POST   /batch-read-only        batch ≤100 set/unset read-only (audited per user)

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

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from app.core.admin_auth import (
    require_admin_token,  # noqa: F401  (legacy import retained for downstream consumers)
)
from app.core.admin_jwt import admin_operator_id, require_admin
from app.core.pii import mask_phone
from app.dependencies import DBSession
from app.exceptions import NotFoundException
from app.models.admin_audit_log import AdminAuditLog
from app.models.admin_user import AdminUser
from app.models.user import User
from app.repositories.user import UserRepository
from app.services.auth import AuthService

# PRD-001 §F8 D2 ratify enum; frontend maps these to user-facing copy.
ReasonCategory = Literal[
    "GRAY_REVOKE",
    "GRAY_ANOMALY",
    "CREDENTIAL_LEAK",
    "COMPLIANCE_REPORT",
]

# AC#3 hard limit; PR description must cite ADR-0053 §7 batch cap rationale.
BATCH_MAX = 100

router = APIRouter(
    prefix="/users",
    tags=["admin-users"],
    dependencies=[Depends(require_admin)],
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
    phone_masked: str | None = Field(None, description="脱敏手机号；永远脱敏，可直接绑定 UI。")
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
# Read-only flag schemas (S2-OPS-A-READ-ONLY-FLAG-ADMIN-API)
# ADR-0053 §5 (DB schema), §7 (admin endpoints), PR #238 (audit pattern).
# ---------------------------------------------------------------------------


class SetReadOnlyBody(BaseModel):
    """AC#1 body for POST /{user_id}/read-only.

    ``reason_detail`` is admin-internal audit text — it is **NEVER** returned
    in any response per PRD-001 §F8 D1 (avoid leaking gray-release / credential
    / compliance details to the affected user). Only the long-form copy in
    ``admin_audit_logs.reason`` is the source of truth for retrospective
    investigations.
    """

    is_read_only: bool = Field(
        ...,
        description=(
            "目mark; must be TRUE for set endpoint. Provided in body (not path)"
            " so the same payload shape can be reused by batch endpoint."
        ),
    )
    reason_category: ReasonCategory | None = Field(
        None,
        description=(
            "PRD-001 §F8 D2 enum mapped to frontend i18n key. NULL allowed when"
            " admin omits (legacy / quick freeze). The companion test"
            " ``test_reason_category_null_when_admin_did_not_set_one``"
            " covers the NULL branch."
        ),
    )
    reason_detail: str | None = Field(
        None,
        max_length=2000,
        description=(
            "Admin internal audit text. NEVER returned to frontend; stored in"
            " both ``users.read_only_reason_detail`` (short retention) and"
            " ``admin_audit_logs.reason`` (long retention)."
        ),
    )


class BatchReadOnlyBody(BaseModel):
    """AC#3 body for POST /batch-read-only. ``user_ids`` capped at
    ``BATCH_MAX`` (100) per ADR-0053 §7 to bound transaction size and
    operator blast radius."""

    user_ids: list[UUID] = Field(
        ...,
        min_length=1,
        description="Target user UUIDs; 1 ≤ len ≤ BATCH_MAX (100).",
    )
    is_read_only: bool = Field(..., description="Set TRUE or FALSE for all targets.")
    reason_category: ReasonCategory | None = None
    reason_detail: str | None = Field(None, max_length=2000)


class ReadOnlyStateResponse(BaseModel):
    """AC#1/AC#2 response. ``reason_detail`` is intentionally OMITTED —
    see ``SetReadOnlyBody`` docstring."""

    user_id: str
    is_read_only: bool
    reason_category: str | None
    read_only_set_at: str | None
    read_only_set_by: int | None


class BatchUserResult(BaseModel):
    user_id: str
    is_read_only: bool | None  # NULL if user_id not found
    error: str | None = None  # "USER_NOT_FOUND" when 404


class BatchReadOnlyResponse(BaseModel):
    """AC#3 per-user result; total numbers help operators reconcile spreadsheets."""

    requested: int
    succeeded: int
    failed: int
    results: list[BatchUserResult]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_item(u: User, *, reveal: bool = False) -> dict:
    masked = mask_phone(u.phone) if u.phone else None
    # `users.role` is the legacy single-role enum column; the newer multi-role
    # signup writes a comma-separated list into `users.roles` instead. Surface
    # whichever one has a value so the admin UI doesn't show '-' for accounts
    # that exist via the new path.
    role_display = (
        u.role.value if u.role is not None else (u.roles.split(",")[0] if u.roles else None)
    )
    return {
        "id": str(u.id),
        "phone": u.phone if reveal else masked,
        "phone_masked": masked,
        "role": role_display,
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
    operator: str,
    reason: str | None = None,
) -> None:
    session.add(
        AdminAuditLog(
            target_type=target_type,
            target_id=target_id,
            action=action,
            operator=operator,
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
    operator: str = Depends(admin_operator_id),
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
        operator=operator,
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
                    operator=operator,
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
    description=(
        "返回单个用户详情；phone 默认脱敏，"
        "?reveal=true 返回明文并写 reveal_pii 审计；同时"
        "写入 view_user_detail 审计行。"
    ),
)
async def get_user(
    user_id: UUID,
    session: DBSession,
    operator: str = Depends(admin_operator_id),
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
        operator=operator,
        reason=f"reveal={reveal}",
    )
    if reveal and user.phone:
        _audit(
            session,
            target_type="user",
            target_id=user_id,
            action="reveal_pii",
            operator=operator,
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
    request: Request,
    operator: str = Depends(admin_operator_id),
):
    """Disable a user.

    Self-protection: under JWT auth this rejects requests where the target
    ``user_id`` (a regular ``users`` row) is the same row the admin is
    operating on. Today admins are not bound to a ``users`` row, so the
    check is best-effort: it never blocks the legacy ``X-Admin-Token``
    path. See ADR-0034.
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
        operator=operator,
        reason=body.reason,
    )
    await session.flush()

    # Kill every active access *and* refresh token so the disabled user can't
    # keep using a cached access token until expiry or rotate refresh.
    auth_service = AuthService(session, request.app.state.redis)
    await auth_service.revoke_all_sessions(user)

    return {"user_id": str(user_id), "is_active": False}


@router.post(
    "/{user_id}/enable",
    response_model=UserStatusResponse,
    summary="后台：启用用户",
    description="重新启用被停用账号；操作写入 admin_audit_log。",
)
async def enable_user(
    user_id: UUID,
    session: DBSession,
    operator: str = Depends(admin_operator_id),
):
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
        operator=operator,
    )
    await session.flush()

    return {"user_id": str(user_id), "is_active": True}


# ---------------------------------------------------------------------------
# Read-only flag endpoints (S2-OPS-A-READ-ONLY-FLAG-ADMIN-API)
#
# Pattern: AC#4 mandates same-transaction audit (PR #238 套路 `view_prep_package`)
# rather than independent-session audit (PR #250 `cache-invalidate` 套路).
# Successful 200 writes both ``users.read_only_*`` columns and the
# ``admin_audit_logs`` row in one ``session.flush()``; failures (404/422/500)
# rollback both, leaving no orphan audit. ADR-0053 §7 accepts this.
# ---------------------------------------------------------------------------


def _read_only_response(user: User) -> dict:
    """AC#1/AC#2 shape: never includes ``reason_detail`` (PRD-001 §F8 D1)."""
    return {
        "user_id": str(user.id),
        "is_read_only": user.is_read_only,
        "reason_category": user.read_only_reason_category,
        "read_only_set_at": (user.read_only_set_at.isoformat() if user.read_only_set_at else None),
        "read_only_set_by": user.read_only_set_by,
    }


def _apply_set_read_only(
    user: User,
    *,
    body: SetReadOnlyBody,
    admin_user_id: int | None,
) -> None:
    """Mutate user columns for ``is_read_only=True``; helper for batch reuse."""
    user.is_read_only = True
    user.read_only_reason_category = body.reason_category
    user.read_only_reason_detail = body.reason_detail
    user.read_only_set_at = datetime.now(timezone.utc)
    # AC#5: read_only_set_by FK only populated under JWT path; legacy
    # X-Admin-Token has no real AdminUser.id to attribute. ADR-0053 §5.1.
    user.read_only_set_by = admin_user_id


def _apply_unset_read_only(user: User) -> None:
    """Mutate user columns for ``is_read_only=False`` + clear metadata."""
    user.is_read_only = False
    user.read_only_reason_category = None
    user.read_only_reason_detail = None
    user.read_only_set_at = None
    user.read_only_set_by = None


@router.post(
    "/{user_id}/read-only",
    response_model=ReadOnlyStateResponse,
    summary="后台：将用户置为只读 (read-only)",
    description=(
        "ADR-0053 §7. 复用 PR #238 同事务 AdminAuditLog 路径 — 成功 200 时写 audit;"
        " 失败 404/422 因事务回滚不留 audit。reason_detail 仅 audit 留存,"
        " response 永远不返 (PRD-001 §F8 D1)。"
    ),
)
async def set_user_read_only(
    user_id: UUID,
    body: SetReadOnlyBody,
    session: DBSession,
    principal=Depends(require_admin),
    operator: str = Depends(admin_operator_id),
):
    repo = UserRepository(session)
    user = await repo.get_by_id(user_id)
    if user is None:
        raise NotFoundException("User not found")

    admin_user_id = principal.id if isinstance(principal, AdminUser) else None
    _apply_set_read_only(user, body=body, admin_user_id=admin_user_id)
    _audit(
        session,
        target_type="user",
        target_id=user_id,
        action="set_read_only",
        operator=operator,
        # AC#4: full audit string — operator can grep historically.
        reason=(f"category={body.reason_category} detail={body.reason_detail or ''}"),
    )
    await session.flush()
    return _read_only_response(user)


@router.delete(
    "/{user_id}/read-only",
    response_model=ReadOnlyStateResponse,
    summary="后台：解除用户只读 (unset read-only)",
    description=(
        "ADR-0053 §7. 清除 is_read_only + 4 列元数据，复用 PR #238 同事务" " AdminAuditLog 路径。"
    ),
)
async def unset_user_read_only(
    user_id: UUID,
    session: DBSession,
    operator: str = Depends(admin_operator_id),
):
    repo = UserRepository(session)
    user = await repo.get_by_id(user_id)
    if user is None:
        raise NotFoundException("User not found")

    _apply_unset_read_only(user)
    _audit(
        session,
        target_type="user",
        target_id=user_id,
        action="unset_read_only",
        operator=operator,
    )
    await session.flush()
    return _read_only_response(user)


@router.post(
    "/batch-read-only",
    response_model=BatchReadOnlyResponse,
    summary="后台：批量设置/解除只读 (≤100)",
    description=(
        "ADR-0053 §7 批量上限 100。每个 user_id 独立成功/失败,"
        " 单 user 404 不阻整批; 全批同一事务 commit (要么 100 个 audit + 100 个"
        " user 行 update 同时落, 要么全回滚)。批 >100 → 422 BATCH_TOO_LARGE。"
    ),
)
async def batch_set_read_only(
    body: BatchReadOnlyBody,
    session: DBSession,
    principal=Depends(require_admin),
    operator: str = Depends(admin_operator_id),
):
    if len(body.user_ids) > BATCH_MAX:
        # AC#3: returned as 422 (FastAPI default for body validation) is
        # acceptable; we wrap it explicitly to give a stable ``error_code``
        # for client retry logic. Using ``NotFoundException`` would be wrong
        # (404 implies missing resource). Raise pydantic-style for parity
        # with other body validators.
        from fastapi import HTTPException

        raise HTTPException(
            status_code=422,
            detail={
                "error_code": "BATCH_TOO_LARGE",
                "message": (f"batch size {len(body.user_ids)} exceeds limit {BATCH_MAX}"),
            },
        )

    repo = UserRepository(session)
    admin_user_id = principal.id if isinstance(principal, AdminUser) else None
    results: list[dict] = []
    succeeded = 0
    failed = 0

    # ``SetReadOnlyBody`` reuse keeps the same defaulting behavior as the
    # single endpoint (category/detail apply identically per user).
    per_user_body = SetReadOnlyBody(
        is_read_only=body.is_read_only,
        reason_category=body.reason_category,
        reason_detail=body.reason_detail,
    )

    for user_id in body.user_ids:
        user = await repo.get_by_id(user_id)
        if user is None:
            results.append(
                {
                    "user_id": str(user_id),
                    "is_read_only": None,
                    "error": "USER_NOT_FOUND",
                }
            )
            failed += 1
            continue

        if body.is_read_only:
            _apply_set_read_only(user, body=per_user_body, admin_user_id=admin_user_id)
            action = "set_read_only"
        else:
            _apply_unset_read_only(user)
            action = "unset_read_only"
        _audit(
            session,
            target_type="user",
            target_id=user_id,
            action=action,
            operator=operator,
            reason=(f"batch category={body.reason_category}" f" detail={body.reason_detail or ''}"),
        )
        results.append(
            {
                "user_id": str(user_id),
                "is_read_only": user.is_read_only,
                "error": None,
            }
        )
        succeeded += 1

    await session.flush()
    return {
        "requested": len(body.user_ids),
        "succeeded": succeeded,
        "failed": failed,
        "results": results,
    }
