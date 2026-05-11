"""
Admin Companions Audit — business logic (B1).

Routes: /api/v1/admin/companions
Auth: X-Admin-Token header (token-based, TODO: migrate to OAuth/JWT)
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_, select

from app.core.admin_auth import require_admin_token  # noqa: F401  (legacy import retained for downstream consumers)
from app.core.admin_jwt import admin_operator_id, require_admin
from app.core.pii import mask_id_number
from app.dependencies import DBSession
from app.models.admin_audit_log import AdminAuditLog
from app.models.companion_profile import CompanionProfile, VerificationStatus
from app.models.user import User
from app.schemas.companion import CertifyCompanionRequest, CompanionDetailResponse
from app.services.admin_audit import AdminAuditService

router = APIRouter(
    prefix="/companions",
    tags=["admin-companions"],
    dependencies=[Depends(require_admin)],
)


# Sentinel used for list-scoped audit rows (no single target).
_LIST_TARGET = UUID("00000000-0000-0000-0000-000000000000")


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


class CompanionSearchItem(BaseModel):
    user_id: str = Field(..., description="陪诊师对应的用户 ID（用于钱包账本筛选）")
    profile_id: str = Field(..., description="陪诊师档案 ID")
    name: str = Field(..., description="姓名")
    phone_last4: str | None = Field(None, description="手机号后 4 位")


class CompanionSearchResponse(BaseModel):
    items: list[CompanionSearchItem] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


def _mask_companion_item(item: dict) -> dict:
    """Apply id_number masking on a service-returned companion dict."""
    raw = item.get("id_number")
    if raw:
        item = {**item, "id_number": mask_id_number(raw)}
    return item


@router.get(
    "/",
    response_model=PaginatedCompanions,
    summary="后台：待审核陪诊师列表",
    description="分页返回提交了入驻申请、状态为 `pending` 的陪诊师。请求头需携带 `X-Admin-Token`。",
)
async def list_pending_companions(
    session: DBSession,
    operator: str = Depends(admin_operator_id),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List companions pending audit. id_number is masked on the wire."""
    svc = AdminAuditService(session)
    result = await svc.list_pending_companions(page=page, page_size=page_size)
    items = result.get("items") or []
    masked = [_mask_companion_item(it) for it in items]

    summary = (
        f"page={page} limit={page_size} returned={len(masked)} status=pending"
    )
    session.add(
        AdminAuditLog(
            target_type="companion",
            target_id=_LIST_TARGET,
            action="view_companions_list",
            operator=operator,
            reason=summary,
        )
    )
    await session.flush()

    return {**result, "items": masked}


@router.post(
    "/{companion_id}/approve",
    response_model=OkResponse,
    summary="后台：批准陪诊师入驻",
    description="批准指定陪诊师，状态转为 `verified`，该陪诊师随即可被搜索与接单。",
)
async def approve_companion(
    companion_id: UUID,
    session: DBSession,
    operator: str = Depends(admin_operator_id),
):
    """Approve a companion."""
    svc = AdminAuditService(session)
    await svc.approve_companion(companion_id, operator_id=operator)
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
    operator: str = Depends(admin_operator_id),
):
    """Reject a companion with reason."""
    svc = AdminAuditService(session)
    await svc.reject_companion(companion_id, operator_id=operator, reason=body.reason)
    return OkResponse()


@router.get(
    "/search",
    response_model=CompanionSearchResponse,
    summary="后台：陪诊师轻量搜索（钱包账本筛选用）",
    description=(
        "按姓名或手机号模糊搜索陪诊师，返回 user_id + 姓名 + 手机号尾 4 位。"
        "默认仅返回 `verified` 状态；传 `status=all` 取消该过滤。"
    ),
)
async def search_companions(
    session: DBSession,
    q: str | None = Query(None, description="姓名或手机号关键字"),
    status: str = Query("verified", description="verified | all"),
    limit: int = Query(20, ge=1, le=50),
):
    stmt = (
        select(CompanionProfile, User)
        .join(User, User.id == CompanionProfile.user_id)
    )
    if status != "all":
        stmt = stmt.where(
            CompanionProfile.verification_status == VerificationStatus.verified
        )
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(CompanionProfile.real_name.ilike(like), User.phone.ilike(like)))
    stmt = stmt.order_by(CompanionProfile.created_at.desc()).limit(limit)

    rows = (await session.execute(stmt)).all()
    items: list[CompanionSearchItem] = []
    for profile, user in rows:
        phone = user.phone or ""
        items.append(
            CompanionSearchItem(
                user_id=str(profile.user_id),
                profile_id=str(profile.id),
                name=profile.real_name,
                phone_last4=phone[-4:] if len(phone) >= 4 else (phone or None),
            )
        )
    return CompanionSearchResponse(items=items)


@router.post(
    "/{companion_id}/certify",
    response_model=CompanionDetailResponse,
    summary="管理员：设置陪诊师资质认证（F-01）",
    description="设置认证类型/证书编号/证书图片并戳记 certified_at；写入 admin_audit_log。",
)
async def certify_companion(
    companion_id: UUID,
    body: CertifyCompanionRequest,
    session: DBSession,
    operator: str = Depends(admin_operator_id),
):
    svc = AdminAuditService(session)
    profile = await svc.certify_companion(
        companion_id,
        operator_id=operator,
        certification_type=body.certification_type,
        certification_no=body.certification_no,
        certification_image_url=body.certification_image_url,
    )
    return profile
