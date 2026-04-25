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
    id: str = Field(..., description="陪诊师 ID", examples=["3fa85f64-5717-4562-b3fc-2c963f66afa6"])
    real_name: str = Field(..., description="真实姓名", examples=["张三"])
    id_number: str | None = Field(None, description="身份证号（脱敏）", examples=["110101********1234"])
    certifications: str | None = Field(None, description="持证信息串", examples=["护士资格证"])
    created_at: str | None = Field(None, description="创建时间 ISO8601", examples=["2026-04-24T10:00:00+08:00"])


class PaginatedCompanions(BaseModel):
    items: list[CompanionItem] = Field(default_factory=list, description="当页陪诊师列表")
    total: int = Field(0, description="总条数")
    page: int = Field(1, description="当前页码")
    page_size: int = Field(20, description="页大小")


class RejectBody(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500, description="驳回原因", examples=["资质证明不清晰"])


class OkResponse(BaseModel):
    ok: bool = Field(True, description="是否成功")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/",
    response_model=PaginatedCompanions,
    summary="后台：待审核陪诊师列表",
    description="分页返回提交了入驻申请、状态为 `pending` 的陪诊师。请求头需携带 `X-Admin-Token`。",
)
async def list_pending_companions(
    session: DBSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List companions pending audit."""
    svc = AdminAuditService(session)
    return await svc.list_pending_companions(page=page, page_size=page_size)


@router.post(
    "/{companion_id}/approve",
    response_model=OkResponse,
    summary="后台：批准陪诊师入驻",
    description="批准指定陪诊师，状态转为 `verified`，该陪诊师随即可被搜索与接单。",
)
async def approve_companion(
    companion_id: UUID,
    session: DBSession,
):
    """Approve a companion."""
    svc = AdminAuditService(session)
    await svc.approve_companion(companion_id, operator_id="admin-token")
    return OkResponse()


@router.post(
    "/{companion_id}/reject",
    response_model=OkResponse,
    summary="后台：驳回陪诊师申请",
    description="驳回指定陪诊师的入驻申请并写入原因（1~500 字）。",
)
async def reject_companion(
    companion_id: UUID,
    body: RejectBody,
    session: DBSession,
):
    """Reject a companion with reason."""
    svc = AdminAuditService(session)
    await svc.reject_companion(companion_id, operator_id="admin-token", reason=body.reason)
    return OkResponse()
