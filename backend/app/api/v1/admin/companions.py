"""
Admin Companions Audit — business logic (B1).

Routes: /api/v1/admin/companions
Auth: X-Admin-Token header (token-based, TODO: migrate to OAuth/JWT)
"""

from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import or_, select

from app.core.admin_auth import (
    require_admin_token,  # noqa: F401  (legacy import retained for downstream consumers)
)
from app.core.admin_jwt import admin_operator_id, require_admin
from app.core.pii import mask_id_number, mask_phone
from app.dependencies import DBSession
from app.exceptions import NotFoundException
from app.models.admin_audit_log import AdminAuditLog
from app.models.companion_profile import CompanionProfile, VerificationStatus
from app.models.user import User
from app.schemas.companion import CertifyCompanionRequest, CompanionDetailResponse
from app.services.admin_audit import AdminAuditService
from app.services.certification_image import (
    content_type_for,
    save_certification_image,
    sign_certification_image_url,
    verify_signed_certification_image,
)

router = APIRouter(
    prefix="/companions",
    tags=["admin-companions"],
    dependencies=[Depends(require_admin)],
)

# Signed image reads are protected by HMAC+expires and must be usable as an
# <img src>. Browser image requests cannot attach X-Admin-Token, so this tiny
# router intentionally has no admin dependency.
public_certification_images_router = APIRouter(
    prefix="/companions",
    tags=["admin-companions"],
)


# Sentinel used for list-scoped audit rows (no single target).
_LIST_TARGET = UUID("00000000-0000-0000-0000-000000000000")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class CompanionItem(BaseModel):
    id: str = Field(
        ...,
        description="陪诊师 ID",
        examples=["3fa85f64-5717-4562-b3fc-2c963f66afa6"],
    )
    real_name: str = Field(..., description="真实姓名", examples=["张三"])
    id_number: str | None = Field(
        None,
        description="身份证号（脱敏）",
        examples=["110101********1234"],
    )
    certifications: str | None = Field(
        None,
        description="持证信息串",
        examples=["护士资格证"],
    )
    created_at: str | None = Field(
        None,
        description="创建时间 ISO8601",
        examples=["2026-04-24T10:00:00+08:00"],
    )


class CompanionDetail(BaseModel):
    """S2-DEV-013 PR-E1 (ADR-0044 §3.2)：admin 审核 drawer 用详情。

    与 list `CompanionItem` 重叠 5 字段（保证 frontend 不需两套 type）+ 新增 9 字段
    覆盖 admin 真审核场景。

    PR-E2 Phase A：`certification_image_signed_url` 对 `cert-image://` 本地私有证件图
    返回 15min HMAC signed URL；历史外部 URL 继续隐藏，留 Phase B storage 迁移。
    """

    # 与 list 重叠
    id: str = Field(..., description="陪诊师 ID")
    real_name: str = Field(..., description="真实姓名")
    id_number: str | None = Field(None, description="身份证号（脱敏）")
    certifications: str | None = Field(None, description="持证信息串")
    created_at: str | None = Field(None, description="创建时间 ISO8601")

    # 新增：审核必要字段
    bio: str | None = Field(None, description="陪诊师自述 / 申请理由")
    verification_status: str = Field(..., description="pending / verified / rejected")
    certified_at: str | None = Field(None, description="认证完成时间 ISO8601")

    # 证件三件
    certification_type: str | None = Field(None, description="证件类型")
    certification_no: str | None = Field(None, description="证件编号")
    certification_image_signed_url: str | None = Field(
        None,
        description=(
            "证件图 signed URL (TTL ≤ 15min)。PR-E2 Phase A 对 cert-image:// "
            "本地私有对象签名；历史外部 URL 返回 None。"
        ),
    )

    # 服务范围
    service_area: str | None = Field(None, description="服务区域")
    service_city: str | None = Field(None, description="服务城市")
    service_hospitals: str | None = Field(None, description="服务医院列表（逗号分隔串）")
    service_types: str | None = Field(None, description="服务类型列表（逗号分隔串）")

    # 历史指标
    avg_rating: float = Field(0.0, description="平均评分")
    total_orders: int = Field(0, description="总单量")

    # 关联用户 (PR-E3 补 reveal phone, 本 PR 仅返 masked)
    user_id: str | None = Field(None, description="关联 User.id（供 reveal phone 调用）")
    user_phone_masked: str | None = Field(
        None,
        description="脸主手机号脱敏。reveal 由独立端点 `/admin/users/{user_id}?reveal=true`",
    )


class PaginatedCompanions(BaseModel):
    items: list[CompanionItem] = Field(default_factory=list, description="当页陪诊师列表")
    total: int = Field(0, description="总条数")
    page: int = Field(1, description="当前页码")
    page_size: int = Field(20, description="页大小")


class RejectBody(BaseModel):
    reason: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="驳回原因",
        examples=["资质证明不清晰"],
    )


class OkResponse(BaseModel):
    ok: bool = Field(True, description="是否成功")


class CompanionSearchItem(BaseModel):
    user_id: str = Field(..., description="陪诊师对应的用户 ID（用于钱包账本筛选）")
    profile_id: str = Field(..., description="陪诊师档案 ID")
    name: str = Field(..., description="姓名")
    phone_last4: str | None = Field(None, description="手机号后 4 位")


class CompanionSearchResponse(BaseModel):
    items: list[CompanionSearchItem] = Field(default_factory=list)


class CertificationImageUploadResponse(BaseModel):
    certification_image_url: str = Field(
        ...,
        description="Phase A 本地私有存储标识；可传给 certify.certification_image_url",
        examples=["cert-image://d9f7c3b8a6f14f91a2b3c4d5e6f70819.jpg"],
    )
    certification_image_signed_url: str = Field(
        ...,
        description="TTL <= 15min 的相对 signed URL，供 admin-v2 上传后立即预览",
    )


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


# detail endpoint 移到 search endpoint 之后（避免 /search 被 /{companion_id} 错误匹配）


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
    "/certification-images",
    response_model=CertificationImageUploadResponse,
    summary="后台：上传陪诊师证件图（Phase A 本地私有存储）",
    description=(
        "仅 admin 可用。保存 jpg/jpeg/png/webp <= 5MB 到 backend 私有本地目录，"
        "返回可写入 certify.certification_image_url 的 cert-image:// 标识 + 15min signed URL。"
    ),
)
async def upload_certification_image(
    session: DBSession,
    file: UploadFile = File(...),
    operator: str = Depends(admin_operator_id),
):
    certification_image_url = await save_certification_image(file)
    signed_url = sign_certification_image_url(certification_image_url)

    session.add(
        AdminAuditLog(
            target_type="companion",
            target_id=_LIST_TARGET,
            action="upload_certification_image",
            operator=operator,
            reason="PR-E2 Phase A local certification image upload",
        )
    )
    await session.flush()

    return CertificationImageUploadResponse(
        certification_image_url=certification_image_url,
        certification_image_signed_url=signed_url or "",
    )


@public_certification_images_router.get(
    "/certification-images/{filename}",
    summary="后台：读取证件图 signed URL",
    description="校验 HMAC + expires 后返回本地私有证件图 bytes。",
)
async def get_certification_image(
    filename: str,
    expires: int,
    sig: str,
):
    path = verify_signed_certification_image(filename, expires, sig)
    return Response(content=path.read_bytes(), media_type=content_type_for(path))


# S2-DEV-013 PR-E1 detail endpoint (ADR-0044 §3.1)。
# 位置：必须在 /search 和 /certification-images/* (static path) 之后注册，否则
# /{companion_id} 会抢先匹配。FastAPI 路由按装饰器出现顺序匹配。
@router.get(
    "/{companion_id}",
    response_model=CompanionDetail,
    summary="后台：陪诊师审核详情",
    description=(
        "返回单个陪诊师 14 字段审核视图。`certification_image_signed_url` 对"
        " PR-E2 Phase A 本地 cert-image:// 对象返回 15min signed URL；历史外部 URL"
        " 返回 None，待 Phase B storage 迁移。reveal phone 走独立端点"
        " `GET /admin/users/{user_id}?reveal=true`。"
        " 写入 view_companion_detail 审计。"
    ),
)
async def get_companion_detail(
    companion_id: UUID,
    session: DBSession,
    operator: str = Depends(admin_operator_id),
):
    profile = await session.get(CompanionProfile, companion_id)
    if profile is None:
        raise NotFoundException("Companion not found")

    # 拉关联 user 取 phone。脱敏后不走这个 endpoint 的 reveal——
    # admin 需明文 phone 点 frontend reveal 按钮 调
    # `GET /admin/users/{user_id}?reveal=true` (独立审计 reveal_pii)
    user = await session.get(User, profile.user_id)
    user_phone_masked = mask_phone(user.phone) if user and user.phone else None

    # 审计留痕
    session.add(
        AdminAuditLog(
            target_type="companion",
            target_id=companion_id,
            action="view_companion_detail",
            operator=operator,
            reason="PR-E1 detail endpoint",
        )
    )
    await session.flush()

    return CompanionDetail(
        id=str(profile.id),
        real_name=profile.real_name,
        id_number=mask_id_number(profile.id_number) if profile.id_number else None,
        certifications=profile.certifications,
        created_at=profile.created_at.isoformat() if profile.created_at else None,
        bio=profile.bio,
        verification_status=profile.verification_status.value,
        certified_at=profile.certified_at.isoformat() if profile.certified_at else None,
        certification_type=profile.certification_type,
        certification_no=profile.certification_no,
        certification_image_signed_url=sign_certification_image_url(profile.certification_image_url),
        service_area=profile.service_area,
        service_city=profile.service_city,
        service_hospitals=profile.service_hospitals,
        service_types=profile.service_types,
        avg_rating=profile.avg_rating,
        total_orders=profile.total_orders,
        user_id=str(profile.user_id),
        user_phone_masked=user_phone_masked,
    )


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
