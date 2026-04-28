"""
Token-based admin authentication.

Reads ADMIN_API_TOKEN from env (default "dev-admin-token" in dev).
Endpoints use ``Depends(require_admin_token)`` with header ``X-Admin-Token``.

For flows that require **operator identity** (e.g. recon double-sign close,
ADR-0032 / D-048), use ``Depends(require_admin_operator)`` which additionally
reads the ``X-Admin-Operator`` header (1-64 chars, free-form). Until OAuth is
in place this is the auditable identity dimension.

TODO: replace with OAuth2/JWT admin login in a future sprint.
"""

from fastapi import Header

from app.config import settings
from app.exceptions import BadRequestException, UnauthorizedException


async def require_admin_token(
    x_admin_token: str = Header(..., alias="X-Admin-Token"),
) -> str:
    """Validate the admin API token from request header."""
    if x_admin_token != settings.admin_api_token:
        raise UnauthorizedException("Invalid admin token")
    return x_admin_token


async def require_admin_operator(
    x_admin_token: str = Header(..., alias="X-Admin-Token"),
    x_admin_operator: str = Header(..., alias="X-Admin-Operator"),
) -> str:
    """Validate token + return the operator identity string.

    The operator is a free-form 1-64 char identifier provided by the admin H5;
    it lands in ``admin_audit_logs.operator`` and ``reconciliation_actions.payload``
    so the double-sign close (D-048) can compare "different admin".
    """
    if x_admin_token != settings.admin_api_token:
        raise UnauthorizedException("Invalid admin token")
    op = (x_admin_operator or "").strip()
    if not op or len(op) > 64:
        raise BadRequestException("X-Admin-Operator header required (1-64 chars)")
    return op
