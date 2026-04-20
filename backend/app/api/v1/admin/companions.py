"""
Admin Companions Audit — business logic (B1).

Routes: /api/v1/admin/companions
Auth: X-Admin-Token header (token-based, TODO: migrate to OAuth/JWT)
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.core.admin_auth import require_admin_token
from app.dependencies import DBSession
from app.services.admin_audit import AdminAuditService

router = APIRouter(
    prefix="/companions",
    tags=["admin-companions"],
    dependencies=[Depends(require_admin_token)],
)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class CompanionItem(BaseModel):
    id: str
    real_name: str
    id_number: str | None = None
    certifications: str | None = None
    created_at: str | None = None


class PaginatedCompanions(BaseModel):
    items: list[CompanionItem] = Field(default_factory=list)
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
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List companions pending audit."""
    svc = AdminAuditService(session)
    return await svc.list_pending_companions(page=page, page_size=page_size)


@router.post("/{companion_id}/approve", response_model=OkResponse)
async def approve_companion(
    companion_id: UUID,
    session: DBSession,
):
    """Approve a companion."""
    svc = AdminAuditService(session)
    await svc.approve_companion(companion_id, operator_id="admin-token")
    return OkResponse()


@router.post("/{companion_id}/reject", response_model=OkResponse)
async def reject_companion(
    companion_id: UUID,
    body: RejectBody,
    session: DBSession,
):
    """Reject a companion with reason."""
    svc = AdminAuditService(session)
    await svc.reject_companion(companion_id, operator_id="admin-token", reason=body.reason)
    return OkResponse()
