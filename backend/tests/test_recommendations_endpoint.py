"""Integration test for ``GET /v1/companions/recommendations`` endpoint.

Commit 3 of S3-DEV-006. Uses real FastAPI client + SQLite test DB.
Covers spec v1 final §1.3 sort + §1.4 admin override 守门 + §2.2 response shape.

ABAC layer 3 + 4 assertions verify endpoint NEVER returns PII:
- real_name / id_number / certification_no / certification_image_url
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models.companion_profile import CompanionProfile, VerificationStatus
from app.models.user import User, UserRole
from tests.conftest import test_session_factory as _session_factory

# ============================================================
# Helpers
# ============================================================


async def _create_companion(
    *,
    real_name: str,
    verification_status: VerificationStatus,
    avg_rating: float = 4.0,
    total_orders: int = 50,
    service_city: str | None = "北京",
    created_at: datetime | None = None,
) -> CompanionProfile:
    """Insert a companion row + its owning user."""
    async with _session_factory() as session:
        user = User(
            id=uuid.uuid4(),
            display_name=f"u-{real_name}",
            phone=f"139{uuid.uuid4().int % 10**8:08d}",
            role=UserRole.companion,
        )
        session.add(user)
        await session.flush()

        profile = CompanionProfile(
            id=uuid.uuid4(),
            user_id=user.id,
            real_name=real_name,
            service_city=service_city,
            service_area="朝阳区",
            service_types="full_accompany",
            bio=f"{real_name} bio",
            avg_rating=avg_rating,
            total_orders=total_orders,
            verification_status=verification_status,
            created_at=created_at or datetime.now(timezone.utc),
        )
        session.add(profile)
        await session.commit()
        await session.refresh(profile)
        return profile


# ============================================================
# Test class
# ============================================================


@pytest.mark.asyncio
class TestGetRecommendations:
    """spec v1 final §2.1 + §2.2 — GET /v1/companions/recommendations."""

    async def test_empty_when_no_companions(self, authenticated_client):
        resp = await authenticated_client.get("/api/v1/companions/recommendations")
        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["total_eligible"] == 0
        assert body["filtered_uncertified_count"] == 0

    async def test_only_uncertified_returns_empty_items(self, authenticated_client):
        """spec §1.4: 未认证不进 top3, 即使是 only candidate (rejected → uncertified)."""
        await _create_companion(
            real_name="未认证陪诊师",
            verification_status=VerificationStatus.rejected,
        )
        resp = await authenticated_client.get("/api/v1/companions/recommendations")
        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["total_eligible"] == 0
        assert body["filtered_uncertified_count"] == 1

    async def test_verified_in_top3_with_rank_1(self, authenticated_client):
        profile = await _create_companion(
            real_name="张三",
            verification_status=VerificationStatus.verified,
            avg_rating=4.8,
        )
        resp = await authenticated_client.get("/api/v1/companions/recommendations")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) == 1
        item = body["items"][0]
        assert item["companion_id"] == str(profile.id)
        assert item["companion_cert_status"] == "verified"
        assert item["recommended"] is True
        assert item["recommendation_rank"] == 1

    async def test_pseudonym_name_uses_mask_name(self, authenticated_client):
        """ABAC: pseudonym_name = mask_name(real_name), NOT real_name itself."""
        await _create_companion(
            real_name="张三",
            verification_status=VerificationStatus.verified,
        )
        resp = await authenticated_client.get("/api/v1/companions/recommendations")
        body = resp.json()
        item = body["items"][0]
        # mask_name("张三") → "张**" per app.core.pii
        assert item["pseudonym_name"] == "张**"

    async def test_pii_fields_absent_from_response(self, authenticated_client):
        """ABAC layer 3 — sentinel assert no PII in recommendation response."""
        async with _session_factory() as session:
            # Set up companion WITH PII fields (cert + id_number)
            user = User(
                id=uuid.uuid4(),
                display_name="u-pii-test",
                phone="13900008888",
                role=UserRole.companion,
            )
            session.add(user)
            await session.flush()
            profile = CompanionProfile(
                id=uuid.uuid4(),
                user_id=user.id,
                real_name="李四",
                id_number="110101199001011234",  # PII
                certification_no="NO.SUPER-SECRET",  # PII
                certification_image_url="https://oss.example.com/cert.jpg",  # PII
                certification_type="护士证",
                verification_status=VerificationStatus.verified,
                avg_rating=5.0,
                total_orders=200,
                created_at=datetime.now(timezone.utc),
            )
            session.add(profile)
            await session.commit()

        resp = await authenticated_client.get("/api/v1/companions/recommendations")
        body = resp.json()
        item = body["items"][0]
        # ABAC layer 4 sentinel: PII must NOT leak
        for pii in ("real_name", "id_number", "certification_no", "certification_image_url"):
            assert pii not in item, f"PII {pii!r} leaked to recommendation response"

    async def test_sort_order_verified_above_pending_above_uncertified(
        self, authenticated_client
    ):
        """spec §1.3 sort: verified > pending_supplement > uncertified."""
        # Insert in mixed order; sort should return verified first.
        now = datetime.now(timezone.utc)
        verified = await _create_companion(
            real_name="V",
            verification_status=VerificationStatus.verified,
            avg_rating=4.0,
            total_orders=50,
            created_at=now,
        )
        pending = await _create_companion(
            real_name="P",
            verification_status=VerificationStatus.pending,
            avg_rating=4.9,
            total_orders=200,
            created_at=now - timedelta(days=10),
        )
        await _create_companion(
            real_name="R",
            verification_status=VerificationStatus.rejected,
            avg_rating=5.0,
            total_orders=999,
        )

        resp = await authenticated_client.get("/api/v1/companions/recommendations")
        body = resp.json()
        items = body["items"]
        # rejected is filtered (uncertified never in top3)
        assert len(items) == 2
        # verified first regardless of rating disadvantage
        assert items[0]["companion_id"] == str(verified.id)
        assert items[0]["companion_cert_status"] == "verified"
        assert items[1]["companion_id"] == str(pending.id)
        assert items[1]["companion_cert_status"] == "pending_supplement"
        # rank assigned 1, 2
        assert items[0]["recommendation_rank"] == 1
        assert items[1]["recommendation_rank"] == 2
        assert body["total_eligible"] == 2
        assert body["filtered_uncertified_count"] == 1

    async def test_tie_break_rating_desc_then_orders_desc_then_created_asc(
        self, authenticated_client
    ):
        """spec §1.3 tie-breaker: rating DESC → completed_orders DESC → created_at ASC."""
        now = datetime.now(timezone.utc)
        # 3 verified companions, same cert level — tie-broken by rating then orders then created_at
        higher_rating = await _create_companion(
            real_name="HR",
            verification_status=VerificationStatus.verified,
            avg_rating=5.0,  # highest rating wins
            total_orders=10,
            created_at=now,
        )
        same_rating_more_orders = await _create_companion(
            real_name="MO",
            verification_status=VerificationStatus.verified,
            avg_rating=4.5,
            total_orders=999,  # more orders ties with lower rating? no — rating sorted first
            created_at=now,
        )
        same_rating_fewer_orders = await _create_companion(
            real_name="FO",
            verification_status=VerificationStatus.verified,
            avg_rating=4.5,
            total_orders=10,
            created_at=now - timedelta(days=10),  # earlier registration
        )

        resp = await authenticated_client.get("/api/v1/companions/recommendations")
        items = resp.json()["items"]
        assert items[0]["companion_id"] == str(higher_rating.id)
        # same rating: more orders wins
        assert items[1]["companion_id"] == str(same_rating_more_orders.id)
        assert items[2]["companion_id"] == str(same_rating_fewer_orders.id)

    async def test_top_k_max_3(self, authenticated_client):
        """spec §2.1 top_k 1-3 only."""
        # Add 5 verified
        for i in range(5):
            await _create_companion(
                real_name=f"C{i}",
                verification_status=VerificationStatus.verified,
                avg_rating=5.0 - i * 0.1,
            )
        # Default top_k=3
        resp = await authenticated_client.get("/api/v1/companions/recommendations")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) == 3
        assert body["total_eligible"] == 5

    async def test_top_k_explicit_1(self, authenticated_client):
        for i in range(3):
            await _create_companion(
                real_name=f"C{i}",
                verification_status=VerificationStatus.verified,
            )
        resp = await authenticated_client.get(
            "/api/v1/companions/recommendations?top_k=1"
        )
        body = resp.json()
        assert len(body["items"]) == 1

    async def test_top_k_invalid_4_returns_422(self, authenticated_client):
        """spec §2.1 max top_k=3, 422 on out-of-range."""
        resp = await authenticated_client.get(
            "/api/v1/companions/recommendations?top_k=4"
        )
        assert resp.status_code == 422

    async def test_city_filter(self, authenticated_client):
        await _create_companion(
            real_name="北京 A",
            verification_status=VerificationStatus.verified,
            service_city="北京",
        )
        await _create_companion(
            real_name="上海 A",
            verification_status=VerificationStatus.verified,
            service_city="上海",
        )
        resp = await authenticated_client.get(
            "/api/v1/companions/recommendations?city=北京"
        )
        body = resp.json()
        assert len(body["items"]) == 1
        assert body["items"][0]["service_city"] == "北京"

    async def test_requires_authentication(self, client):
        """ABAC layer 1: 未登录 403 (FastAPI Depends 默 forbidden when no Bearer)."""
        resp = await client.get("/api/v1/companions/recommendations")
        assert resp.status_code == 403

    async def test_meta_counts_transparency(self, authenticated_client):
        """spec §2.2 transparency: total_eligible + filtered_uncertified_count."""
        # 2 verified + 1 pending + 3 rejected
        for i in range(2):
            await _create_companion(
                real_name=f"V{i}",
                verification_status=VerificationStatus.verified,
            )
        await _create_companion(
            real_name="P0",
            verification_status=VerificationStatus.pending,
        )
        for i in range(3):
            await _create_companion(
                real_name=f"R{i}",
                verification_status=VerificationStatus.rejected,
            )

        resp = await authenticated_client.get("/api/v1/companions/recommendations")
        body = resp.json()
        assert body["total_eligible"] == 3  # verified + pending_supplement
        assert body["filtered_uncertified_count"] == 3  # all rejected
        assert len(body["items"]) == 3  # top3 (2 verified + 1 pending)
