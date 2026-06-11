from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, field_serializer
from pydantic.types import condecimal

# ADR-0030: 金额统一 Decimal(10,2)，JSON 序列化为 number
MoneyDecimal = condecimal(max_digits=10, decimal_places=2)


class ApplyCompanionRequest(BaseModel):
    real_name: str = Field(
        ..., min_length=2, max_length=50, description="真实姓名", examples=["张三"]
    )
    id_number: str | None = Field(None, description="身份证号", examples=["110101199001011234"])
    certifications: str | None = Field(
        None, description="资质证书描述（多个用逗号分隔）", examples=["护士资格证,养老护理员"]
    )
    service_area: str | None = Field(
        None, description="服务区域，如『朝阳区,海淀区』", examples=["朝阳区,海淀区"]
    )
    service_types: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="提供的服务类型，逗号分隔",
        examples=["full_accompany,half_accompany"],
    )
    service_hospitals: str | None = Field(None, description="签约医院 ID 列表，逗号分隔")
    service_city: str | None = Field(None, description="服务城市", examples=["北京"])
    bio: str | None = Field(None, description="个人简介", examples=["5 年三甲医院护理经验"])


class UpdateCompanionProfileRequest(BaseModel):
    service_area: str | None = Field(None, description="服务区域")
    service_types: str | None = Field(None, description="服务类型")
    bio: str | None = Field(None, description="个人简介")
    certifications: str | None = Field(None, description="资质证书")
    service_hospitals: str | None = Field(None, description="签约医院")
    service_city: str | None = Field(None, description="服务城市")


class DimensionScores(BaseModel):
    """F-04 多维度评分在陆诊师详情中的平均值展示。"""

    punctuality: float = Field(0.0, description="守时维度平均分", examples=[4.8])
    professionalism: float = Field(0.0, description="专业维度平均分", examples=[4.9])
    communication: float = Field(0.0, description="沟通维度平均分", examples=[4.7])
    attitude: float = Field(0.0, description="态度维度平均分", examples=[5.0])


# ---------------------------------------------------------------------------
# Public-facing ABAC layer 3 schemas (S3-OPS-ABAC-COMPANIONS-LIST-PII-FIX)
# ---------------------------------------------------------------------------
#
# CRITICAL — these schemas serialize ``GET /v1/companions`` (list) and
# ``GET /v1/companions/{id}`` (detail) for **non-self** consumers.
# They are intentionally a **positive list** of public fields.  The
# following PII fields MUST NEVER appear here (negative list, ADR-0049 §6):
#   - ``real_name``       — use ``pseudonym_name`` (mask_name(real_name) fallback)
#   - ``id_number``       — never exposed publicly
#   - ``certification_no`` — never exposed publicly (admin-only)
#   - ``certification_image_url`` — admin-only, OSS URL is PII vector
#
# Enforced by ``test_companions_public_view_pii_negative_list`` sentinel test
# (ABAC layer 4, ADR-0049 §6.4).
#
# Self-introspection: ``GET /v1/companions/me`` continues to use
# ``CompanionDetailResponse`` (real_name OK — user views own profile).
# Admin: ``GET /admin/companions/*`` continues to use ``Companion*`` admin
# schemas (admin entrance is ABAC-allowed real_name access, ADR-0049 §6).


class CompanionDirectoryView(BaseModel):
    """Public-facing companion list item (non-self).

    ABAC layer 3 positive list — strictly forbids 4 PII fields (see module docstring).
    Reuses ``app.core.pii.mask_name`` for ``pseudonym_name`` (share.py 同款脱敏).
    """

    id: UUID = Field(..., description="陪诊师档案 ID")
    user_id: UUID = Field(..., description="对应用户 ID")
    pseudonym_name: str = Field(
        ...,
        description=(
            "化名 (PRD-001 v1.5 §F8 PII 脱敏)。"
            "S3 阶段 fallback ``mask_name(real_name)`` = 「张**」格式。"
            "PRD-001 v1.5 拆 ``companion_pseudonym`` table 后将切真正化名。"
        ),
        examples=["张**"],
    )
    service_area: str | None = Field(None, description="服务区域")
    service_types: str | None = Field(None, description="服务类型")
    service_hospitals: str | None = Field(None, description="签约医院 ID 列表")
    service_city: str | None = Field(None, description="服务城市")
    bio: str | None = Field(None, description="个人简介")
    avg_rating: float = Field(0.0, description="平均评分（0~5）", examples=[4.8])
    total_orders: int = Field(0, description="累计完成订单数", examples=[126])
    verification_status: str = Field(
        "pending",
        description="审核状态: pending/verified/rejected (UI 三态映射见 share.py)",
        examples=["verified"],
    )

    model_config = {"from_attributes": True}


class CompanionDirectoryDetailView(CompanionDirectoryView):
    """Public-facing companion detail (non-self).

    ABAC layer 3 — extends list view with public-safe detail fields.
    ``certification_type`` 可暴露 (公开资质类别如「护士证」, 非证件号).
    ``certified_at`` 仅 verified 状态时填 (与 share.py 对齐).
    ``certifications`` 描述性文本可暴露 (公开宣传, 不含 OSS URL).
    """

    certifications: str | None = Field(None, description="资质证书描述")
    certification_type: str | None = Field(
        None,
        description="认证类型 (如『护士证』, 非证件号)",
        examples=["护士证"],
    )
    certified_at: datetime | None = Field(
        None,
        description="认证通过时间 (仅 verified 状态填)",
    )
    created_at: datetime = Field(..., description="档案创建时间")
    dimension_scores: DimensionScores = Field(
        default_factory=DimensionScores,
        description="F-04 4 个维度的平均评分",
    )

    model_config = {"from_attributes": True}


# Negative list used by ABAC sentinel test (layer 4 defense).
# Source of truth for what MUST NOT leak through public companion endpoints.
COMPANION_DIRECTORY_VIEW_NEGATIVE_LIST: frozenset[str] = frozenset(
    {
        "real_name",
        "id_number",
        "certification_no",
        "certification_image_url",
    }
)
"""ABAC layer 4 negative list — sentinel-asserted absent from public schemas."""


class CompanionListResponse(BaseModel):
    id: UUID = Field(..., description="陪诊师档案 ID")
    user_id: UUID = Field(..., description="对应用户 ID")
    real_name: str = Field(..., description="真实姓名")
    service_area: str | None = Field(None, description="服务区域")
    service_types: str | None = Field(None, description="服务类型")
    service_hospitals: str | None = Field(None, description="签约医院 ID 列表")
    service_city: str | None = Field(None, description="服务城市")
    bio: str | None = Field(None, description="个人简介")
    avg_rating: float = Field(0.0, description="平均评分（0~5）", examples=[4.8])
    total_orders: int = Field(0, description="累计完成订单数", examples=[126])
    verification_status: str = Field(
        "pending", description="审核状态：pending/verified/rejected", examples=["verified"]
    )

    model_config = {"from_attributes": True}


class CompanionDetailResponse(CompanionListResponse):
    certifications: str | None = Field(None, description="资质证书")
    certification_type: str | None = Field(
        None, description="认证类型（护士证 / 健康管理师等）", examples=["护士证"]
    )
    certification_no: str | None = Field(None, description="证书编号", examples=["NO.20231234"])
    certification_image_url: str | None = Field(None, description="证书图片 OSS URL")
    certified_at: datetime | None = Field(None, description="认证通过时间")
    created_at: datetime = Field(..., description="档案创建时间")
    dimension_scores: DimensionScores = Field(
        default_factory=DimensionScores,
        description="F-04 4 个维度的平均评分（无评价时均为 0）",
    )

    model_config = {"from_attributes": True}


class CertifyCompanionRequest(BaseModel):
    """管理员为陪诊师设置资质认证（F-01）。"""

    certification_type: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="认证类型（护士证 / 健康管理师等）",
        examples=["护士证"],
    )
    certification_no: str = Field(
        ..., min_length=1, max_length=100, description="证书编号", examples=["NO.20231234"]
    )
    certification_image_url: str = Field(
        ..., min_length=1, max_length=500, description="证书图片 OSS URL"
    )


class CompanionStatsResponse(BaseModel):
    open_orders: int = Field(0, description="进行中订单数", examples=[2])
    total_orders: int = Field(0, description="累计订单数", examples=[126])
    avg_rating: float = Field(0.0, description="平均评分", examples=[4.8])
    total_earnings: MoneyDecimal = Field(
        Decimal("0.00"), description="累计收入（元）", examples=["12480.50"]
    )

    @field_serializer("total_earnings")
    def _ser_total_earnings(self, v: Decimal) -> Decimal:
        # ADR-0030 / TD-MONEY-01 (done 2026-05-25): 不再转 float。
        return Decimal(v).quantize(Decimal("0.01"))
