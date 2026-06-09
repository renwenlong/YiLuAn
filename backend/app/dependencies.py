from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.admin_jwt import require_admin_jwt
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

    if payload.get("type") != "access":
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
    """Require that the JWT-authenticated user has the ``patient`` role."""
    if current_user.role == UserRole.patient:
        return current_user
    if current_user.has_role(UserRole.patient):
        return current_user
    raise ForbiddenException("patient role required")


CurrentPatient = Annotated[User, Depends(get_current_patient)]


async def get_current_companion(
    current_user: CurrentUser,
) -> User:
    """Require that the JWT-authenticated user has the ``companion`` role.

    Returns the same ``User`` row that ``get_current_user`` returned,
    after asserting either:

    - ``user.role == UserRole.companion`` (legacy single-role enum), or
    - ``user.has_role(UserRole.companion)`` (newer multi-role string).

    Both are checked so we don't get tripped up by ongoing role-model
    migrations.

    Raises ``ForbiddenException`` (403) on role mismatch — not
    ``UnauthorizedException`` (401), because the token IS valid; the
    caller simply isn't permitted at this endpoint.
    """
    if current_user.role == UserRole.companion:
        return current_user
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
