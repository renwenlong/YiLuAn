"""Apple Sign-In endpoint and identity-token verifier.

This module implements the backend half of "Sign in with Apple":

  POST /api/v1/auth/apple/login
       { identity_token, authorization_code, user_info? }

It validates the JWT issued by Apple (iss/aud/exp/sub), then delegates
to ``AuthService.login_or_register_by_apple_sub`` to issue our own
JWT/refresh-token pair (reusing the existing token plumbing).

Signature verification uses Apple's JWKS endpoint
(https://appleid.apple.com/auth/keys). In dev/test we set
``APPLE_MOCK_VERIFY=1`` (or ``settings.apple_mock_verify=True``) which
skips the cryptographic step but still fully validates claims
(iss / aud / exp / nonce-shape / sub-presence). Tests monkeypatch the
JWKS fetcher so they never hit appleid.apple.com.

[W18-A]
"""
from __future__ import annotations

import time
from typing import Any

import httpx
from fastapi import APIRouter, Request
from jose import jwt
from jose.exceptions import ExpiredSignatureError, JWTError
from pydantic import BaseModel, Field

from app.config import settings
from app.dependencies import DBSession
from app.exceptions import UnauthorizedException
from app.schemas.auth import TokenResponse
from app.services.auth import AuthService


router = APIRouter(prefix="/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class AppleUserInfo(BaseModel):
    """Optional profile bundle Apple returns ONLY on the first sign-in."""

    email: str | None = None
    first_name: str | None = None
    last_name: str | None = None


class AppleLoginRequest(BaseModel):
    identity_token: str = Field(..., min_length=1, description="Apple JWT (id_token)")
    authorization_code: str = Field(
        ..., min_length=1, description="Apple authorization code (server-to-server use)"
    )
    user_info: AppleUserInfo | None = Field(
        default=None,
        description="Optional profile (only present on first authorization).",
    )


# ---------------------------------------------------------------------------
# JWKS fetcher (overridable via monkeypatch in tests)
# ---------------------------------------------------------------------------
async def fetch_apple_jwks() -> dict[str, Any]:
    """Fetch Apple's public JWKS document.

    Tests monkeypatch this function so they never hit the real network.
    """
    async with httpx.AsyncClient(timeout=5.0) as http:
        resp = await http.get(settings.apple_jwks_url)
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# Token verification
# ---------------------------------------------------------------------------
async def verify_apple_identity_token(identity_token: str) -> dict[str, Any]:
    """Validate an Apple identity token and return its claims.

    Raises :class:`UnauthorizedException` (with a stable error_code) on any
    structural / claim / signature problem.
    """
    expected_iss = settings.apple_issuer
    expected_aud = settings.apple_client_id or None  # may be empty in dev

    # ---- 1. Parse header / claims (no verification yet) -------------------
    try:
        unverified_header = jwt.get_unverified_header(identity_token)
        unverified_claims = jwt.get_unverified_claims(identity_token)
    except JWTError as e:
        raise UnauthorizedException(
            f"Malformed Apple identity token: {e}",
            error_code="INVALID_APPLE_TOKEN",
        )

    # ---- 2. Mock mode: validate claims only, skip signature ---------------
    if settings.apple_mock_verify:
        return _validate_apple_claims(unverified_claims, expected_iss, expected_aud)

    # ---- 3. Real mode: pull JWKS, verify signature ------------------------
    kid = unverified_header.get("kid")
    alg = unverified_header.get("alg", "RS256")
    if not kid:
        raise UnauthorizedException(
            "Apple token missing 'kid' header",
            error_code="INVALID_APPLE_TOKEN",
        )

    try:
        jwks = await fetch_apple_jwks()
    except httpx.HTTPError as e:
        # Treat upstream JWKS failure as token-invalid (don't 5xx the client).
        raise UnauthorizedException(
            f"Unable to fetch Apple JWKS: {e}",
            error_code="INVALID_APPLE_TOKEN",
        )

    matching_key = next(
        (k for k in jwks.get("keys", []) if k.get("kid") == kid), None
    )
    if matching_key is None:
        raise UnauthorizedException(
            "Apple token signed with unknown key id",
            error_code="INVALID_APPLE_TOKEN",
        )

    try:
        claims = jwt.decode(
            identity_token,
            matching_key,
            algorithms=[alg],
            audience=expected_aud,
            issuer=expected_iss,
        )
    except ExpiredSignatureError:
        raise UnauthorizedException(
            "Apple identity token expired",
            error_code="APPLE_TOKEN_EXPIRED",
        )
    except JWTError as e:
        raise UnauthorizedException(
            f"Invalid Apple identity token: {e}",
            error_code="INVALID_APPLE_TOKEN",
        )

    # `python-jose` already enforced iss/aud/exp; double-check `sub`.
    if not claims.get("sub"):
        raise UnauthorizedException(
            "Apple token missing 'sub' claim",
            error_code="INVALID_APPLE_TOKEN",
        )
    return claims


def _validate_apple_claims(
    claims: dict[str, Any], expected_iss: str, expected_aud: str | None
) -> dict[str, Any]:
    """Mock-mode claim validation (no crypto). Mirrors what jwt.decode would enforce."""
    iss = claims.get("iss")
    if iss != expected_iss:
        raise UnauthorizedException(
            f"Invalid Apple token issuer: {iss!r}",
            error_code="INVALID_APPLE_TOKEN",
        )

    if expected_aud is not None:
        aud = claims.get("aud")
        # `aud` may be string or list per JWT spec.
        aud_values = aud if isinstance(aud, (list, tuple)) else [aud]
        if expected_aud not in aud_values:
            raise UnauthorizedException(
                "Invalid Apple token audience",
                error_code="INVALID_APPLE_TOKEN",
            )

    exp = claims.get("exp")
    if exp is None:
        raise UnauthorizedException(
            "Apple token missing 'exp' claim",
            error_code="INVALID_APPLE_TOKEN",
        )
    try:
        exp_int = int(exp)
    except (TypeError, ValueError):
        raise UnauthorizedException(
            "Apple token has malformed 'exp' claim",
            error_code="INVALID_APPLE_TOKEN",
        )
    if exp_int < int(time.time()):
        raise UnauthorizedException(
            "Apple identity token expired",
            error_code="APPLE_TOKEN_EXPIRED",
        )

    if not claims.get("sub"):
        raise UnauthorizedException(
            "Apple token missing 'sub' claim",
            error_code="INVALID_APPLE_TOKEN",
        )

    # `nonce` is optional; if present it must be a string. Replay protection
    # is the client's responsibility (compare against locally stored nonce).
    nonce = claims.get("nonce")
    if nonce is not None and not isinstance(nonce, str):
        raise UnauthorizedException(
            "Apple token has malformed 'nonce' claim",
            error_code="INVALID_APPLE_TOKEN",
        )

    return claims


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------
@router.post(
    "/apple/login",
    response_model=TokenResponse,
    summary="Apple Sign-In 登录",
    description=(
        "使用 Apple 颁发的 identity_token 完成登录/首次注册。"
        "返回标准 access_token / refresh_token，复用现有 JWT 流。"
    ),
)
async def apple_login(
    body: AppleLoginRequest, request: Request, session: DBSession
) -> TokenResponse:
    claims = await verify_apple_identity_token(body.identity_token)
    apple_sub = claims["sub"]

    # Prefer email from the (one-shot) user_info bundle; fall back to JWT.
    email: str | None = None
    if body.user_info is not None:
        email = body.user_info.email
    if email is None:
        email = claims.get("email")

    service = AuthService(session, request.app.state.redis)
    return await service.login_or_register_by_apple_sub(apple_sub, email=email)
