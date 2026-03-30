import pytest
from app.core.security import create_access_token
from app.models.order import OrderStatus
from app.models.user import UserRole


pytestmark = pytest.mark.asyncio


class TestSubmitReview:
    async def test_submit_review_success(
        self, authenticated_client, seed_user, seed_hospital, seed_order
    ):
        patient = authenticated_client._test_user
        companion = await seed_user(phone="13700137001", role=UserRole.companion)
        hospital = await seed_hospital()
        order = await seed_order(
            patient.id,
            hospital.id,
            companion_id=companion.id,
            status=OrderStatus.completed,
        )

        resp = await authenticated_client.post(
            f"/api/v1/orders/{order.id}/review",
            json={"rating": 5, "content": "非常满意的陪诊服务！"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["rating"] == 5
        assert data["content"] == "非常满意的陪诊服务！"
        assert data["order_id"] == str(order.id)
        assert data["companion_id"] == str(companion.id)

    async def test_submit_review_transitions_to_reviewed(
        self, authenticated_client, seed_user, seed_hospital, seed_order
    ):
        patient = authenticated_client._test_user
        companion = await seed_user(phone="13700137002", role=UserRole.companion)
        hospital = await seed_hospital()
        order = await seed_order(
            patient.id,
            hospital.id,
            companion_id=companion.id,
            status=OrderStatus.completed,
        )

        await authenticated_client.post(
            f"/api/v1/orders/{order.id}/review",
            json={"rating": 4, "content": "还不错的服务体验"},
        )

        # Verify order status changed to reviewed
        resp = await authenticated_client.get(f"/api/v1/orders/{order.id}")
        assert resp.json()["status"] == "reviewed"

    async def test_submit_review_duplicate(
        self, authenticated_client, seed_user, seed_hospital, seed_order
    ):
        patient = authenticated_client._test_user
        companion = await seed_user(phone="13700137003", role=UserRole.companion)
        hospital = await seed_hospital()
        order = await seed_order(
            patient.id,
            hospital.id,
            companion_id=companion.id,
            status=OrderStatus.completed,
        )

        resp1 = await authenticated_client.post(
            f"/api/v1/orders/{order.id}/review",
            json={"rating": 5, "content": "第一次评价非常好"},
        )
        assert resp1.status_code == 201

        resp2 = await authenticated_client.post(
            f"/api/v1/orders/{order.id}/review",
            json={"rating": 3, "content": "不能再评价了吧"},
        )
        assert resp2.status_code == 400

    async def test_submit_review_not_completed(
        self, authenticated_client, seed_user, seed_hospital, seed_order
    ):
        patient = authenticated_client._test_user
        companion = await seed_user(phone="13700137004", role=UserRole.companion)
        hospital = await seed_hospital()
        order = await seed_order(
            patient.id,
            hospital.id,
            companion_id=companion.id,
            status=OrderStatus.accepted,
        )

        resp = await authenticated_client.post(
            f"/api/v1/orders/{order.id}/review",
            json={"rating": 5, "content": "还没完成就评价"},
        )
        assert resp.status_code == 400

    async def test_submit_review_not_patient(
        self, client, seed_user, seed_hospital, seed_order
    ):
        patient = await seed_user(phone="13800138010", role=UserRole.patient)
        companion = await seed_user(phone="13700137005", role=UserRole.companion)
        hospital = await seed_hospital()
        order = await seed_order(
            patient.id,
            hospital.id,
            companion_id=companion.id,
            status=OrderStatus.completed,
        )

        # Login as companion, try to review
        token = create_access_token({"sub": str(companion.id), "role": "companion"})
        client.headers["Authorization"] = f"Bearer {token}"
        resp = await client.post(
            f"/api/v1/orders/{order.id}/review",
            json={"rating": 5, "content": "陪诊师不能自评"},
        )
        assert resp.status_code == 403

    async def test_submit_review_invalid_rating(
        self, authenticated_client, seed_user, seed_hospital, seed_order
    ):
        patient = authenticated_client._test_user
        companion = await seed_user(phone="13700137006", role=UserRole.companion)
        hospital = await seed_hospital()
        order = await seed_order(
            patient.id,
            hospital.id,
            companion_id=companion.id,
            status=OrderStatus.completed,
        )

        resp = await authenticated_client.post(
            f"/api/v1/orders/{order.id}/review",
            json={"rating": 6, "content": "评分超出范围"},
        )
        assert resp.status_code == 422

    async def test_submit_review_content_too_short(
        self, authenticated_client, seed_user, seed_hospital, seed_order
    ):
        patient = authenticated_client._test_user
        companion = await seed_user(phone="13700137007", role=UserRole.companion)
        hospital = await seed_hospital()
        order = await seed_order(
            patient.id,
            hospital.id,
            companion_id=companion.id,
            status=OrderStatus.completed,
        )

        resp = await authenticated_client.post(
            f"/api/v1/orders/{order.id}/review",
            json={"rating": 5, "content": "好"},
        )
        assert resp.status_code == 422

    async def test_submit_review_order_not_found(self, authenticated_client):
        import uuid

        resp = await authenticated_client.post(
            f"/api/v1/orders/{uuid.uuid4()}/review",
            json={"rating": 5, "content": "订单不存在的评价"},
        )
        assert resp.status_code == 404


class TestGetReview:
    async def test_get_review_success(
        self, authenticated_client, seed_user, seed_hospital, seed_order, seed_review
    ):
        patient = authenticated_client._test_user
        companion = await seed_user(phone="13700137010", role=UserRole.companion)
        hospital = await seed_hospital()
        order = await seed_order(
            patient.id,
            hospital.id,
            companion_id=companion.id,
            status=OrderStatus.completed,
        )
        await seed_review(order.id, patient.id, companion.id)

        resp = await authenticated_client.get(f"/api/v1/orders/{order.id}/review")
        assert resp.status_code == 200
        assert resp.json()["rating"] == 5

    async def test_get_review_not_found(
        self, authenticated_client, seed_user, seed_hospital, seed_order
    ):
        patient = authenticated_client._test_user
        hospital = await seed_hospital()
        order = await seed_order(patient.id, hospital.id)

        resp = await authenticated_client.get(f"/api/v1/orders/{order.id}/review")
        assert resp.status_code == 404


class TestListCompanionReviews:
    async def test_list_reviews_success(
        self, authenticated_client, seed_user, seed_hospital, seed_order, seed_review
    ):
        patient = authenticated_client._test_user
        companion = await seed_user(phone="13700137020", role=UserRole.companion)
        hospital = await seed_hospital()

        # Create 2 completed orders with reviews
        for i in range(2):
            order = await seed_order(
                patient.id,
                hospital.id,
                companion_id=companion.id,
                status=OrderStatus.completed,
            )
            await seed_review(
                order.id, patient.id, companion.id, rating=4 + i, content=f"评价内容 {i}"
            )

        resp = await authenticated_client.get(
            f"/api/v1/companions/{companion.id}/reviews"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

    async def test_list_reviews_empty(
        self, authenticated_client, seed_user
    ):
        companion = await seed_user(phone="13700137021", role=UserRole.companion)
        resp = await authenticated_client.get(
            f"/api/v1/companions/{companion.id}/reviews"
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 0
        assert resp.json()["items"] == []


class TestAvgRatingDenormalization:
    async def test_submit_review_updates_avg_rating(
        self,
        authenticated_client,
        seed_user,
        seed_hospital,
        seed_order,
        seed_companion_profile,
    ):
        patient = authenticated_client._test_user
        companion = await seed_user(phone="13700137030", role=UserRole.companion)
        profile = await seed_companion_profile(companion.id)
        hospital = await seed_hospital()
        order = await seed_order(
            patient.id,
            hospital.id,
            companion_id=companion.id,
            status=OrderStatus.completed,
        )

        resp = await authenticated_client.post(
            f"/api/v1/orders/{order.id}/review",
            json={"rating": 4, "content": "评价后应更新平均分"},
        )
        assert resp.status_code == 201

        # Check companion profile via API
        resp = await authenticated_client.get(
            f"/api/v1/companions/{profile.id}",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["avg_rating"] == 4.0
        assert data["total_orders"] == 1

    async def test_multiple_reviews_avg_rating(
        self,
        client,
        seed_user,
        seed_hospital,
        seed_order,
        seed_companion_profile,
    ):
        patient1 = await seed_user(phone="13800138030", role=UserRole.patient)
        patient2 = await seed_user(phone="13800138031", role=UserRole.patient)
        companion = await seed_user(phone="13700137031", role=UserRole.companion)
        profile = await seed_companion_profile(companion.id)
        hospital = await seed_hospital()

        # First review (rating=4)
        order1 = await seed_order(
            patient1.id,
            hospital.id,
            companion_id=companion.id,
            status=OrderStatus.completed,
        )
        token1 = create_access_token({"sub": str(patient1.id), "role": "patient"})
        client.headers["Authorization"] = f"Bearer {token1}"
        resp = await client.post(
            f"/api/v1/orders/{order1.id}/review",
            json={"rating": 4, "content": "第一次评价还行的服务"},
        )
        assert resp.status_code == 201

        # Second review (rating=2)
        order2 = await seed_order(
            patient2.id,
            hospital.id,
            companion_id=companion.id,
            status=OrderStatus.completed,
        )
        token2 = create_access_token({"sub": str(patient2.id), "role": "patient"})
        client.headers["Authorization"] = f"Bearer {token2}"
        resp = await client.post(
            f"/api/v1/orders/{order2.id}/review",
            json={"rating": 2, "content": "第二次评价一般的服务"},
        )
        assert resp.status_code == 201

        # Avg should be (4+2)/2 = 3.0
        resp = await client.get(
            f"/api/v1/companions/{profile.id}",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["avg_rating"] == 3.0
        assert data["total_orders"] == 2
