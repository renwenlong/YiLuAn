"""Admin v2 — JWT auth (B3 / B4 / ADR-0034).

Two pieces live here:

* ``create_admin_access_token`` / ``decode_admin_token`` — token helpers,
  signed with ``settings.jwt_secret_key`` and tagged ``type="admin_access"``
  to be unambiguously distinct from the user-side access tokens issued by
  :mod:`app.core.security`.
* ``require_admin_jwt`` — FastAPI dependency that resolves the bearer token
  to a live :class:`AdminUser` row.
* ``require_admin`` — **double-track** dependency for the W19 transition
  window. Returns either an ``AdminUser`` (when JWT is present) or the
  legacy sentinel string ``"admin-token"`` (when ``X-Admin-Token`` is
  used). Routers should switch to ``require_admin_jwt`` directly once the
  legacy path is retired (W20, see ADR-0034).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional, Union

import jwt
from fastapi import Depends, Header
from jwt import ExpiredSignatureError, PyJWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.admin_auth import require_admin_token
from app.database import get_db
from app.exceptions import UnauthorizedException
from app.models.admin_user import AdminUser

ADMIN_TOKEN_TYPE = "admin_access"
ADMIN_TOKEN_TTL = timedelta(hours=8)

# Sentinel returned by the double-track dependency when the caller used the
# legacy ``X-Admin-Token`` header. Matches the historical audit value so
# existing reports stay continuous during the transition window.
LEGACY_ADMIN_TOKEN_SENTINEL = "admin-token"


def create_admin_access_token(
    admin_user: AdminUser, *, expires_in: timedelta | None = None
) -> str:
    expire = datetime.now(timezone.utc) + (expires_in or ADMIN_TOKEN_TTL)
    payload = {
        "sub": str(admin_user.id),
        "role": admin_user.role.value,
        "username": admin_user.username,
        "type": ADMIN_TOKEN_TYPE,
        "exp": expire,
    }
    return jwt.encode(
        payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )


def decode_admin_token(token: str) -> dict:
    """Decode + validate. Raises ``UnauthorizedException`` on any failure."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except ExpiredSignatureError:
        raise UnauthorizedException("admin token expired")
    except PyJWTError:
        raise UnauthorizedException("invalid admin token")
    if payload.get("type") != ADMIN_TOKEN_TYPE:
        raise UnauthorizedException("invalid admin token type")
    return payload


async def _resolve_admin(
    authorization: Optional[str], session: AsyncSession
) -> AdminUser:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise UnauthorizedException("Bearer token required")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise UnauthorizedException("Bearer token required")
    payload = decode_admin_token(token)
    sub = payload.get("sub")
    if not sub:
        raise UnauthorizedException("invalid admin token: missing sub")
    try:
        admin_id = int(sub)
    except (TypeError, ValueError):
        raise UnauthorizedException("invalid admin token: bad sub")
    user = await session.get(AdminUser, admin_id)
    if user is None or not user.is_active:
        raise UnauthorizedException("admin account inactive or missing")
    return user


async def require_admin_jwt(
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
    session: AsyncSession = Depends(get_db),
) -> AdminUser:
    """Resolve a bearer JWT to an active ``AdminUser``."""
    return await _resolve_admin(authorization, session)


async def require_admin(
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
    x_admin_token: Optional[str] = Header(default=None, alias="X-Admin-Token"),
    session: AsyncSession = Depends(get_db),
) -> Union[AdminUser, str]:
    """Double-track: prefer JWT, fall back to legacy ``X-Admin-Token``.

    Returns the :class:`AdminUser` when JWT is used so routes can audit the
    real operator id; returns :data:`LEGACY_ADMIN_TOKEN_SENTINEL` when the
    caller is still on the old shared-token path.

    A user-side ``Authorization: Bearer ...`` (e.g. a patient access token)
    is **ignored** rather than rejected when ``X-Admin-Token`` is also
    provided — this preserves the existing pytest ``admin_client``
    fixture, which sends both headers, and keeps the door open for an
    in-app "sudo to admin" UX without breaking dual-auth shells.
    """
    if authorization and authorization.lower().startswith("bearer "):
        try:
            return await _resolve_admin(authorization, session)
        except UnauthorizedException:
            # Bearer token wasn't a valid admin JWT; fall through to legacy
            # header if present. Otherwise re-raise below.
            if x_admin_token is None:
                raise
    if x_admin_token is not None:
        # Delegate validation to the legacy helper (raises Unauthorized if
        # the token is wrong). It returns the token string itself; we map
        # that to the sentinel so audit rows keep their historical value.
        await require_admin_token(x_admin_token=x_admin_token)
        return LEGACY_ADMIN_TOKEN_SENTINEL
    raise UnauthorizedException(
        "admin auth required: provide Authorization: Bearer <jwt> or X-Admin-Token"
    )


async def admin_principal(
    principal: Union[AdminUser, str] = Depends(require_admin),
) -> Union[AdminUser, str]:
    """Alias of :func:`require_admin` exposed as a dependency that routes
    add explicitly so they can read the principal (e.g. for self-protection
    rules) without re-resolving the bearer token. FastAPI dependency cache
    deduplicates underlying header reads."""
    return principal


async def admin_operator_id(
    principal: Union[AdminUser, str] = Depends(require_admin),
) -> str:
    """Per-request operator id string suitable for ``AdminAuditLog.operator``.

    JWT principals → ``str(admin_user.id)``; legacy → ``"admin-token"``.
    """
    return operator_id_of(principal)


def operator_id_of(principal: Union[AdminUser, str]) -> str:
    """Map a :func:`require_admin` result to the audit ``operator`` value."""
    if isinstance(principal, AdminUser):
        return str(principal.id)
    return principal or LEGACY_ADMIN_TOKEN_SENTINEL


def is_jwt_principal(principal: Union[AdminUser, str]) -> bool:
    return isinstance(principal, AdminUser)
