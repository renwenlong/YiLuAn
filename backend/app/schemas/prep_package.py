"""ABAC 4-layer view schemas for AI prep packages (ADR-0048 §7.0.1).

Three role-specific Pydantic views enforce **field-level access control**:

- ``UserPrepPackageView`` — patient-facing, full content
- ``CompanionPrepPackageView`` — companion-facing, **red-line**: no
  ``pre_visit_notes`` / ``possible_questions`` / ``trace_*`` / raw
  ``carry_items`` (only ``carry_items_summary``)
- ``AdminPrepPackageView`` — admin-facing, full content + ops metadata
  (trace_id / prompt_version_id / cost / fallback_reason)

The companion view's safety property is not "set to None" or "redacted
empty" — those fields are **literally absent from the Pydantic model**.
Even if the service layer accidentally returns extra fields, Pydantic's
``ConfigDict(extra="ignore")`` will silently drop them.

This is Layer 1 of the ABAC 4-layer defense (ADR-0048 §7.0):
- Layer 1: Schema — this file (fields don't exist)
- Layer 2: Endpoint — 3 independent routers + role-strict Depends
- Layer 3: Service — SELECT column trimming at DB layer (PART2)
- Layer 4: Test — unit + integration sentinel (PART2)
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PrepStatus(str, Enum):
    pending = "pending"
    generating = "generating"
    active = "active"
    active_fallback_template = "active_fallback_template"
    generation_failed = "generation_failed"


class _BasePrepFields(BaseModel):
    """Common config: read-only ORM mode, drop unknown fields silently.

    ``extra="ignore"`` is deliberate — if Service layer accidentally
    SELECTs forbidden columns and passes them to the view, Pydantic
    will silently drop them. This is defense in depth.
    """

    model_config = ConfigDict(from_attributes=True, extra="ignore")

    id: UUID
    order_id: UUID
    status: PrepStatus
    user_checked_items: list[str] = Field(default_factory=list)


class UserPrepPackageView(_BasePrepFields):
    """Patient-facing prep package view (full content, no ops metadata)."""

    carry_items: list[str] = Field(
        default_factory=list, description="建议携带物品清单 (完整列表)"
    )
    pre_visit_notes: str | None = Field(
        None, description="就诊前注意事项 (患者完整版,含病史相关提示)"
    )
    possible_questions: list[str] = Field(
        default_factory=list, description="建议向医生询问的问题"
    )
    companion_focus_points: list[str] = Field(
        default_factory=list, description="陪诊师协助焦点 (患者也可见)"
    )


class CompanionPrepPackageView(_BasePrepFields):
    """Companion-facing prep package view — **ABAC RED LINE**.

    Explicitly **absent**:
    - ``pre_visit_notes`` (病史相关原文)
    - ``possible_questions`` (主诉相关原文)
    - ``carry_items`` (替代为 ``carry_items_summary``)
    - ``trace_id`` / ``prompt_version_id`` / ops metadata
    """

    carry_items_summary: str | None = Field(
        None,
        description=(
            "携带物品摘要 (短句, 不暴露病情细节). 替代 ``carry_items`` 给陪诊师."
        ),
    )
    companion_focus_points: list[str] = Field(
        default_factory=list,
        description="陪诊师协助焦点 (服务性 tips, 不含病史)",
    )


class AdminPrepPackageView(_BasePrepFields):
    """Admin-facing prep package view — full content + ops metadata."""

    carry_items: list[str] = Field(
        default_factory=list, description="完整携带物品列表 (admin 可见全字段)"
    )
    pre_visit_notes: str | None = Field(None, description="就诊前注意事项 (完整版)")
    possible_questions: list[str] = Field(default_factory=list)
    companion_focus_points: list[str] = Field(default_factory=list)

    # ops metadata (admin-only)
    trace_id: str | None = Field(None, description="AI 调用 trace id (跟 logs / OTel 关联)")
    prompt_version_id: UUID | None = Field(
        None, description="生成本包用的 prompt version (git_blame + db)"
    )
    model: str | None = Field(None, description="AI provider model name (e.g. deepseek-chat)")
    estimated_cost_yuan: Decimal | None = Field(
        None, description="生成时预扣预算 (¥, 4 位小数)"
    )
    actual_cost_yuan: Decimal | None = Field(None, description="实际消耗预算 (¥, 4 位小数)")
    generation_time_ms: int | None = Field(None, description="生成耗时 (毫秒)")
    fallback_reason: str | None = Field(None, description="fallback 原因")
