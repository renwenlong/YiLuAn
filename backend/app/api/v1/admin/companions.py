"""
Admin Companions Audit — MVP scaffold (A6).

Routes: /api/v1/admin/companions
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.api.v1.admin import AdminUser
from app.dependencies import DBSession
from app.models.user import User

router = APIRouter(prefix="/companions", tags=["admin-companions"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class PaginatedCompanions(BaseModel):
    items: list = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20


class RejectBody(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)


class OkResponse(BaseModel):
    ok: bool = True


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/", response_model=PaginatedCompanions)
async def list_pending_companions(
    session: DBSession,
    _admin: User = Depends(AdminUser),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List companions pending audit. TODO: wire to AdminAuditService."""
    # TODO: call AdminAuditService.list_pending_companions
    return PaginatedCompanions(items=[], total=0, page=page, page_size=page_size)


@router.post("/{companion_id}/approve", response_model=OkResponse)
async def approve_companion(
    companion_id: UUID,
    session: DBSession,
    _admin: User = Depends(AdminUser),
):
    """Approve a companion. TODO: wire to AdminAuditService."""
    # TODO: call AdminAuditService.approve_companion
    return OkResponse()


@router.post("/{companion_id}/reject", response_model=OkResponse)
async def reject_companion(
    companion_id: UUID,
    body: RejectBody,
    session: DBSession,
    _admin: User = Depends(AdminUser),
):
    """Reject a companion with reason. TODO: wire to AdminAuditService."""
    # TODO: call AdminAuditService.reject_companion
    return OkResponse()
