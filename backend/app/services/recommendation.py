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

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Sequence


class CompanionCertStatus(str, Enum):
    """Three-state cert status from PRD-001 v1.5 §F8 (spec v1 final §1.2).

    Spec字面 enum (not yet wired to model — see fast-track query):
      - ``verified`` 已认证
      - ``pending_supplement`` 临时证明补交中
      - ``uncertified`` 未认证

    Architect ratify pending: 是否 alembic-migrate model enum 字面到此 (方案 A)
    或在 service 层 facade mapping (方案 B). 本 enum 只是 spec 字面,
    不依赖任何 model 实装. unit test 直接构造此 enum 验证 ranking 算法.
    """

    verified = "verified"
    pending_supplement = "pending_supplement"
    uncertified = "uncertified"


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
