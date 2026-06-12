"""Unit tests for service-layer model↔spec mapping (commit 2 part of S3-DEV-006).

Covers:
  - ``map_verification_to_cert_status`` 3-state + None defensive (logger.warning)
  - ``companion_to_ranking_candidate`` model projection (no PII)
  - ``_to_recommendation_item`` mask_name + alias fields
  - ``RecommendationItem`` schema validation (positive list + alias)
  - ``RecommendationResponse`` schema validation + meta counts
  - ``RECOMMENDATION_RESPONSE_NEGATIVE_LIST`` sentinel (ABAC layer 4)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.models.companion_profile import VerificationStatus
from app.schemas.recommendation import (
    RECOMMENDATION_RESPONSE_NEGATIVE_LIST,
    CompanionCertStatus,
    RecommendationItem,
    RecommendationResponse,
)
from app.services.recommendation import (
    RankingCandidate,
    companion_to_ranking_candidate,
    map_verification_to_cert_status,
)
from app.services.recommendation_service import _to_recommendation_item

# ============================================================
# 1. map_verification_to_cert_status (3-state + None defensive)
# ============================================================


class TestMapVerificationToCertStatus:
    """魈 18:18Z 拍: logger.warning 加 [CERT_STATUS_DRIFT] tag prefix."""

    def test_verified_maps_to_verified(self):
        assert (
            map_verification_to_cert_status(VerificationStatus.verified)
            == CompanionCertStatus.verified
        )

    def test_pending_maps_to_pending_supplement(self):
        assert (
            map_verification_to_cert_status(VerificationStatus.pending)
            == CompanionCertStatus.pending_supplement
        )

    def test_rejected_maps_to_uncertified(self):
        assert (
            map_verification_to_cert_status(VerificationStatus.rejected)
            == CompanionCertStatus.uncertified
        )

    def test_none_defensive_fallback_to_uncertified(self):
        """DB DDL NOT NULL 保证不会真出 None, 但 ORM defensive 仍处理."""
        result = map_verification_to_cert_status(None)
        assert result == CompanionCertStatus.uncertified

    def test_none_emits_drift_warning_with_tag(self, caplog):
        """魈 18:18Z 拍: [CERT_STATUS_DRIFT] tag prefix (Grafana/Datadog 检索)."""
        import logging

        caplog.set_level(logging.WARNING, logger="app.services.recommendation")
        map_verification_to_cert_status(None, companion_id="abc-123")
        # 应 emit warning with tag
        assert any(
            "[CERT_STATUS_DRIFT]" in rec.message for rec in caplog.records
        ), "logger.warning missing [CERT_STATUS_DRIFT] tag"
        assert any(
            "abc-123" in rec.message for rec in caplog.records
        ), "companion_id should be in warning message context"

    def test_valid_values_emit_no_warning(self, caplog):
        """正常 3 state 不应 emit drift warning."""
        import logging

        caplog.set_level(logging.WARNING, logger="app.services.recommendation")
        for vs in (
            VerificationStatus.verified,
            VerificationStatus.pending,
            VerificationStatus.rejected,
        ):
            map_verification_to_cert_status(vs, companion_id="xyz")
        assert not any(
            "[CERT_STATUS_DRIFT]" in rec.message for rec in caplog.records
        ), "valid VerificationStatus should not emit drift warning"


# ============================================================
# 2. companion_to_ranking_candidate (model → spec dataclass)
# ============================================================


class TestCompanionToRankingCandidate:
    def _make_profile(self, **overrides):
        """Lightweight CompanionProfile-shaped mock (SimpleNamespace)."""
        defaults = {
            "id": uuid.UUID("12345678-1234-5678-1234-567812345678"),
            "user_id": uuid.uuid4(),
            "real_name": "测试陪诊师",
            "id_number": "110101199001011234",  # PII — should NOT leak
            "certification_no": "NO.20231234",  # PII — should NOT leak
            "certification_image_url": "https://oss.example.com/cert.jpg",  # PII
            "service_city": "北京",
            "service_area": "朝阳区",
            "service_types": "full_accompany",
            "bio": "5年三甲护理经验",
            "avg_rating": 4.8,
            "total_orders": 126,
            "verification_status": VerificationStatus.verified,
            "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
            # S3-DEV-006-FOLLOWUP-ADMIN-OVERRIDE: admin 手动 override 字段
            # 默认 None = 未 override, 走 service 默认计算 cert_status != uncertified
            "admin_recommended_override": None,
        }
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    def test_basic_projection_mapping(self):
        profile = self._make_profile()
        candidate = companion_to_ranking_candidate(profile)
        assert isinstance(candidate, RankingCandidate)
        assert candidate.companion_id == "12345678-1234-5678-1234-567812345678"
        assert candidate.companion_cert_status == CompanionCertStatus.verified
        assert candidate.rating == 4.8
        assert candidate.completed_orders == 126

    def test_pending_status_maps_to_pending_supplement(self):
        profile = self._make_profile(verification_status=VerificationStatus.pending)
        candidate = companion_to_ranking_candidate(profile)
        assert candidate.companion_cert_status == CompanionCertStatus.pending_supplement

    def test_rejected_status_maps_to_uncertified(self):
        profile = self._make_profile(verification_status=VerificationStatus.rejected)
        candidate = companion_to_ranking_candidate(profile)
        assert candidate.companion_cert_status == CompanionCertStatus.uncertified

    def test_pii_fields_not_present_on_candidate(self):
        """RankingCandidate dataclass 字面不存 PII 字段 — defensive at type level."""
        profile = self._make_profile()
        candidate = companion_to_ranking_candidate(profile)
        # __dataclass_fields__ has authoritative field list
        fields = set(candidate.__dataclass_fields__.keys())
        for pii in ("real_name", "id_number", "certification_no", "certification_image_url"):
            assert pii not in fields, f"PII field {pii!r} leaked into RankingCandidate"

    def test_admin_override_projection_none(self):
        """S3-DEV-006-FOLLOWUP: profile.admin_recommended_override=None 默认传递."""
        profile = self._make_profile(admin_recommended_override=None)
        candidate = companion_to_ranking_candidate(profile)
        assert candidate.admin_recommended_override is None

    def test_admin_override_projection_true(self):
        """S3-DEV-006-FOLLOWUP: profile.admin_recommended_override=True 透传."""
        profile = self._make_profile(admin_recommended_override=True)
        candidate = companion_to_ranking_candidate(profile)
        assert candidate.admin_recommended_override is True

    def test_admin_override_projection_false(self):
        """S3-DEV-006-FOLLOWUP: profile.admin_recommended_override=False 透传."""
        profile = self._make_profile(admin_recommended_override=False)
        candidate = companion_to_ranking_candidate(profile)
        assert candidate.admin_recommended_override is False


# ============================================================
# 3. _to_recommendation_item (mask_name + alias fields)
# ============================================================


class TestToRecommendationItem:
    def _make_profile(self, **overrides):
        defaults = {
            "id": uuid.UUID("12345678-1234-5678-1234-567812345678"),
            "real_name": "张三",
            "bio": "护理 5 年",
            "service_city": "北京",
            "service_area": "朝阳区",
            "service_types": "full_accompany",
            "verification_status": VerificationStatus.verified,
            "avg_rating": 4.5,
            "total_orders": 100,
            "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        }
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    def test_mask_name_applied_to_pseudonym(self):
        profile = self._make_profile(real_name="张三")
        d = _to_recommendation_item(profile, recommended=True, rank=1)
        # mask_name("张三") → "张**" (per app.core.pii.mask_name)
        assert d["pseudonym_name"] == "张**"

    def test_pseudonym_none_when_real_name_empty(self):
        profile = self._make_profile(real_name=None)
        d = _to_recommendation_item(profile, recommended=False, rank=None)
        assert d["pseudonym_name"] is None

    def test_alias_fields_use_model_names_for_validation(self):
        """dict keys are model字面 (avg_rating, total_orders) for Pydantic alias."""
        profile = self._make_profile(avg_rating=4.5, total_orders=100)
        d = _to_recommendation_item(profile, recommended=True, rank=1)
        # Pydantic validation_alias expects model names for parsing
        assert d["avg_rating"] == 4.5
        assert d["total_orders"] == 100

    def test_no_pii_keys_in_dict(self):
        profile = self._make_profile()
        d = _to_recommendation_item(profile, recommended=True, rank=1)
        for pii in ("real_name", "id_number", "certification_no", "certification_image_url"):
            assert pii not in d, f"PII key {pii!r} leaked into _to_recommendation_item output"


# ============================================================
# 4. RecommendationItem schema (positive list + alias)
# ============================================================


class TestRecommendationItemSchema:
    def _make_dict(self, **overrides):
        d = {
            "companion_id": uuid.UUID("12345678-1234-5678-1234-567812345678"),
            "pseudonym_name": "张**",
            "bio": "护理 5 年",
            "service_city": "北京",
            "service_area": "朝阳区",
            "service_types": "full_accompany",
            "companion_cert_status": CompanionCertStatus.verified,
            "avg_rating": 4.5,  # validation_alias → rating
            "total_orders": 100,  # validation_alias → completed_orders
            "recommended": True,
            "recommendation_rank": 1,
            "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        }
        d.update(overrides)
        return d

    def test_alias_avg_rating_parses_to_rating(self):
        item = RecommendationItem.model_validate(self._make_dict(avg_rating=4.5))
        assert item.rating == 4.5

    def test_alias_total_orders_parses_to_completed_orders(self):
        item = RecommendationItem.model_validate(self._make_dict(total_orders=100))
        assert item.completed_orders == 100

    def test_recommendation_rank_bounds(self):
        # rank must be 1-3 (spec §2.1 top3)
        with pytest.raises(ValueError):
            RecommendationItem.model_validate(self._make_dict(recommendation_rank=4))
        with pytest.raises(ValueError):
            RecommendationItem.model_validate(self._make_dict(recommendation_rank=0))

    def test_rating_bounds(self):
        with pytest.raises(ValueError):
            RecommendationItem.model_validate(self._make_dict(avg_rating=5.1))
        with pytest.raises(ValueError):
            RecommendationItem.model_validate(self._make_dict(avg_rating=-0.1))


# ============================================================
# 5. ABAC layer 4 sentinel — negative list intersection = empty set
# ============================================================


class TestRecommendationABACSentinel:
    """ABAC layer 4 (ADR-0049 §6.4) — schema field set is closed positive list."""

    def test_recommendation_item_no_pii_intersection(self):
        item_fields = set(RecommendationItem.model_fields.keys())
        intersection = item_fields & RECOMMENDATION_RESPONSE_NEGATIVE_LIST
        assert (
            intersection == set()
        ), f"RecommendationItem leaks {intersection}; remove from positive list"

    def test_recommendation_response_no_pii_intersection(self):
        resp_fields = set(RecommendationResponse.model_fields.keys())
        intersection = resp_fields & RECOMMENDATION_RESPONSE_NEGATIVE_LIST
        assert intersection == set(), f"RecommendationResponse leaks {intersection}; remove"

    def test_negative_list_immutable_frozenset(self):
        with pytest.raises((AttributeError, TypeError)):
            RECOMMENDATION_RESPONSE_NEGATIVE_LIST.add("companion_phone")  # type: ignore[attr-defined]

    def test_negative_list_includes_core_pii(self):
        for pii in (
            "companion_phone",
            "companion_id_card",
            "companion_cert_url",
            "companion_real_name",
        ):
            assert (
                pii in RECOMMENDATION_RESPONSE_NEGATIVE_LIST
            ), f"core PII {pii!r} missing from negative list — ABAC layer 4 weakened"
