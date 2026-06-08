"""User-facing contracts API (S3-DEV-001-CONTRACT-API).

ADR-0047 §6.2 + §6.3:
- POST /api/v1/contracts/{contract_id}/accept — 用户勾选合同同意, 写
  user_audit_logs.contract_acceptance_clicked
- GET /api/v1/contracts/{contract_id} — 用户查看合同 PDF, 返 signed URL
  (TTL=15min, ViewerRole.USER), 同时写 user_audit_logs.contract_viewed

# 鉴权
所有端点要求 CurrentUser (登录用户), 且 contract 必须属于该 user
(``ServiceContract.order.patient_id == current_user.id``)。
non-owner 一律 404 (不暴露 contract 存在性, 防 IDOR 探测).

# 审计
- accept: 写 user_audit_logs.contract_acceptance_clicked + UA/IP + template_version
- view: 写 user_audit_logs.contract_viewed + UA/IP
- admin 操作走 ../admin/contracts.py (不入此模块)

# 限流
30/minute per user (与 orders.py create_order 同档位)。
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.api.v1.openapi_meta import err
from app.core.rate_limit import limiter
from app.dependencies import CurrentUser, DBSession
from app.models.order import Order
from app.models.service_contract import ContractStatus, ServiceContract
from app.schemas.contract_api import (
    ContractAcceptanceRequest,
    ContractAcceptanceResponse,
    ContractDetailResponse,
)
from app.services.contract_storage import ViewerRole, get_contract_signed_url
from app.services.user_audit import UserAuditService

router = APIRouter(prefix="/contracts", tags=["contracts"])


async def _load_user_contract(
    session: DBSession,
    contract_id: UUID,
    user_id: UUID,
) -> ServiceContract:
    """Load a contract that belongs to the given user, else 404.

    Returns 404 instead of 403 for non-owner to avoid leaking contract
    existence (IDOR 探测防御)。

    Two-step query (contract + order) instead of joinedload — ServiceContract
    未声明 ORM relationship 到 Order (避免循环 import), 手工 join
    cost 可忽 (两个 PK lookup)。
    """
    contract = await session.scalar(
        select(ServiceContract).where(ServiceContract.id == contract_id)
    )
    if contract is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="contract not found",
        )
    order = await session.scalar(
        select(Order).where(Order.id == contract.order_id)
    )
    if order is None or order.patient_id != user_id:
        # Non-owner: hide existence
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="contract not found",
        )
    return contract


@router.post(
    "/{contract_id}/accept",
    response_model=ContractAcceptanceResponse,
    status_code=200,
    summary="用户勾选合同同意 (AC#1)",
    description=(
        "用户在支付前勾选 '我已阅读并同意' checkbox 时调用。\n\n"
        "写 `user_audit_logs.contract_acceptance_clicked` 留痕 "
        "(含 user_agent + client_ip, PIPL/民法典电子合同取证). "
        "**幂等**: 同一用户重复 accept 同一 contract 会写多条 audit log "
        "(取证需要看到所有勾选时点), 但 contract 状态不变."
    ),
    responses={**err(401, 404, 422, 429, 500)},
)
@limiter.limit("30/minute")
async def accept_contract(
    request: Request,
    contract_id: UUID,
    body: ContractAcceptanceRequest,  # noqa: ARG001  reserved for future fields
    current_user: CurrentUser,
    session: DBSession,
) -> ContractAcceptanceResponse:
    contract = await _load_user_contract(session, contract_id, current_user.id)

    audit_service = UserAuditService(session)
    log = await audit_service.record_contract_acceptance_clicked(
        user_id=current_user.id,
        order_id=contract.order_id,
        request=request,
        template_version=contract.template_version,
    )
    await session.commit()
    return ContractAcceptanceResponse(
        contract_id=contract.id,
        order_id=contract.order_id,
        accepted_at=log.created_at,
        audit_log_id=log.id,
    )


@router.get(
    "/{contract_id}",
    response_model=ContractDetailResponse,
    summary="用户查看合同详情 + 签名 URL (AC#2)",
    description=(
        "返合同元信息 + ContractStorage 签名 URL (TTL=15min, ViewerRole.USER, "
        "ADR-0046 §3.1).\n\n"
        "`status != 'active'` (生成中 / 失败 / 作废) 时 signed_url 为 null, "
        "前端按 status 显示对应文案.\n\n"
        "写 `user_audit_logs.contract_viewed` 留痕 (PIPL 取证)."
    ),
    responses={**err(401, 404, 422, 429, 500)},
)
@limiter.limit("60/minute")
async def get_contract(
    request: Request,
    contract_id: UUID,
    current_user: CurrentUser,
    session: DBSession,
) -> ContractDetailResponse:
    contract = await _load_user_contract(session, contract_id, current_user.id)

    signed_url: str | None = None
    signed_url_expires_at: datetime | None = None
    if contract.status == ContractStatus.active and contract.storage_blob_path:
        signed = get_contract_signed_url(
            blob_path=contract.storage_blob_path,
            viewer_role=ViewerRole.USER,
        )
        signed_url = signed.url
        # ViewerRole.USER TTL = 15min (ADR-0046 §3.1)
        signed_url_expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)

    audit_service = UserAuditService(session)
    await audit_service.record_contract_viewed(
        user_id=current_user.id,
        order_id=contract.order_id,
        request=request,
    )
    await session.commit()

    return ContractDetailResponse(
        contract_id=contract.id,
        order_id=contract.order_id,
        template_version=contract.template_version,
        status=contract.status,
        signed_url=signed_url,
        signed_url_expires_at=signed_url_expires_at,
        generated_at=contract.generated_at,
    )
