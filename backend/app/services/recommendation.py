"""Recommendation ranking algorithm (pure functions, no DB / no I/O).

Spec source: ``docs/prd/drafts/2026-06-11-s3-prd-001-f8-recommendation-filter-spec-v1-final.md``
§1.3 排序算法 + §1.4 admin override 守门 + §1.5 分页规则.

Pure ranking logic separated from data access so it can be unit-tested
without a database. ``RecommendationService`` (to be added) wires this
together with ``CompanionProfileRepository``.

This module is **architecture-neutral** w.r.t. the model-vs-spec
field naming drift (verification_status / avg_rating / total_orders
vs companion_cert_status / rating / completed_orders). Caller is
responsible for projecting model rows into ``RankingCandidate``;
projection layer is pending architect ratify (S3-DEV-006 fast-track
query, see board comments).

# Defense layers (ABAC 4-layer, ADR-0049 §6) — REUSED FROM
# ``backend/app/api/v1/companions_feedbacks.py`` pattern (applied at
# endpoint/service/schema/test layers, not this pure-algorithm module):
#   Layer 1: Depends(get_current_user) — auth gate at endpoint
#   Layer 2: Service SELECT only public columns + filter cert_status
#   Layer 3: Pydantic ``RecommendationItem`` does NOT define
#            companion_phone / companion_id_card / companion_cert_url
#            / companion_real_name → extra='ignore' drops them even if
#            service layer leaks
#   Layer 4: Sentinel test
#            ``test_recommendation_response_field_set_locked`` asserts
#            response field set is closed
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Sequence

from app.schemas.recommendation import CompanionCertStatus

if TYPE_CHECKING:
    from app.models.companion_profile import CompanionProfile, VerificationStatus

_logger = logging.getLogger(__name__)

# Re-exported for backward compat (commit 1 unit tests import from here).
__all__ = [
    "CompanionCertStatus",
    "RankingCandidate",
    "CERT_RANK",
    "ADMIN_OVERRIDE_RANK",
    "sort_companions_for_recommendation",
    "filter_top3_recommendations",
    "map_verification_to_cert_status",
    "companion_to_ranking_candidate",
]


# Spec §1.3: smaller rank = higher priority.
# uncertified rank=2 is sorted last AND filtered out from top3 推荐位.
CERT_RANK: dict[CompanionCertStatus, int] = {
    CompanionCertStatus.verified: 0,
    CompanionCertStatus.pending_supplement: 1,
    CompanionCertStatus.uncertified: 2,
}


# S3-DEV-006-FOLLOWUP-ADMIN-OVERRIDE 架构决策 2026-06-12 02:30Z 魈拍方案 C:
# admin override 作为第 2 sort key (CERT_RANK 之后、-rating 之前).
# True (admin 显示推) < None (默认) < False (admin 显示压)
#
# 设计哲学: admin override 影响 rank 但不破坏 cert/rating 序。admin 在
# verified 同 cert_status 内 推/压某个 companion, 但不能将 uncertified
# 括进 top3 (filter_top3_recommendations 硬约束).
ADMIN_OVERRIDE_RANK: dict[bool | None, int] = {
    True: 0,  # admin 显示推荐 (上推)
    None: 1,  # 未 override, 默认计算 (cert_status != uncertified 则默认 recommended)
    False: 2,  # admin 显示压低
}


@dataclass(frozen=True)
class RankingCandidate:
    """Minimal companion projection for ranking (no PII, no full model).

    Service layer hydrates this from companion data sources; pure-data,
    immutable, hashable so tests can assert ordering with simple equality.

    Field names follow spec v1 final §1.2 (``rating`` / ``completed_orders``
    / ``companion_cert_status``), independent of underlying model field
    names (``avg_rating`` / ``total_orders`` / ``verification_status``).

    S3-DEV-006-FOLLOWUP 加 ``admin_recommended_override``:
      - NULL (默认) = 未 override, 走 cert_status != uncertified 默认
      - True = admin 显示推 (sort rank 0)
      - False = admin 显示压 (sort rank 2)
    """

    companion_id: str
    companion_cert_status: CompanionCertStatus
    rating: float
    completed_orders: int
    created_at: datetime
    admin_recommended_override: bool | None = None


def sort_companions_for_recommendation(
    candidates: Sequence[RankingCandidate],
) -> list[RankingCandidate]:
    """Sort candidates by spec §1.3 + §1.4 ordering rule (5 层 sort key).

    Sort key (lower = higher priority):
      1. cert_status rank (verified < pending_supplement < uncertified)
      2. admin_override rank (True < None < False)  — S3-DEV-006-FOLLOWUP
      3. -rating  (higher rating first)
      4. -completed_orders  (more completed first)
      5. created_at  (earlier registered first)

    uncertified candidates are sorted but NOT filtered here; use
    ``filter_top3_recommendations`` for top3 enforcement.

    PM-005-9 排序规则:
      - 已认证 > 临时证明补交中 > 未认证 (第 1 层)
      - 同 cert_status 内, admin 显示推 > 默认 > admin 显示压 (第 2 层)
      - 同 admin override 内, rating > orders > created_at (3-5 层)

    架构决策 2026-06-12 02:30Z 魈拍方案 C: admin override 影响 rank 但不
    破坏 cert/rating 序, admin 不能跨 cert_status 守门 (硬约束留在
    ``filter_top3_recommendations``).
    """
    return sorted(
        candidates,
        key=lambda c: (
            CERT_RANK[c.companion_cert_status],
            ADMIN_OVERRIDE_RANK[c.admin_recommended_override],
            -c.rating,
            -c.completed_orders,
            c.created_at,
        ),
    )


def filter_top3_recommendations(
    sorted_candidates: Sequence[RankingCandidate],
    limit: int = 3,
) -> list[RankingCandidate]:
    """Take top ``limit`` candidates with cert_status != uncertified.

    PM-005-9 守门 (spec §1.4):
      - admin 设 ``recommended=true`` 但 ``cert_status=uncertified`` →
        数据库写入成功 (不报错) 但本函数仍 filter 掉 → 推荐 endpoint
        不返回该 companion. 守门在 service 层硬编码, 不可 admin override.
      - 已认证不足 ``limit`` 时返回实际数 (不补未认证).

    Args:
        sorted_candidates: 已按 sort_companions_for_recommendation 排序的 list.
        limit: top N (spec §2.1 default=3, max=3).

    Returns:
        前 limit 个 verified 或 pending_supplement candidate.
    """
    eligible = [
        c for c in sorted_candidates if c.companion_cert_status != CompanionCertStatus.uncertified
    ]
    return eligible[:limit]


# ===================================================================
# Service layer: model ↔ spec mapping (魈拍板方案 B, 2026-06-11)
# ===================================================================
#
# spec 字面 (CompanionCertStatus) ↔ model 字面 (VerificationStatus)
#
# Architect ratify B: 0 DB migration. Service layer facade mapping.
# DB 保留 VerificationStatus(pending/verified/rejected) 原字面.
# 推荐 endpoint 返 spec 字面 enum via this mapping.
#
# Rationale (PM-005-1/2 业务三态):
#   - verified → verified (1:1)
#   - pending → pending_supplement (PM 语义: "补交中")
#   - rejected → uncertified (PM 语义: "未认证")
#   - None (defensive, NOT NULL DDL 理论上不会出)
#       → uncertified (safe fallback) + logger.warning("[CERT_STATUS_DRIFT]")
#
# 魈 18:18Z 拍: logger.warning 加 `[CERT_STATUS_DRIFT]` tag prefix
# (Grafana/Datadog alert 打标可检索).


def map_verification_to_cert_status(
    vs: "VerificationStatus | None",
    *,
    companion_id: str | None = None,
) -> CompanionCertStatus:
    """Map ``CompanionProfile.verification_status`` → spec ``CompanionCertStatus``.

    Single source of truth for the 3-state mapping (PM-005-1/2):
      - verified → verified
      - pending → pending_supplement (“补交中”)
      - rejected → uncertified (“未认证”)
      - None (defensive, DB DDL NOT NULL 保证不会真出) → uncertified +
        ``logger.warning("[CERT_STATUS_DRIFT]")`` for observability.

    Args:
        vs: model side enum (or None for ORM defensive).
        companion_id: optional id for log context (None safe).

    Returns:
        Spec side 3-state enum.
    """
    # Late import to avoid circular dep (schemas → services → schemas).
    from app.models.companion_profile import VerificationStatus  # noqa: PLC0415

    if vs is None:
        _logger.warning(
            "[CERT_STATUS_DRIFT] CompanionProfile.verification_status is None "
            "(NOT NULL DDL 冲突, ORM defensive fallback uncertified) companion_id=%s",
            companion_id,
        )
        return CompanionCertStatus.uncertified
    if vs == VerificationStatus.verified:
        return CompanionCertStatus.verified
    if vs == VerificationStatus.pending:
        return CompanionCertStatus.pending_supplement
    # vs == VerificationStatus.rejected (唯一剩下)
    return CompanionCertStatus.uncertified


def companion_to_ranking_candidate(profile: "CompanionProfile") -> RankingCandidate:
    """Project ``CompanionProfile`` model row → ``RankingCandidate`` (spec 字面).

    Mapping (per architect ratify B):
      - id → companion_id (str)
      - verification_status → companion_cert_status
        (3-state via ``map_verification_to_cert_status``)
      - avg_rating → rating (alias)
      - total_orders → completed_orders (alias)
      - created_at → created_at (名 1:1)

    PII 字段 (real_name / id_number / certification_no / certification_image_url) 严禁拷入.
    """
    return RankingCandidate(
        companion_id=str(profile.id),
        companion_cert_status=map_verification_to_cert_status(
            profile.verification_status, companion_id=str(profile.id)
        ),
        rating=profile.avg_rating,
        completed_orders=profile.total_orders,
        created_at=profile.created_at,
        admin_recommended_override=profile.admin_recommended_override,
    )
