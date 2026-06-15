from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.admin_jwt import ADMIN_TOKEN_TYPE, require_admin_jwt
from app.core.security import decode_token
from app.database import get_db
from app.exceptions import ForbiddenException, UnauthorizedException
from app.models.admin_user import AdminUser
from app.models.user import User, UserRole
from app.repositories.user import UserRepository

DBSession = Annotated[AsyncSession, Depends(get_db)]

security_scheme = HTTPBearer()


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security_scheme)],
    session: DBSession,
) -> User:
    token = credentials.credentials
    payload = decode_token(token)
    if payload is None:
        raise UnauthorizedException("Invalid or expired token")

    token_type = payload.get("type")
    if token_type == ADMIN_TOKEN_TYPE:
        # Valid admin-issued JWT but used against a user-role endpoint.
        # Mirror the symmetry established by ``get_current_admin``:
        # auth OK, role-domain wrong -> 403, not 401. See PR #233
        # follow-up ("user/companion endpoint should 403 on admin token")
        # and ADR-0048 §7.0 strict-role design.
        raise ForbiddenException("user role required")
    if token_type != "access":
        raise UnauthorizedException("Invalid token type")

    user_id_str = payload.get("sub")
    if not user_id_str:
        raise UnauthorizedException("Invalid token: missing subject")

    try:
        user_id = UUID(user_id_str)
    except ValueError:
        raise UnauthorizedException("Invalid token: malformed subject")

    repo = UserRepository(session)
    user = await repo.get_by_id(user_id)
    if user is None:
        raise UnauthorizedException("User not found")
    if user.is_deleted:
        raise UnauthorizedException("Account has been deleted")
    if not user.is_active:
        raise UnauthorizedException("Account is disabled")
    # token_version revocation cursor. Tokens minted before this column
    # existed have no ``v`` claim (``token_v`` is None) — those predate the
    # rollout and were already gated by ``is_active`` / ``is_deleted``
    # checks above, so we accept them. Once a token *has* a ``v`` it must
    # match the user's current version; any logout-all / disable / delete
    # bumps the user counter and instantly invalidates them.
    token_v = payload.get("v")
    if token_v is not None and token_v != user.token_version:
        raise UnauthorizedException("Session revoked; please log in again")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


# -----------------------------------------------------------------------
# Read-only flag gate (ADR-0053 §5.2 / S2-DEV-016-READ-ONLY-FLAG-DB AC#3)
# -----------------------------------------------------------------------
#
# When ``users.is_read_only = TRUE`` we want every *mutating* endpoint
# (POST/PUT/PATCH/DELETE on business resources) to return 403 with the
# canonical UX shape from PRD-001 §F8 D2 (`error_code=USER_READONLY` +
# `reason_category` enum). GET endpoints stay unaffected — read-only
# means *no writes*, not *no access*.
#
# Implementation: reuse ``get_current_user`` (single DB query) and gate
# on the freshly loaded ``user.is_read_only`` flag. No extra round-trip.
#
# 403 shape (PRD-001 §F8 D2; frontend maps category → user-facing copy):
#
#     {
#       "detail": {
#         "error_code": "USER_READONLY",
#         "message": "Account is in read-only mode",
#         "reason_category": "GRAY_REVOKE" | "GRAY_ANOMALY" |
#                            "CREDENTIAL_LEAK" | "COMPLIANCE_REPORT" | null
#       }
#     }
#
# Backend deliberately does NOT expose the admin's free-text
# ``reason_detail`` (lives in ``admin_audit_logs.reason``); only the UX
# enum is returned so the frontend never leaks internal grey-list /
# compliance context to the user.
#
# IMPORTANT: GET endpoints must keep using ``CurrentUser`` so read-only
# users can still browse / inspect their own data. The E#9 lint gate
# (see backend/scripts/lint_writeable_user.py) enforces that every
# POST/PUT/PATCH/DELETE handler with a user-side identity dep uses
# ``WriteableUser`` instead of ``CurrentUser``.


async def require_writeable_user(
    current_user: CurrentUser,
) -> User:
    """Require ``users.is_read_only = FALSE``; otherwise 403 USER_READONLY.

    Sits on top of :func:`get_current_user` so the JWT check + user-row
    load happen exactly once per request; this dep only adds the boolean
    gate. Returns the same ``User`` row so the endpoint can use it
    interchangeably with the ``CurrentUser`` dep.
    """
    if current_user.is_read_only:
        # PRD-001 §F8 D2 canonical shape: backend never exposes the
        # admin's free-text ``reason_detail`` (lives in
        # ``admin_audit_logs.reason``); only the UX enum category goes to
        # the frontend so we don't leak grey-list / compliance context.
        # ForbiddenException only carries a single ``error_code``; the
        # 403 here also needs ``reason_category`` so we raise the raw
        # HTTPException with the full dict shape.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error_code": "USER_READONLY",
                "message": "Account is in read-only mode",
                "reason_category": current_user.read_only_reason_category,
            },
        )
    return current_user


#: Drop-in replacement for ``CurrentUser`` on mutating endpoints. Use
#: this on every business-write POST/PUT/PATCH/DELETE. Auth/recovery
#: paths (logout-all, bind-phone, etc.) stay on ``CurrentUser`` so a
#: read-only user can still log out / recover their account.
WriteableUser = Annotated[User, Depends(require_writeable_user)]


# -----------------------------------------------------------------------
# ABAC role-strict dependencies (ADR-0048 §7.0 / S3-DEV-002-ABAC-4LAYER)
# -----------------------------------------------------------------------
#
# The base ``get_current_user`` only verifies the JWT and that the user
# row exists / is active. It does **not** enforce role. For the AI prep
# package endpoints (PRD-003 §2.2, AC-6 PM P0 red line) we need strict
# role separation so that:
#
# - companion endpoints reject patient tokens (and vice versa) with 403
# - admin endpoints reject all non-admin tokens with 403
#
# These deps live here (not inline in routers) so they can be reused
# across the 3 prep-package routers + future role-scoped endpoints, and
# so the ABAC test suite can hit them directly.


async def get_current_patient(
    current_user: CurrentUser,
) -> User:
    """Require that the JWT-authenticated user has the ``patient`` role.

    ADR-0055: single SoT via ``has_role()``; the deprecated ``user.role``
    enum field is no longer read. Historical users with ``role=patient``
    but ``roles=NULL`` are covered by the backfill migration
    ``<auto>_backfill_roles_from_role.py`` (idempotent UPDATE).
    """
    if current_user.has_role(UserRole.patient):
        return current_user
    raise ForbiddenException("patient role required")


CurrentPatient = Annotated[User, Depends(get_current_patient)]


async def get_current_companion(
    current_user: CurrentUser,
) -> User:
    """Require that the JWT-authenticated user has the ``companion`` role.

    Returns the same ``User`` row that ``get_current_user`` returned,
    after asserting ``user.has_role(UserRole.companion)``.

    ADR-0055: single SoT via ``has_role()``; the deprecated ``user.role``
    enum field is no longer read. Historical users are covered by the
    backfill migration ``<auto>_backfill_roles_from_role.py`` (idempotent).

    Raises ``ForbiddenException`` (403) on role mismatch — not
    ``UnauthorizedException`` (401), because the token IS valid; the
    caller simply isn't permitted at this endpoint.
    """
    if current_user.has_role(UserRole.companion):
        return current_user
    raise ForbiddenException("companion role required")


CurrentCompanion = Annotated[User, Depends(get_current_companion)]


async def get_current_admin(
    session: DBSession,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> AdminUser:
    """Require a valid admin JWT (not a user token, not the legacy sentinel).

    A syntactically valid user-side access token is authenticated-but-not-
    authorized for admin prep-package routes, so it returns 403. Missing,
    malformed, expired, or otherwise invalid tokens remain 401.
    """
    try:
        return await require_admin_jwt(authorization=authorization, session=session)
    except UnauthorizedException as exc:
        if authorization and authorization.lower().startswith("bearer "):
            payload = decode_token(authorization.split(" ", 1)[1].strip())
            if payload and payload.get("type") == "access":
                raise ForbiddenException("admin role required") from exc
        raise


CurrentAdmin = Annotated[AdminUser, Depends(get_current_admin)]
