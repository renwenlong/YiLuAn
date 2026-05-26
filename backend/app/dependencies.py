from typing import Annotated
from uuid import UUID

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.database import get_db
from app.exceptions import UnauthorizedException
from app.models.user import User
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
