"""
Token-based admin authentication.

Reads ADMIN_API_TOKEN from env (default "dev-admin-token" in dev).
Endpoints use ``Depends(require_admin_token)`` with header ``X-Admin-Token``.

TODO: replace with OAuth2/JWT admin login in a future sprint.
"""

from fastapi import Header

from app.config import settings
from app.exceptions import UnauthorizedException


async def require_admin_token(
    x_admin_token: str = Header(..., alias="X-Admin-Token"),
) -> str:
    """Validate the admin API token from request header."""
    if x_admin_token != settings.admin_api_token:
        raise UnauthorizedException("Invalid admin token")
    return x_admin_token
