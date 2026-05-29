"""Pydantic schemas for family share (ADR-0036 §2.7 + PRD-001 v1.2 §4).

Field names / types / requireness MUST stay in lock-step with the
跨端字段表 in ADR-0036 §2.7 — the OpenAPI baseline diff (S2-DEV-004)
will flag any drift.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.order_share_token import ShareScope


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------


class CreateShareRequest(BaseModel):
    """POST /api/v1/orders/{order_id}/shares body."""

    share_scope: ShareScope = Field(
        default=ShareScope.FULL,
        description="分享数据切片：full=位置+进度+影像+摘要，progress_only=仅进度",
    )


class ExchangeSessionRequest(BaseModel):
    """POST /api/v1/shares/{token}/session body.

    Family viewer arrives via the short link, then exchanges *token + auth
    proof* for a short-lived ``share_session`` JWT (TTL 30min).

    Either ``wx_openid`` (微信小程序静默) or ``otp`` (iOS App / 外部浏览器
    SMS fallback) MUST be provided. Validation lives in the service layer
    so we can return a unified 401 instead of a 422.
    """

    wx_openid: str | None = Field(
        default=None,
        max_length=64,
        description="微信静默授权返回的 openid (jscode2session 路径)",
    )
    phone: str | None = Field(
        default=None,
        max_length=20,
        description="iOS/H5 fallback：收验证码的手机号（与 otp 成对提交）",
    )
    otp: str | None = Field(
        default=None,
        max_length=12,
        description="iOS/H5 fallback：6 位短信验证码（需与 phone 同传）",
    )


class SendOtpRequest(BaseModel):
    """POST /api/v1/shares/{token}/otp body — 请求下发短信验证码。"""

    phone: str = Field(
        ...,
        min_length=6,
        max_length=20,
        description="接收验证码的手机号",
    )


# ---------------------------------------------------------------------------
# Response bodies
# ---------------------------------------------------------------------------


class ShareTokenResponse(BaseModel):
    """Single token row payload returned to the order owner."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="token 行 ID（DELETE 时使用）")
    share_token: str = Field(..., description="URL-safe random token，短链 ID")
    share_url: str = Field(
        ..., description="短链 URL；模板 https://m.yiluan.cn/s/{token}"
    )
    share_scope: ShareScope = Field(..., description="分享数据切片")
    share_expires_at: datetime = Field(
        ..., description="过期时间 (UTC, ISO8601)"
    )
    share_revoked_at: datetime | None = Field(
        default=None, description="吊销时间，未吊销为 null"
    )
    created_at: datetime
    first_accessed_at: datetime | None = None
    distinct_accessor_count: int = Field(
        default=0, description="去重访问人数（aggregate, 上限 3 提示警告）"
    )


class CreateShareResponse(ShareTokenResponse):
    """POST returns the freshly minted token (single row + meta)."""

    share_active_count: int = Field(
        ...,
        description="同订单当前 active token 计数（上限 3）",
    )


class ListSharesResponse(BaseModel):
    items: list[ShareTokenResponse]
    share_active_count: int = Field(
        ..., description="当前 active token 计数（上限 3）"
    )


class ExchangeSessionResponse(BaseModel):
    """POST /shares/{token}/session response."""

    share_session: str = Field(
        ..., description="JWT，TTL 30 分钟；存 sessionStorage"
    )
    share_session_expires_at: datetime = Field(
        ..., description="JWT 过期时间 (UTC, ISO8601)"
    )
    share_scope: ShareScope
    order_id: UUID


class SendOtpResponse(BaseModel):
    """POST /shares/{token}/otp response."""

    sent: bool = Field(default=True, description="验证码是否已下发")
    masked_phone: str = Field(..., description="掩码手机号，如 138****0001")
    expires_in: int = Field(..., description="验证码有效期（秒）")


# ---------------------------------------------------------------------------
# Family-facing read-only order view (§2.5 PII rules)
# ---------------------------------------------------------------------------


class CompanionPublicView(BaseModel):
    name: str | None = Field(None, description="陪诊师姓名（完整）")
    avatar_url: str | None = None


class ShareOrderResponse(BaseModel):
    """GET /shares/session/order response — desensitized order view.

    Strict subset of ``OrderResponse`` — PII fields (患者电话/身份证/病情
    描述) are intentionally absent. Family-facing fields only.
    """

    order_id: UUID
    order_number: str
    status: str = Field(..., description="订单状态")
    service_type: str
    appointment_date: str
    appointment_time: str
    hospital_name: str | None
    patient_name_masked: str | None = Field(
        None, description="患者姓名首字 + **（§2.5 脱敏）"
    )
    companion: CompanionPublicView | None
    share_scope: ShareScope
    # Conditional sections — populated only when scope=full
    can_view_images: bool = Field(
        ..., description="scope=full 时为 true；progress_only 为 false"
    )
    can_view_ai_summary: bool = Field(
        ..., description="同上 (scope gating, §2.5 + AC#21)"
    )
    timeline: list[dict] | None = None
