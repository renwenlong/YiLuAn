"""Unit tests for recommendation ranking algorithm.

Source: ``app/services/recommendation.py`` (pure functions, no DB).

Covers spec v1 final (PRD-001 v1.5 §F8, see ``docs/prd/drafts/`` for spec v1 final):
  §1.3 排序算法 (verified > pending_supplement > uncertified + tie-breaker)
  §1.4 admin override 守门 (uncertified 永远不进 top3)
  §1.5 分页 (top3 不补未认证, limit 默认 3)

AC coverage:
  AC#3 三态排序 + tie-breaker — ``test_sort_*`` cases
  AC#4 uncertified 不进 rank — ``test_filter_top3_excludes_uncertified_*`` cases
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.services.recommendation import (
    CERT_RANK,
    CompanionCertStatus,
    RankingCandidate,
    filter_top3_recommendations,
    sort_companions_for_recommendation,
)


def _make(
    cid: str,
    status: CompanionCertStatus = CompanionCertStatus.verified,
    rating: float = 5.0,
    completed: int = 100,
    created_at: datetime | None = None,
) -> RankingCandidate:
    """Test factory — defaults to top-tier candidate so test customizes only relevant fields."""
    return RankingCandidate(
        companion_id=cid,
        companion_cert_status=status,
        rating=rating,
        completed_orders=completed,
        created_at=created_at or datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


class TestCertRank:
    """Spec §1.3: CERT_RANK 字面常量 (smaller = higher priority)."""

    def test_verified_rank_is_zero(self):
        assert CERT_RANK[CompanionCertStatus.verified] == 0

    def test_pending_supplement_rank_is_one(self):
        assert CERT_RANK[CompanionCertStatus.pending_supplement] == 1

    def test_uncertified_rank_is_two(self):
        assert CERT_RANK[CompanionCertStatus.uncertified] == 2

    def test_rank_order_strict_priority(self):
        assert (
            CERT_RANK[CompanionCertStatus.verified]
            < CERT_RANK[CompanionCertStatus.pending_supplement]
            < CERT_RANK[CompanionCertStatus.uncertified]
        )


class TestSortByCertStatus:
    """Spec §1.3 排序 Tier 1: cert_status 优先于其他所有 key."""

    def test_verified_before_pending_supplement(self):
        v = _make("v", CompanionCertStatus.verified)
        p = _make("p", CompanionCertStatus.pending_supplement, rating=999.0)
        result = sort_companions_for_recommendation([p, v])
        assert [c.companion_id for c in result] == ["v", "p"]

    def test_pending_supplement_before_uncertified(self):
        p = _make("p", CompanionCertStatus.pending_supplement)
        u = _make("u", CompanionCertStatus.uncertified, rating=999.0)
        result = sort_companions_for_recommendation([u, p])
        assert [c.companion_id for c in result] == ["p", "u"]

    def test_all_three_tiers_in_order(self):
        v = _make("v", CompanionCertStatus.verified, rating=1.0, completed=1)
        p = _make("p", CompanionCertStatus.pending_supplement, rating=5.0, completed=999)
        u = _make("u", CompanionCertStatus.uncertified, rating=5.0, completed=999)
        result = sort_companions_for_recommendation([u, p, v])
        assert [c.companion_id for c in result] == ["v", "p", "u"]


class TestTieBreakerRating:
    """Spec §1.3 Tier 2: rating DESC inside same cert_status."""

    def test_higher_rating_first(self):
        low = _make("low", rating=3.0)
        high = _make("high", rating=4.9)
        result = sort_companions_for_recommendation([low, high])
        assert [c.companion_id for c in result] == ["high", "low"]

    def test_equal_rating_falls_through(self):
        a = _make("a", rating=4.5, completed=50)
        b = _make("b", rating=4.5, completed=100)
        result = sort_companions_for_recommendation([a, b])
        # 同 rating → 走 completed_orders DESC → b 100 > a 50
        assert [c.companion_id for c in result] == ["b", "a"]


class TestTieBreakerCompletedOrders:
    """Spec §1.3 Tier 3: completed_orders DESC."""

    def test_more_orders_first(self):
        few = _make("few", completed=10)
        many = _make("many", completed=200)
        result = sort_companions_for_recommendation([few, many])
        assert [c.companion_id for c in result] == ["many", "few"]


class TestTieBreakerCreatedAt:
    """Spec §1.3 Tier 4: created_at ASC (earlier registered first)."""

    def test_earlier_registered_first(self):
        new = _make("new", created_at=datetime(2026, 6, 1, tzinfo=timezone.utc))
        old = _make("old", created_at=datetime(2024, 1, 1, tzinfo=timezone.utc))
        result = sort_companions_for_recommendation([new, old])
        assert [c.companion_id for c in result] == ["old", "new"]


class TestFullCompositeTieBreaker:
    """Spec §1.3: 4 key composite sort end-to-end."""

    def test_realistic_ranking(self):
        # 6 candidates, mixed cert + tie configurations
        a = _make("a", CompanionCertStatus.verified, rating=4.9, completed=200)
        b = _make(
            "b",
            CompanionCertStatus.verified,
            rating=4.9,
            completed=200,
            created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )  # earlier than a -> wins tie 4
        c = _make("c", CompanionCertStatus.verified, rating=4.8, completed=999)
        d = _make("d", CompanionCertStatus.pending_supplement, rating=5.0)
        e = _make("e", CompanionCertStatus.uncertified, rating=5.0)
        f = _make("f", CompanionCertStatus.uncertified, rating=3.0)
        result = sort_companions_for_recommendation([a, b, c, d, e, f])
        # b 比 a 早 created_at -> b 先, a 再; c rating 4.8 比 a/b 低
        # d pending_supplement 排在 verified 后; e/f uncertified 末尾
        # e rating 5.0 > f rating 3.0
        assert [c.companion_id for c in result] == ["b", "a", "c", "d", "e", "f"]


class TestFilterTop3Recommendations:
    """Spec §1.4 admin override 守门 + §1.5 分页."""

    def test_excludes_uncertified_even_when_top_rated(self):
        u_top = _make("u_top", CompanionCertStatus.uncertified, rating=5.0, completed=999)
        v = _make("v", CompanionCertStatus.verified, rating=4.0)
        sorted_list = sort_companions_for_recommendation([u_top, v])
        # u_top 因 cert_status rank=2 已被排到末尾
        assert [c.companion_id for c in sorted_list] == ["v", "u_top"]
        # filter 后只剩 v
        top3 = filter_top3_recommendations(sorted_list)
        assert [c.companion_id for c in top3] == ["v"]

    def test_uncertified_never_enters_top3(self):
        """Admin override 守门 (spec §1.4): 即使 admin 设 recommended=true,
        uncertified 仍被 filter."""
        candidates = [
            _make("u1", CompanionCertStatus.uncertified, rating=5.0),
            _make("u2", CompanionCertStatus.uncertified, rating=4.9),
            _make("u3", CompanionCertStatus.uncertified, rating=4.8),
        ]
        sorted_list = sort_companions_for_recommendation(candidates)
        top3 = filter_top3_recommendations(sorted_list)
        assert top3 == []

    def test_returns_at_most_limit(self):
        candidates = [
            _make(f"v{i}", CompanionCertStatus.verified, rating=5.0 - i * 0.1) for i in range(10)
        ]
        sorted_list = sort_companions_for_recommendation(candidates)
        top3 = filter_top3_recommendations(sorted_list)
        assert len(top3) == 3
        assert [c.companion_id for c in top3] == ["v0", "v1", "v2"]

    def test_returns_fewer_than_limit_when_pool_small(self):
        """Spec §1.5: 已认证不足 limit 时返回实际数."""
        candidates = [
            _make("v1", CompanionCertStatus.verified),
        ]
        sorted_list = sort_companions_for_recommendation(candidates)
        top3 = filter_top3_recommendations(sorted_list)
        assert len(top3) == 1

    def test_pending_supplement_included_in_top3(self):
        """Spec §1.3: pending_supplement 进 top3 (仅 uncertified 被守门)."""
        candidates = [
            _make("v1", CompanionCertStatus.verified, rating=4.5),
            _make("p1", CompanionCertStatus.pending_supplement, rating=5.0),
            _make("p2", CompanionCertStatus.pending_supplement, rating=4.8),
        ]
        sorted_list = sort_companions_for_recommendation(candidates)
        top3 = filter_top3_recommendations(sorted_list)
        assert [c.companion_id for c in top3] == ["v1", "p1", "p2"]

    def test_custom_limit_respected(self):
        candidates = [
            _make(f"v{i}", CompanionCertStatus.verified, rating=5.0 - i * 0.1) for i in range(5)
        ]
        sorted_list = sort_companions_for_recommendation(candidates)
        top2 = filter_top3_recommendations(sorted_list, limit=2)
        assert [c.companion_id for c in top2] == ["v0", "v1"]

    def test_empty_input(self):
        assert filter_top3_recommendations([]) == []

    def test_only_uncertified_returns_empty(self):
        """NO_ELIGIBLE_COMPANIONS scenario base case (AC#8 spec §2.1)."""
        candidates = [
            _make("u1", CompanionCertStatus.uncertified),
            _make("u2", CompanionCertStatus.uncertified),
        ]
        sorted_list = sort_companions_for_recommendation(candidates)
        top3 = filter_top3_recommendations(sorted_list)
        assert top3 == []


class TestCompanionCertStatusEnum:
    """Spec §1.2 字面 enum 验证."""

    def test_enum_values_literal(self):
        assert CompanionCertStatus.verified.value == "verified"
        assert CompanionCertStatus.pending_supplement.value == "pending_supplement"
        assert CompanionCertStatus.uncertified.value == "uncertified"

    def test_enum_is_str(self):
        """str enum mixin — Pydantic / JSON serialization safe."""
        assert isinstance(CompanionCertStatus.verified, str)
        assert CompanionCertStatus.verified == "verified"

    def test_enum_membership(self):
        assert "verified" in [s.value for s in CompanionCertStatus]
        # spec 字面只 3 态, model 字面 ('pending'/'rejected') 不应出现
        assert "pending" not in [s.value for s in CompanionCertStatus]
        assert "rejected" not in [s.value for s in CompanionCertStatus]


@pytest.mark.parametrize(
    "input_list,expected_order",
    [
        # 案 1: 3 verified 按 rating DESC
        (
            [
                ("a", CompanionCertStatus.verified, 3.0),
                ("b", CompanionCertStatus.verified, 5.0),
                ("c", CompanionCertStatus.verified, 4.0),
            ],
            ["b", "c", "a"],
        ),
        # 案 2: 混合 status, verified 全在前
        (
            [
                ("u", CompanionCertStatus.uncertified, 5.0),
                ("v", CompanionCertStatus.verified, 3.0),
                ("p", CompanionCertStatus.pending_supplement, 4.0),
            ],
            ["v", "p", "u"],
        ),
        # 案 3: 单 candidate
        (
            [("only", CompanionCertStatus.verified, 4.0)],
            ["only"],
        ),
    ],
)
def test_sort_parameterized(input_list, expected_order):
    candidates = [_make(cid, status, rating=rating) for cid, status, rating in input_list]
    result = sort_companions_for_recommendation(candidates)
    assert [c.companion_id for c in result] == expected_order


# ============================================================
# S3-DEV-006-FOLLOWUP-ADMIN-OVERRIDE — admin override sort key tests
# ============================================================
# AC#A5 5 case (架构师 魈 02:30Z 拍板方案 C):
#   (1) admin=true + cert=verified → 进 top3 rank 1
#   (2) admin=true + cert=uncertified → 0 进 top3 (硬约束生效)
#   (3) admin=false + cert=verified → 全列表末序 (admin_rank=2)
#   (4) admin=NULL + cert=verified → 默认 rank (admin_rank=1, 跟普通 verified 序)
#   (5) mixed 场景: 3 verified (2 admin=true 1 NULL) + 2 pending
#       → top3 = 2 admin=true verified + 1 NULL verified
# 引用: spec v1 final §1.4 line 125-156, PR #286 `5bdadd4`.


def _make_with_admin(
    cid: str,
    status: CompanionCertStatus = CompanionCertStatus.verified,
    admin: bool | None = None,
    rating: float = 5.0,
    completed: int = 100,
    created_at: datetime | None = None,
) -> RankingCandidate:
    """Test factory with admin_recommended_override 显示参数。"""
    return RankingCandidate(
        companion_id=cid,
        companion_cert_status=status,
        rating=rating,
        completed_orders=completed,
        created_at=created_at or datetime(2026, 1, 1, tzinfo=timezone.utc),
        admin_recommended_override=admin,
    )


class TestAdminOverrideRank:
    """ADMIN_OVERRIDE_RANK 字面常量 (smaller = higher priority).

    架构决策 2026-06-12 02:30Z 魈拍方案 C: True < None < False.
    """

    def test_true_rank_is_zero(self):
        from app.services.recommendation import ADMIN_OVERRIDE_RANK

        assert ADMIN_OVERRIDE_RANK[True] == 0

    def test_none_rank_is_one(self):
        from app.services.recommendation import ADMIN_OVERRIDE_RANK

        assert ADMIN_OVERRIDE_RANK[None] == 1

    def test_false_rank_is_two(self):
        from app.services.recommendation import ADMIN_OVERRIDE_RANK

        assert ADMIN_OVERRIDE_RANK[False] == 2

    def test_rank_order_strict_priority(self):
        from app.services.recommendation import ADMIN_OVERRIDE_RANK

        assert ADMIN_OVERRIDE_RANK[True] < ADMIN_OVERRIDE_RANK[None] < ADMIN_OVERRIDE_RANK[False]


class TestAdminOverrideSort5Case:
    """AC#A5: admin override 5 case 字面 (spec v1 final §1.4 + 魈 02:30Z 方案 C)."""

    def test_case_1_admin_true_verified_enters_top3_rank_1(self):
        """Case 1: admin=true + cert=verified → 进 top3 rank 1.

        admin_override=True + 普通 verified rating 平局时, admin=True (admin_rank=0)
        排在普通 verified (admin_rank=1) 之前.
        """
        admin_true = _make_with_admin(
            "admin_true_verified", CompanionCertStatus.verified, admin=True, rating=4.0
        )
        default = _make_with_admin(
            "default_verified", CompanionCertStatus.verified, admin=None, rating=5.0
        )
        sorted_list = sort_companions_for_recommendation([default, admin_true])
        assert sorted_list[0].companion_id == "admin_true_verified"
        assert sorted_list[1].companion_id == "default_verified"
        top3 = filter_top3_recommendations(sorted_list)
        assert top3[0].companion_id == "admin_true_verified"

    def test_case_2_admin_true_uncertified_filtered_from_top3(self):
        """Case 2: admin=true + cert=uncertified → 0 进 top3 (硬约束生效).

        即使 admin_override=True, cert_status=uncertified 仍被 filter.
        守门规则不可绕过 (spec §1.4 字面).
        """
        admin_uncert = _make_with_admin(
            "admin_true_uncertified",
            CompanionCertStatus.uncertified,
            admin=True,
            rating=5.0,
            completed=999,
        )
        verified = _make_with_admin(
            "verified", CompanionCertStatus.verified, admin=None, rating=3.0
        )
        sorted_list = sort_companions_for_recommendation([admin_uncert, verified])
        assert sorted_list[0].companion_id == "verified"
        assert sorted_list[1].companion_id == "admin_true_uncertified"
        top3 = filter_top3_recommendations(sorted_list)
        assert [c.companion_id for c in top3] == ["verified"]
        assert "admin_true_uncertified" not in [c.companion_id for c in top3]

    def test_case_3_admin_false_verified_falls_to_end_of_full_list(self):
        """Case 3: admin=false + cert=verified → 全列表末序 (admin_rank=2).

        admin=False 显示压低, 在同 cert_status 内排到末尾.
        但仍是 verified, filter 后仍进 top3 (uncertified 才被守门).
        """
        admin_false = _make_with_admin(
            "admin_false_verified", CompanionCertStatus.verified, admin=False, rating=5.0
        )
        default = _make_with_admin(
            "default_verified", CompanionCertStatus.verified, admin=None, rating=3.0
        )
        sorted_list = sort_companions_for_recommendation([admin_false, default])
        assert sorted_list[0].companion_id == "default_verified"
        assert sorted_list[1].companion_id == "admin_false_verified"
        top3 = filter_top3_recommendations(sorted_list)
        assert [c.companion_id for c in top3] == ["default_verified", "admin_false_verified"]

    def test_case_4_admin_none_verified_default_rank(self):
        """Case 4: admin=NULL + cert=verified → 默认 rank (admin_rank=1, 跟普通 verified 序).

        admin=None 即未 override, sort 序按默认 cert/rating/orders/created_at.
        多个 admin=None verified 之间按 rating DESC.
        """
        candidates = [
            _make_with_admin("default_low", CompanionCertStatus.verified, admin=None, rating=3.0),
            _make_with_admin("default_high", CompanionCertStatus.verified, admin=None, rating=5.0),
            _make_with_admin("default_mid", CompanionCertStatus.verified, admin=None, rating=4.0),
        ]
        sorted_list = sort_companions_for_recommendation(candidates)
        assert [c.companion_id for c in sorted_list] == [
            "default_high",
            "default_mid",
            "default_low",
        ]

    def test_case_5_mixed_realistic_scenario(self):
        """Case 5: 3 verified (2 admin=true, 1 NULL) + 2 pending.

        期望: top3 = 2 admin=true verified + 1 NULL verified.

        混合场景 — admin override 影响排序但不绕过 cert_status 守门.
        2 admin=true verified rank 0-1, 1 default verified rank 2, pending rank 3-4.
        """
        candidates = [
            _make_with_admin(
                "v_admin_true_high", CompanionCertStatus.verified, admin=True, rating=4.5
            ),
            _make_with_admin(
                "v_admin_true_low", CompanionCertStatus.verified, admin=True, rating=4.0
            ),
            _make_with_admin("v_default", CompanionCertStatus.verified, admin=None, rating=5.0),
            _make_with_admin(
                "p_high", CompanionCertStatus.pending_supplement, admin=None, rating=4.9
            ),
            _make_with_admin(
                "p_low", CompanionCertStatus.pending_supplement, admin=None, rating=4.7
            ),
        ]
        sorted_list = sort_companions_for_recommendation(candidates)
        expected_order = [
            "v_admin_true_high",
            "v_admin_true_low",
            "v_default",
            "p_high",
            "p_low",
        ]
        assert [c.companion_id for c in sorted_list] == expected_order
        top3 = filter_top3_recommendations(sorted_list)
        assert [c.companion_id for c in top3] == [
            "v_admin_true_high",
            "v_admin_true_low",
            "v_default",
        ]


class TestAdminOverrideEdgeCases:
    """Edge cases — admin override + cert_status 组合矩阵 + 守门 verify."""

    def test_admin_true_pending_supplement_promoted_in_pending_tier(self):
        """admin=True 在 pending_supplement 内也生效 — admin 影响 rank 在所有 cert tier 适用."""
        candidates = [
            _make_with_admin(
                "p_admin_true", CompanionCertStatus.pending_supplement, admin=True, rating=3.0
            ),
            _make_with_admin(
                "p_default", CompanionCertStatus.pending_supplement, admin=None, rating=5.0
            ),
        ]
        sorted_list = sort_companions_for_recommendation(candidates)
        assert sorted_list[0].companion_id == "p_admin_true"

    def test_admin_false_uncertified_double_excluded(self):
        """admin=False + uncertified — 双重排末尾, 仍被守门, 不进 top3."""
        admin_false_uncert = _make_with_admin(
            "admin_false_uncert", CompanionCertStatus.uncertified, admin=False, rating=5.0
        )
        verified = _make_with_admin("verified", CompanionCertStatus.verified, admin=None)
        sorted_list = sort_companions_for_recommendation([admin_false_uncert, verified])
        assert sorted_list[-1].companion_id == "admin_false_uncert"
        top3 = filter_top3_recommendations(sorted_list)
        assert [c.companion_id for c in top3] == ["verified"]

    def test_all_admin_true_verified_break_tie_by_rating(self):
        """全部 admin=True + verified 同 admin_rank, 后续 sort key (rating) 起作用."""
        candidates = [
            _make_with_admin("low", CompanionCertStatus.verified, admin=True, rating=3.0),
            _make_with_admin("high", CompanionCertStatus.verified, admin=True, rating=5.0),
            _make_with_admin("mid", CompanionCertStatus.verified, admin=True, rating=4.0),
        ]
        sorted_list = sort_companions_for_recommendation(candidates)
        assert [c.companion_id for c in sorted_list] == ["high", "mid", "low"]
