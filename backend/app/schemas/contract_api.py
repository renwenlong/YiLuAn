"""Contract API request/response schemas (S3-DEV-001-CONTRACT-API).

ADR-0047 §6.2 + §6.3: 用户合同 acceptance + view 端点 + admin invalidate 端点。

Schemas 设计原则:
- ABAC 4 层防御 §1 (schema 层): 用户视图不暴露 admin-only 字段 (e.g.
  invalidation_reason / invalidated_by_admin_id 走 ContractAdminDetailResponse,
  ContractDetailResponse 不含)
- signed URL TTL 默认 ViewerRole.USER = 15min (ADR-0046 §3.1 ContractStorage.
  ``_VIEWER_TTL_SECONDS``); admin 视图走 ViewerRole.ADMIN = 5min
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.service_contract import ContractStatus


class ContractAcceptanceRequest(BaseModel):
    """POST /api/v1/contracts/{contract_id}/accept body.

    AC#1 (ADR-0047 §6.3): 用户勾选合同同意 (默认 unchecked).

    No-op body — order_id 与 user 信息从 path + auth 提取。本 schema 保留
    作为未来扩展位 (e.g. acceptance 时回填用户问卷).
    """


class ContractAcceptanceResponse(BaseModel):
    """POST /api/v1/contracts/{contract_id}/accept return.

    确认 audit log 写入 + 返回最新合同状态供前端校验。
    """

    contract_id: uuid.UUID
    order_id: uuid.UUID
    accepted_at: datetime = Field(
        description="user_audit_logs.created_at 时间 (UTC)"
    )
    audit_log_id: uuid.UUID = Field(
        description="user_audit_logs 行 ID, 取证溯源用"
    )


class ContractDetailResponse(BaseModel):
    """GET /api/v1/contracts/{contract_id} user-facing return.

    AC#2 (ADR-0047 §6.2): 返签名 URL (15min TTL) + 基础元信息。
    **不暴露** invalidation_reason / invalidated_by_admin_id / hash_inputs
    等 admin-only 字段 (ABAC §1 schema 层兜底)。
    """

    contract_id: uuid.UUID
    order_id: uuid.UUID
    template_version: str
    status: ContractStatus
    signed_url: str | None = Field(
        description=(
            "ContractStorage 签名 URL (TTL=15min, ViewerRole.USER). "
            "status != 'active' 时为 None (PDF 还没生成)."
        )
    )
    signed_url_expires_at: datetime | None = Field(
        description="signed URL 失效时间; status != 'active' 时为 None"
    )
    generated_at: datetime | None = Field(
        description="WORM 写入 time; status != 'active' 时为 None"
    )


class AdminContractInvalidateRequest(BaseModel):
    """POST /api/v1/admin/contracts/{contract_id}/invalidate body.

    AC#3: 必填 reason + invalidated_by_admin_id 通过 admin auth Depends 注入。
    """

    reason: str = Field(
        min_length=1,
        max_length=1000,
        description=(
            "作废原因 (必填, 进 admin_audit_logs.reason + "
            "service_contracts.invalidation_reason)"
        ),
    )


class AdminContractInvalidateResponse(BaseModel):
    """POST /api/v1/admin/contracts/{contract_id}/invalidate return."""

    contract_id: uuid.UUID
    order_id: uuid.UUID
    status: ContractStatus = Field(
        description="操作后 status (永远是 'manually_invalidated')"
    )
    invalidated_at: datetime
    invalidated_by_admin_id: int
    invalidation_reason: str
    admin_audit_log_id: uuid.UUID
