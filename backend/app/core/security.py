import uuid
from datetime import datetime, timedelta, timezone

import jwt
from jwt import PyJWTError

from app.config import settings


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.jwt_access_token_expire_minutes)
    )
    to_encode.update({"exp": expire, "type": "access"})
    # ``v`` (token_version) is the per-user revocation cursor; callers MUST
    # pass it via ``data``. We don't default it here so a forgotten caller
    # blows up loudly in tests instead of silently minting un-revocable
    # tokens.
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(data: dict, jti: str | None = None) -> str:
    """Issue a refresh JWT with a unique ``jti`` claim.

    The ``jti`` is required to support server-side rotation / revocation via
    Redis (see ``app.services.refresh_tokens.RefreshTokenStore``). If callers
    don't pass one, we generate a fresh uuid4.
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_token_expire_days)
    if jti is None:
        jti = uuid.uuid4().hex
    to_encode.update({"exp": expire, "type": "refresh", "jti": jti})
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        return payload
    except PyJWTError:
        return None
