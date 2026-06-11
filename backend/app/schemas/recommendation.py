"""Recommendation API schemas — ABAC layer 3 (Pydantic positive list).

Source: spec v1 final §1.2 字面 enum + §2.2 response shape.
ABAC: ADR-0049 §6 4-layer defense, this file = layer 3 (response schema).

CRITICAL — negative list 4 fields MUST NOT appear in this schema:
  - companion_phone
  - companion_id_card
  - companion_cert_url
  - companion_real_name

Enforced by ``test_recommendation_response_field_set_locked`` sentinel test
(layer 4, ADR-0049 §6.4).

Field name reconciliation (魈 拍板 B, 2026-06-11):
  spec 字面 (this file) ←→ model 字面 (CompanionProfile)
  - companion_cert_status ←→ verification_status (service mapping)
  - rating ←→ avg_rating (Pydantic validation_alias)
  - completed_orders ←→ total_orders (Pydantic validation_alias)
  - recommended ←→ (dynamic, service computed)

DRAFT — not committed until 魈 confirms #1/#2/#3 push backs (17:09Z + 17:14Z).
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CompanionCertStatus(str, Enum):
    """Spec v1 final §1.2 字面 enum (PRD-001 v1.5 §F8 ubiquitous).

    Distinct from model ``VerificationStatus`` enum (pending/verified/rejected).
    Mapping in ``app/services/recommendation.py::_map_cert_status``.
    """

    verified = "verified"
    pending_supplement = "pending_supplement"
    uncertified = "uncertified"


class RecommendationItem(BaseModel):
    """Single companion recommendation item in ``GET /v1/companions/recommendations`` response.

    ABAC layer 3 — positive list of public fields. NO PII fields.
    """

    model_config = ConfigDict(
        from_attributes=True,
        # Pydantic populate_by_name allows both spec 字面 (rating) and model 字面 (avg_rating)
        # during serialization, but validation_alias forces input mapping.
        populate_by_name=True,
    )

    companion_id: UUID = Field(..., description="陪诊师 ID")
    pseudonym_name: str | None = Field(
        None,
        description="化名 (PRD-001 v1.5 §F8 PII 脱敏, 严禁 fallback real_name)",
        examples=["陪诊师 A"],
    )
    bio: str | None = Field(
        None, description="个人简介 (public)", examples=["5 年三甲医院护理经验"]
    )
    service_city: str | None = Field(None, description="服务城市", examples=["北京"])
    service_area: str | None = Field(None, description="服务区域", examples=["朝阳区,海淀区"])
    service_types: str | None = Field(None, description="服务类型", examples=["full_accompany"])

    # 三态认证 (spec §1.2 字面 enum)
    companion_cert_status: CompanionCertStatus = Field(
        ..., description="陪诊师认证状态 (spec v1 final §1.2 字面 enum)"
    )

    # 评分字段 — Pydantic alias 自适应 model 字面
    rating: float = Field(
        0.0,
        ge=0.0,
        le=5.0,
        description="平均评分 (0~5)",
        validation_alias="avg_rating",
    )
    completed_orders: int = Field(
        0,
        ge=0,
        description="累计完成订单数",
        validation_alias="total_orders",
    )

    # 推荐元数据 (service 动态计算, 0 model 持久化)
    recommended: bool = Field(
        ...,
        description="是否进入推荐 top3 (service 层动态计算 = (cert_status != 'uncertified'))",
    )
    recommendation_rank: int | None = Field(
        None,
        ge=1,
        le=3,
        description="推荐排名 (1-3, None 表示未进 top3)",
    )

    created_at: datetime = Field(..., description="注册时间 (tie-breaker 4 用)")


class RecommendationResponse(BaseModel):
    """Spec v1 final §2.2 response shape.

    Includes meta fields ``total_eligible`` + ``filtered_uncertified_count``
    for transparency (PM-005-9 第 3 条 admin override 守门可见).
    """

    items: list[RecommendationItem] = Field(
        ...,
        max_length=3,
        description="top3 推荐 (uncertified 永不进, spec §1.4 admin override 守门)",
    )
    total_eligible: int = Field(
        ...,
        ge=0,
        description="符合 cert 资格的陪诊师总数 (verified + pending_supplement)",
    )
    filtered_uncertified_count: int = Field(
        ...,
        ge=0,
        description="被 admin override 过滤的 uncertified 陪诊师数 (审计透明用)",
    )


# Negative list (cross-domain forbidden, ADR-0049 §6.4)
# Used by schema sentinel test (NOT runtime check — defense via positive list).
RECOMMENDATION_RESPONSE_NEGATIVE_LIST: frozenset[str] = frozenset(
    {
        # ABAC layer 3 — PII fields strictly forbidden in recommendation response
        "companion_phone",
        "companion_id_card",
        "companion_cert_url",
        "companion_real_name",
        # cross-domain (ADR-0046 §3.5 + ADR-0048 §7.0)
        "contract_hash",
        "contract_storage_blob_path",
        "insurance_carrier_internal_id",
        "insurance_actual_premium",
        "preparation_prompt_version",
        "preparation_raw_llm_output",
        "share_token_hash",
        # internal admin/audit fields (must not leak to user-facing endpoint)
        "admin_review_comments",
        "admin_user_id",
        "feedback_internal_notes",
        "verification_completed_at",  # admin-only timestamp (kept on model, not exposed)
    }
)
"""Field names that **must not** appear in recommendation response.

Asserted in unit test ``test_recommendation_response_field_set_locked``.
"""
