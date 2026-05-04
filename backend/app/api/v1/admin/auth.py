"""Admin v2 login endpoint (B3 / ADR-0034).

``POST /api/v1/admin/login`` exchanges username + password for an 8h
JWT. The route lives at the admin router root (``/api/v1/admin/login``)
so it can be reached without any prior auth header.
"""

from datetime import datetime, timezone

import bcrypt
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.admin_jwt import ADMIN_TOKEN_TTL, create_admin_access_token
from app.database import get_db
from app.exceptions import ForbiddenException, UnauthorizedException
from app.models.admin_user import AdminUser

router = APIRouter(tags=["admin-auth"])


class AdminLoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)


class AdminLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds
    role: str
    username: str


def _verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


@router.post(
    "/login",
    response_model=AdminLoginResponse,
    summary="Admin v2 登录（JWT）",
    description=(
        "校验 `admin_users.username` + bcrypt 密码，签发 8h JWT。"
        "Token 用 `Authorization: Bearer <token>` 传递。"
        "见 ADR-0034。"
    ),
)
async def admin_login(
    body: AdminLoginRequest,
    session: AsyncSession = Depends(get_db),
) -> AdminLoginResponse:
    stmt = select(AdminUser).where(AdminUser.username == body.username)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    # Always validate password even if user is None to keep timing similar.
    valid = user is not None and _verify_password(body.password, user.password_hash)
    if not user or not valid:
        raise UnauthorizedException("invalid credentials")
    if not user.is_active:
        raise ForbiddenException("admin account disabled")

    user.last_login_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(user)

    token = create_admin_access_token(user)
    return AdminLoginResponse(
        access_token=token,
        token_type="bearer",
        expires_in=int(ADMIN_TOKEN_TTL.total_seconds()),
        role=user.role.value,
        username=user.username,
    )
