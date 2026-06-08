"""Admin contracts API (S3-DEV-001-CONTRACT-API).

ADR-0047 §6.2 + §4: admin 客服作废合同端点。

# 唯一端点
POST /api/v1/admin/contracts/{contract_id}/invalidate
  body: {reason: string}

# 鉴权要求
- 必须 JWT principal (AdminUser); 拒绝 legacy X-Admin-Token sentinel。
  原因: invalidated_by_admin_id 是 BigInt FK 到 admin_users.id, legacy
  sentinel 没有 .id, 无法满足 service_contracts.invalidated_by_admin_id
  NOT NULL 约束 (assert_invalidation_metadata 强制)。
  实操: admin H5 必须登录获取 JWT, legacy CLI tool 不允许此操作。

# 审计
- 写 admin_audit_logs (target_type=service_contract, action=invalidate,
  operator=admin_user.id 字串, reason=请求 body.reason)
- 更新 service_contracts: status=manually_invalidated, invalidation_reason,
  invalidated_by_admin_id, invalidated_at
- ContractStateMachine.assert_transition 强制走合法 transition

# 不做
- 不删 blob (WORM 一旦写不可删)
- 不退款 (订单退款走 PaymentService, 独立流程)
"""


from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.api.v1.openapi_meta import err
from app.core.admin_jwt import require_admin
from app.dependencies import DBSession
from app.models.admin_audit_log import AdminAuditLog
from app.models.admin_user import AdminUser
from app.models.service_contract import ContractStatus, ServiceContract
from app.schemas.contract_api import (
    AdminContractInvalidateRequest,
    AdminContractInvalidateResponse,
)
from app.services.contract_state_machine import (
    ContractInvalidationMetadataMissingError,
    InvalidContractStateTransitionError,
    assert_invalidation_metadata,
    assert_transition,
)

router = APIRouter(prefix="/contracts", tags=["admin-contracts"])


def _require_jwt_admin(principal) -> AdminUser:
    """Reject legacy ``X-Admin-Token`` sentinel for invalidate (need .id).

    Invalidate writes ``service_contracts.invalidated_by_admin_id`` (BigInt FK
    to admin_users.id) + asserts NOT NULL via
    :func:`assert_invalidation_metadata`. Legacy ``LEGACY_ADMIN_TOKEN_SENTINEL``
    str has no .id, cannot satisfy the FK.

    Admin H5 已迁 JWT (W19+); 此端点是新加端点, 走 JWT-only 不破历史 caller.
    """
    if not isinstance(principal, AdminUser):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "contract invalidate requires admin JWT login "
                "(legacy X-Admin-Token not supported for this operation)"
            ),
        )
    return principal


@router.post(
    "/{contract_id}/invalidate",
    response_model=AdminContractInvalidateResponse,
    summary="admin 客服作废合同 (AC#3)",
    description=(
        "客服在用户申请作废合同 / 灰度回滚 / 误生成时使用。\n\n"
        "**必须** JWT admin 登录, 拒绝 legacy X-Admin-Token (需 admin_user.id).\n\n"
        "副作用:\n"
        "- service_contracts.status → manually_invalidated\n"
        "- service_contracts.invalidation_reason / invalidated_by_admin_id / invalidated_at 填\n"
        "- 写 admin_audit_logs (target_type=service_contract, action=invalidate)\n"
        "- **不删 blob** (WORM 不可删, ADR-0046 §3.3 第 3 层)\n"
        "- **不退款** (走 PaymentService 独立流程)"
    ),
    responses={**err(401, 403, 404, 409, 422, 500)},
)
async def invalidate_contract(
    contract_id: UUID,
    body: AdminContractInvalidateRequest,
    session: DBSession,
    principal=Depends(require_admin),
) -> AdminContractInvalidateResponse:
    admin_user = _require_jwt_admin(principal)

    contract = await session.scalar(
        select(ServiceContract).where(ServiceContract.id == contract_id)
    )
    if contract is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="contract not found",
        )

    # AC#3 assert_invalidation_metadata: reason + admin_id 必填
    try:
        assert_invalidation_metadata(
            invalidation_reason=body.reason,
            invalidated_by_admin_id=admin_user.id,
        )
    except ContractInvalidationMetadataMissingError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    # assert_transition: 强制走合法 transition
    # (重复 invalidate 命中 terminal guard → InvalidContractStateTransitionError)
    try:
        assert_transition(
            from_status=contract.status,
            to_status=ContractStatus.manually_invalidated,
            retry_count=contract.retry_count,
        )
    except InvalidContractStateTransitionError as exc:
        # 唯一 hard terminal — 重复 invalidate 触发
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    # S3-DEV-001-CONTRACT-WORM-COMPENSATION (ADR-0047 §5.2 降级语义):
    # WORM permanently_failed = 审计层不可信 (3 次 cron retry 全挂 + 高优 alert
    # 已外发) → 拒 admin invalidate, 要求 ops 先处理 WORM policy 问题后才能
    # 走 invalidate 流程. pending_retry 仍允许 (可能还会修复成功).
    from app.models.service_contract import ContractWormStatus

    if contract.worm_status == ContractWormStatus.permanently_failed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "contract WORM policy permanently_failed; "
                "先联系 ops 处理 Azure immutability policy 后再 invalidate"
            ),
        )

    # Mutate contract row (DB trigger 拒改 immutable 字段, status/invalidation_*
    # 在 mutable list, 写入 OK)
    now = datetime.now(timezone.utc)
    contract.status = ContractStatus.manually_invalidated
    contract.invalidation_reason = body.reason
    contract.invalidated_by_admin_id = admin_user.id
    contract.invalidated_at = now

    # admin_audit_logs (separate from user_audit_logs by ADR-0047 §3.5)
    audit = AdminAuditLog(
        target_type="service_contract",
        target_id=contract.id,
        action="invalidate",
        operator=str(admin_user.id),
        reason=body.reason,
    )
    session.add(audit)
    await session.flush()
    await session.commit()

    return AdminContractInvalidateResponse(
        contract_id=contract.id,
        order_id=contract.order_id,
        status=contract.status,
        invalidated_at=contract.invalidated_at,
        invalidated_by_admin_id=admin_user.id,
        invalidation_reason=contract.invalidation_reason,
        admin_audit_log_id=audit.id,
    )
