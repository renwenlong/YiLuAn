"""Schemas for user-facing order precheck status.

S3-DEV-003-PRECHECK-BACKEND — 4 信任卡 (合同 / 保险 / AI 准备包 / 陪诊师资质)
precheck summary returned to the order owner before payment.

Design source: ``docs/design/S3-trust-precheck-ui.md`` §3.2 + §5.3 (ABAC
4-layer defense). ADR refs: ADR-0046 §3.5 (positive-list field prefix),
ADR-0047 §3.1 / §3.3 (contract/insurance status enums), ADR-0048 §7.0
(ABAC schema template).

⚠️ **ABAC Layer 1 — physical schema exclusion** ⚠️

The 5 View classes below are the **physical** boundary that proves we
cannot leak the 17 negative-list fields into a user response — they
are simply not defined as fields, so Pydantic serialization cannot
include them no matter what the service layer hands in.

The 17 negative-list fields (design §5.3, do NOT add any of these here
or to the 4 sub-views):

* Contract: ``contract_hash`` / ``hash_inputs`` / ``storage_blob_path`` /
  ``template_key``
* Insurance: ``carrier_internal_id`` / ``actual_premium`` /
  ``underwriter_meta``
* Preparation: ``prompt_version`` / ``model_used`` / ``raw_llm_output`` /
  ``cost_yuan``
* Companion cert: ``companion_real_name`` / ``companion_id_card_hash`` /
  ``companion_phone`` / ``companion_user_id`` (+ pattern matches
  ``companion_real_*`` / ``*_id_card_*``)

The companion field names follow ADR-0046 §3.5 ``companion_cert_*``
positive-list prefix (set in S3 to disambiguate from operator-side
``companion_*`` fields). The insurance fields use the ``insurance_*``
prefix per ADR-0046 §3.5 + 设计 §3.2 (胡桃 r2 amend).

Design doc uses abstract domain language (``ContractStateMachine`` /
``InsuranceOrderStateMachine`` / ``companion_cert_verifications``);
implementation maps to codebase actual models (``ContractStatus`` /
``ServiceInsuranceRecord`` / ``CompanionProfile.verification_status``)
per 魈 ack at 14:10Z. PR commit messages spell out the mapping for
later maintainers.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class ContractStatusView(BaseModel):
    """Contract card — only positive-list fields.

    Maps to :class:`app.models.service_contract.ContractStatus`;
    ``ready`` is ``True`` iff status is ``active`` (real WORM stored,
    signed URL available). ``generation_failed`` /
    ``generation_permanently_failed`` / ``manually_invalidated`` are
    surfaced as ``ready=False`` with a ``blocked_reason`` at the
    :class:`OrderPrecheckSummaryView` level.

    Negative-list (NEVER add here): ``contract_hash`` / ``hash_inputs`` /
    ``storage_blob_path`` / ``template_key``.
    """

    model_config = ConfigDict(extra="forbid")

    ready: bool
    contract_id: str | None = None
    contract_template_version: str | None = None
    contract_pdf_url: str | None = Field(
        default=None,
        description="Signed URL, TTL ≤15min. See `signed_url_expires_at` " "on parent summary.",
    )
    generated_at: datetime | None = None


class InsuranceStatusView(BaseModel):
    """Insurance card — only positive-list fields.

    Maps to :class:`app.models.service_insurance_record.ServiceInsuranceRecord`
    (design doc abstract name ``InsuranceOrderStateMachine``). ``ready``
    is ``True`` iff status is ``active``. ``expired`` / ``cancelled`` /
    ``issue_failed`` / ``manually_invalidated`` surface as
    ``ready=False`` with a ``blocked_reason`` on the parent summary.

    Field names use ``insurance_*`` prefix per ADR-0046 §3.5 + 胡桃
    r2 amend (避免与 admin-side ``policy_*`` 字段 collide).

    Negative-list (NEVER add here): ``carrier_internal_id`` /
    ``actual_premium`` / ``underwriter_meta``.
    """

    model_config = ConfigDict(extra="forbid")

    ready: bool
    insurance_order_id: str | None = None
    insurance_policy_no_masked: str | None = Field(
        default=None,
        description="保单号脱敏: 头 4 + ****  + 尾 4 (例 BX2026****1234)",
    )
    insurance_policy_pdf_url: str | None = Field(
        default=None,
        description="Signed URL, TTL ≤15min.",
    )
    insurance_effective_from: date | None = None


class PreparationStatusView(BaseModel):
    """AI preparation package card — only positive-list fields.

    Maps to :class:`app.models.preparation_package.PreparationPackage`
    (design doc abstract name ``preparation_status 表``). ``ready`` is
    ``True`` iff status is ``active`` or ``active_fallback_template``.

    Negative-list (NEVER add here): ``prompt_version`` / ``model_used`` /
    ``raw_llm_output`` / ``cost_yuan``.
    """

    model_config = ConfigDict(extra="forbid")

    ready: bool
    preparation_id: str | None = None
    prep_summary: str | None = Field(
        default=None,
        description="已过 ABAC + 关键词过滤的摘要文本",
    )
    sections_count: int | None = None
    generated_at: datetime | None = None


class CompanionCertStatusView(BaseModel):
    """Companion certification card — only positive-list fields.

    Maps to :class:`app.models.companion_profile.CompanionProfile`
    (design doc abstract name ``companion_cert_verifications 表``).
    ``ready`` is ``True`` iff ``verification_status`` is ``verified``.

    Field names use ``companion_cert_*`` prefix per ADR-0046 §3.5
    positive-list lint (区分 user-side display 与 operator-side admin
    field 防止 ABAC layer 3 service SELECT 漂移).

    Negative-list (NEVER add here): ``companion_real_name`` /
    ``companion_id_card_hash`` / ``companion_phone`` /
    ``companion_user_id`` (+ patterns ``companion_real_*`` /
    ``*_id_card_*``).
    """

    model_config = ConfigDict(extra="forbid")

    ready: bool
    companion_cert_pseudonym_name: str | None = Field(
        default=None,
        description="化名: e.g. '陈师傅', 不出真名 (ABAC defense)",
    )
    companion_cert_work_id: str | None = Field(
        default=None,
        description="工号: e.g. 'PC0042'",
    )
    companion_cert_qualifications: list[str] | None = Field(
        default=None,
        description="资质列表: ['康复治疗师', '健康管理师']",
    )
    companion_cert_proof_image_urls: list[str] | None = Field(
        default=None,
        description="资质证明图 signed URL, TTL ≤15min.",
    )
    companion_cert_verified_at: datetime | None = Field(
        default=None,
        description="admin verify 通过那一刻的 timestamp; 映射到 "
        "CompanionProfile.verification_completed_at (S3-DEV-003 c1 加列)",
    )


class OrderPrecheckSummaryView(BaseModel):
    """Aggregated 4-card precheck summary for an order.

    Returned by GET /api/v1/users/orders/{order_id}/precheck-status and
    pushed via WS /ws/v1/orders/{order_id}/precheck. Order owner only;
    admin / companion roles MUST NOT receive this view (ABAC Layer 2
    enforced at the endpoint).

    ``payment_enabled`` decouples from ``all_ready`` to allow PM-side
    payment-pause overrides (e.g. PM kills payment for an order even
    when 4 cards are ready). ``blocked_reason`` is filled when at least
    one card is ``ready=False``; format is a short human-readable
    string from the precheck文案 lint set (design §3.3) — front-end
    renders directly.
    """

    model_config = ConfigDict(extra="forbid")

    order_id: str

    contract_status: ContractStatusView
    insurance_status: InsuranceStatusView
    preparation_status: PreparationStatusView
    companion_cert_status: CompanionCertStatusView

    all_ready: bool
    payment_enabled: bool
    blocked_reason: str | None = None

    signed_url_expires_at: datetime | None = Field(
        default=None,
        description="所有 signed URL 中最早过期时间 (max-min). 前端用来"
        "判 polling 时是否需要 refresh URL. TTL >15min 的 URL CI fail.",
    )


__all__ = [
    "ContractStatusView",
    "InsuranceStatusView",
    "PreparationStatusView",
    "CompanionCertStatusView",
    "OrderPrecheckSummaryView",
]
