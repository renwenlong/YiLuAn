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


@dataclass(frozen=True)
class RankingCandidate:
    """Minimal companion projection for ranking (no PII, no full model).

    Service layer hydrates this from companion data sources; pure-data,
    immutable, hashable so tests can assert ordering with simple equality.

    Field names follow spec v1 final §1.2 (``rating`` / ``completed_orders``
    / ``companion_cert_status``), independent of underlying model field
    names (``avg_rating`` / ``total_orders`` / ``verification_status``).
    """

    companion_id: str
    companion_cert_status: CompanionCertStatus
    rating: float
    completed_orders: int
    created_at: datetime


def sort_companions_for_recommendation(
    candidates: Sequence[RankingCandidate],
) -> list[RankingCandidate]:
    """Sort candidates by spec §1.3 ordering rule.

    Sort key (lower = higher priority):
      1. cert_status rank (verified < pending_supplement < uncertified)
      2. -rating  (higher rating first)
      3. -completed_orders  (more completed first)
      4. created_at  (earlier registered first)

    uncertified candidates are sorted but NOT filtered here; use
    ``filter_top3_recommendations`` for top3 enforcement.

    PM-005-9 排序规则: 已认证 > 临时证明补交中 > 未认证.
    """
    return sorted(
        candidates,
        key=lambda c: (
            CERT_RANK[c.companion_cert_status],
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
    )
