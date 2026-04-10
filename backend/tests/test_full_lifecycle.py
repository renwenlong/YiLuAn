"""
Full order lifecycle tests — from create to review, including payment, cancel, and notifications.

Two types of tests:
1. TestFullOrderLifecycle — end-to-end tests covering the entire happy path and cancel path.
   If these pass, the core order pipeline is working.
2. TestStage* classes — isolated tests per stage for quick debugging when a full lifecycle test fails.
"""

import pytest

from app.core.security import create_access_token
from app.models.order import OrderStatus, ServiceType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _create_order(client, hospital_id, service_type="full_accompany", **kwargs):
    """Create an order as the current user, return order data dict."""
    payload = {
        "service_type": service_type,
        "hospital_id": str(hospital_id),
        "appointment_date": kwargs.pop("appointment_date", "2026-06-01"),
        "appointment_time": kwargs.pop("appointment_time", "09:00"),
    }
    payload.update(kwargs)
    resp = await client.post("/api/v1/orders", json=payload)
    assert resp.status_code == 201, f"Create order failed: {resp.text}"
    return resp.json()


def _switch_to_companion(client, companion_user):
    """Switch client to companion role, return saved auth header."""
    saved = client.headers.get("Authorization")
    token = create_access_token({"sub": str(companion_user.id), "role": "companion"})
    client.headers["Authorization"] = f"Bearer {token}"
    return saved


def _restore_auth(client, saved_auth):
    """Restore previously saved auth header (switch back to patient)."""
    client.headers["Authorization"] = saved_auth


# ---------------------------------------------------------------------------
# Class 1: Full Order Lifecycle
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestFullOrderLifecycle:
    async def test_complete_lifecycle_create_to_review(
        self, authenticated_client, seed_hospital, seed_user, seed_companion_profile
    ):
        """Happy path: create → pay → accept → request-start → confirm-start → complete → review."""
        hospital = await seed_hospital()
        patient = authenticated_client._test_user

        # 1. Patient creates order
        order = await _create_order(authenticated_client, hospital.id)
        order_id = order["id"]
        assert order["status"] == "created"
        assert order["price"] == 299.0
        assert order["order_number"].startswith("YLA")

        # 2. Patient pays
        resp = await authenticated_client.post(f"/api/v1/orders/{order_id}/pay")
        assert resp.status_code == 200
        pay_data = resp.json()
        assert pay_data["provider"] == "mock"
        assert pay_data["mock_success"] is True

        # Verify payment_status = paid
        resp = await authenticated_client.get(f"/api/v1/orders/{order_id}")
        assert resp.json()["payment_status"] == "paid"

        # 3. Switch to companion — accept order
        companion = await seed_user(phone="13500135200", role="companion")
        await seed_companion_profile(companion.id, real_name="测试陪诊师lifecycle")
        saved = _switch_to_companion(authenticated_client, companion)

        resp = await authenticated_client.post(f"/api/v1/orders/{order_id}/accept")
        assert resp.status_code == 200
        assert resp.json()["status"] == "accepted"
        assert resp.json()["companion_id"] is not None

        # 4. Companion requests start — status stays accepted
        resp = await authenticated_client.post(f"/api/v1/orders/{order_id}/request-start")
        assert resp.status_code == 200
        assert resp.json()["status"] == "accepted"

        # 5. Switch to patient — confirm start
        _restore_auth(authenticated_client, saved)
        resp = await authenticated_client.post(f"/api/v1/orders/{order_id}/confirm-start")
        assert resp.status_code == 200
        assert resp.json()["status"] == "in_progress"

        # 6. Switch to companion — complete
        saved = _switch_to_companion(authenticated_client, companion)
        resp = await authenticated_client.post(f"/api/v1/orders/{order_id}/complete")
        assert resp.status_code == 200
        assert resp.json()["status"] == "completed"

        # 7. Switch to patient — review
        _restore_auth(authenticated_client, saved)
        resp = await authenticated_client.post(
            f"/api/v1/orders/{order_id}/review",
            json={"rating": 5, "content": "非常满意，服务很专业"},
        )
        assert resp.status_code == 201
        review = resp.json()
        assert review["rating"] == 5
        assert review["companion_id"] == str(companion.id)

        # Verify order status is now reviewed
        resp = await authenticated_client.get(f"/api/v1/orders/{order_id}")
        assert resp.status_code == 200
        detail = resp.json()
        assert detail["status"] == "reviewed"
        assert detail["payment_status"] == "paid"

        # Verify timeline has all status records
        assert "timeline" in detail
        # History records: created, accepted, in_progress, completed (review doesn't add history)
        assert len(detail["timeline"]) >= 4

        # Verify companion profile updated (avg_rating, total_orders)
        saved = _switch_to_companion(authenticated_client, companion)
        resp = await authenticated_client.get("/api/v1/companions/me/stats")
        assert resp.status_code == 200
        stats = resp.json()
        assert stats["avg_rating"] == 5.0
        assert stats["total_orders"] >= 1
        _restore_auth(authenticated_client, saved)

        # Verify notifications sent to patient
        resp = await authenticated_client.get("/api/v1/notifications")
        assert resp.status_code == 200
        patient_notifs = resp.json()["items"]
        patient_types = [n["type"] for n in patient_notifs]
        assert "order_status_changed" in patient_types
        assert "start_service_request" in patient_types

        # Verify notifications sent to companion
        saved = _switch_to_companion(authenticated_client, companion)
        resp = await authenticated_client.get("/api/v1/notifications")
        assert resp.status_code == 200
        companion_notifs = resp.json()["items"]
        companion_types = [n["type"] for n in companion_notifs]
        assert "review_received" in companion_types
        _restore_auth(authenticated_client, saved)

    async def test_cancel_lifecycle_with_half_refund(
        self, authenticated_client, seed_hospital, seed_user, seed_companion_profile
    ):
        """Cancel path: create → pay → accept → confirm-start (in_progress) → cancel → 50% refund."""
        hospital = await seed_hospital()

        # Create & pay
        order = await _create_order(authenticated_client, hospital.id)
        order_id = order["id"]
        await authenticated_client.post(f"/api/v1/orders/{order_id}/pay")

        # Companion accepts
        companion = await seed_user(phone="13500135201", role="companion")
        await seed_companion_profile(companion.id, real_name="测试陪诊师cancel")
        saved = _switch_to_companion(authenticated_client, companion)
        resp = await authenticated_client.post(f"/api/v1/orders/{order_id}/accept")
        assert resp.status_code == 200

        # Companion starts (direct start)
        resp = await authenticated_client.post(f"/api/v1/orders/{order_id}/start")
        assert resp.status_code == 200
        assert resp.json()["status"] == "in_progress"

        # Switch to patient — cancel in_progress
        _restore_auth(authenticated_client, saved)
        resp = await authenticated_client.post(f"/api/v1/orders/{order_id}/cancel")
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled_by_patient"

        # Verify 50% refund via wallet transactions
        resp = await authenticated_client.get("/api/v1/wallet/transactions")
        assert resp.status_code == 200
        items = resp.json()["items"]
        refund_txns = [t for t in items if t["payment_type"] == "refund"]
        assert len(refund_txns) == 1
        assert refund_txns[0]["amount"] == 149.5  # 50% of 299.0

        # Verify order payment_status = refunded
        resp = await authenticated_client.get(f"/api/v1/orders/{order_id}")
        assert resp.status_code == 200
        assert resp.json()["payment_status"] == "refunded"


# ---------------------------------------------------------------------------
# Class 2: Stage 1 — Create Order
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestStage1_CreateOrder:
    async def test_create_success(self, authenticated_client, seed_hospital):
        hospital = await seed_hospital()
        order = await _create_order(authenticated_client, hospital.id)
        assert order["status"] == "created"
        assert order["price"] == 299.0
        assert order["order_number"].startswith("YLA")
        assert order["hospital_name"] == "测试医院"

    async def test_create_all_service_types(self, authenticated_client, seed_hospital, seed_payment):
        hospital = await seed_hospital()
        user = authenticated_client._test_user

        # full_accompany = 299
        order1 = await _create_order(authenticated_client, hospital.id, service_type="full_accompany")
        assert order1["price"] == 299.0
        # Pay so next order isn't blocked
        await authenticated_client.post(f"/api/v1/orders/{order1['id']}/pay")

        # half_accompany = 199
        order2 = await _create_order(authenticated_client, hospital.id, service_type="half_accompany")
        assert order2["price"] == 199.0
        await authenticated_client.post(f"/api/v1/orders/{order2['id']}/pay")

        # errand = 149
        order3 = await _create_order(authenticated_client, hospital.id, service_type="errand")
        assert order3["price"] == 149.0

    async def test_create_blocked_by_unpaid(self, authenticated_client, seed_hospital):
        hospital = await seed_hospital()
        # First order (unpaid)
        await _create_order(authenticated_client, hospital.id)
        # Second order should fail
        resp = await authenticated_client.post(
            "/api/v1/orders",
            json={
                "service_type": "full_accompany",
                "hospital_id": str(hospital.id),
                "appointment_date": "2026-06-02",
                "appointment_time": "10:00",
            },
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Class 3: Stage 2 — Payment
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestStage2_Payment:
    async def test_pay_success(self, authenticated_client, seed_hospital):
        hospital = await seed_hospital()
        order = await _create_order(authenticated_client, hospital.id)
        resp = await authenticated_client.post(f"/api/v1/orders/{order['id']}/pay")
        assert resp.status_code == 200
        data = resp.json()
        assert data["provider"] == "mock"
        assert data["mock_success"] is True

    async def test_pay_duplicate_rejected(self, authenticated_client, seed_hospital):
        hospital = await seed_hospital()
        order = await _create_order(authenticated_client, hospital.id)
        await authenticated_client.post(f"/api/v1/orders/{order['id']}/pay")
        resp = await authenticated_client.post(f"/api/v1/orders/{order['id']}/pay")
        assert resp.status_code == 400

    async def test_order_payment_status_after_pay(self, authenticated_client, seed_hospital):
        hospital = await seed_hospital()
        order = await _create_order(authenticated_client, hospital.id)

        # Before pay
        resp = await authenticated_client.get(f"/api/v1/orders/{order['id']}")
        assert resp.json()["payment_status"] == "unpaid"

        # After pay
        await authenticated_client.post(f"/api/v1/orders/{order['id']}/pay")
        resp = await authenticated_client.get(f"/api/v1/orders/{order['id']}")
        assert resp.json()["payment_status"] == "paid"


# ---------------------------------------------------------------------------
# Class 4: Stage 3 — Accept
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestStage3_Accept:
    async def test_accept_success(
        self, authenticated_client, seed_hospital, seed_user, seed_companion_profile
    ):
        hospital = await seed_hospital()
        order = await _create_order(authenticated_client, hospital.id)

        companion = await seed_user(phone="13500135300", role="companion")
        await seed_companion_profile(companion.id)
        saved = _switch_to_companion(authenticated_client, companion)
        resp = await authenticated_client.post(f"/api/v1/orders/{order['id']}/accept")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "accepted"
        assert data["companion_id"] is not None
        _restore_auth(authenticated_client, saved)

    async def test_accept_requires_companion_role(self, authenticated_client, seed_hospital):
        hospital = await seed_hospital()
        order = await _create_order(authenticated_client, hospital.id)
        # Patient tries to accept — should fail
        resp = await authenticated_client.post(f"/api/v1/orders/{order['id']}/accept")
        assert resp.status_code == 403

    async def test_accept_only_created_status(
        self, authenticated_client, seed_hospital, seed_user, seed_order, seed_companion_profile
    ):
        """Cannot accept an order that is already accepted."""
        user = authenticated_client._test_user
        companion = await seed_user(phone="13500135301", role="companion")
        await seed_companion_profile(companion.id)
        hospital = await seed_hospital()
        order = await seed_order(
            user.id, hospital.id, companion_id=companion.id, status=OrderStatus.accepted
        )
        saved = _switch_to_companion(authenticated_client, companion)
        resp = await authenticated_client.post(f"/api/v1/orders/{order.id}/accept")
        assert resp.status_code == 400
        _restore_auth(authenticated_client, saved)


# ---------------------------------------------------------------------------
# Class 5: Stage 4 — Start Service
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestStage4_StartService:
    async def test_request_start_no_state_change(
        self, authenticated_client, seed_hospital, seed_user, seed_order, seed_companion_profile
    ):
        user = authenticated_client._test_user
        companion = await seed_user(phone="13500135400", role="companion")
        await seed_companion_profile(companion.id)
        hospital = await seed_hospital()
        order = await seed_order(
            user.id, hospital.id, companion_id=companion.id, status=OrderStatus.accepted
        )
        saved = _switch_to_companion(authenticated_client, companion)
        resp = await authenticated_client.post(f"/api/v1/orders/{order.id}/request-start")
        assert resp.status_code == 200
        assert resp.json()["status"] == "accepted"  # no state change
        _restore_auth(authenticated_client, saved)

    async def test_confirm_start_by_patient(
        self, authenticated_client, seed_hospital, seed_user, seed_order, seed_companion_profile
    ):
        user = authenticated_client._test_user
        companion = await seed_user(phone="13500135401", role="companion")
        await seed_companion_profile(companion.id)
        hospital = await seed_hospital()
        order = await seed_order(
            user.id, hospital.id, companion_id=companion.id, status=OrderStatus.accepted
        )
        resp = await authenticated_client.post(f"/api/v1/orders/{order.id}/confirm-start")
        assert resp.status_code == 200
        assert resp.json()["status"] == "in_progress"

    async def test_direct_start_by_companion(
        self, authenticated_client, seed_hospital, seed_user, seed_order, seed_companion_profile
    ):
        user = authenticated_client._test_user
        companion = await seed_user(phone="13500135402", role="companion")
        await seed_companion_profile(companion.id)
        hospital = await seed_hospital()
        order = await seed_order(
            user.id, hospital.id, companion_id=companion.id, status=OrderStatus.accepted
        )
        saved = _switch_to_companion(authenticated_client, companion)
        resp = await authenticated_client.post(f"/api/v1/orders/{order.id}/start")
        assert resp.status_code == 200
        assert resp.json()["status"] == "in_progress"
        _restore_auth(authenticated_client, saved)

    async def test_confirm_start_requires_patient(
        self, authenticated_client, seed_hospital, seed_user, seed_order, seed_companion_profile
    ):
        """Companion cannot call confirm-start — only patient can."""
        user = authenticated_client._test_user
        companion = await seed_user(phone="13500135403", role="companion")
        await seed_companion_profile(companion.id)
        hospital = await seed_hospital()
        order = await seed_order(
            user.id, hospital.id, companion_id=companion.id, status=OrderStatus.accepted
        )
        saved = _switch_to_companion(authenticated_client, companion)
        resp = await authenticated_client.post(f"/api/v1/orders/{order.id}/confirm-start")
        assert resp.status_code == 403
        _restore_auth(authenticated_client, saved)


# ---------------------------------------------------------------------------
# Class 6: Stage 5 — Complete
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestStage5_Complete:
    async def test_complete_success(
        self, authenticated_client, seed_hospital, seed_user, seed_order, seed_companion_profile
    ):
        user = authenticated_client._test_user
        companion = await seed_user(phone="13500135500", role="companion")
        await seed_companion_profile(companion.id)
        hospital = await seed_hospital()
        order = await seed_order(
            user.id, hospital.id, companion_id=companion.id, status=OrderStatus.in_progress
        )
        saved = _switch_to_companion(authenticated_client, companion)
        resp = await authenticated_client.post(f"/api/v1/orders/{order.id}/complete")
        assert resp.status_code == 200
        assert resp.json()["status"] == "completed"
        _restore_auth(authenticated_client, saved)

    async def test_complete_requires_in_progress(
        self, authenticated_client, seed_hospital, seed_user, seed_order, seed_companion_profile
    ):
        user = authenticated_client._test_user
        companion = await seed_user(phone="13500135501", role="companion")
        await seed_companion_profile(companion.id)
        hospital = await seed_hospital()
        order = await seed_order(
            user.id, hospital.id, companion_id=companion.id, status=OrderStatus.accepted
        )
        saved = _switch_to_companion(authenticated_client, companion)
        resp = await authenticated_client.post(f"/api/v1/orders/{order.id}/complete")
        assert resp.status_code == 400
        _restore_auth(authenticated_client, saved)


# ---------------------------------------------------------------------------
# Class 7: Stage 6 — Review
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestStage6_Review:
    async def test_review_success(
        self, authenticated_client, seed_hospital, seed_user, seed_order, seed_companion_profile
    ):
        user = authenticated_client._test_user
        companion = await seed_user(phone="13500135600", role="companion")
        await seed_companion_profile(companion.id)
        hospital = await seed_hospital()
        order = await seed_order(
            user.id, hospital.id, companion_id=companion.id, status=OrderStatus.completed
        )
        resp = await authenticated_client.post(
            f"/api/v1/orders/{order.id}/review",
            json={"rating": 5, "content": "非常满意，陪诊师很专业"},
        )
        assert resp.status_code == 201
        review = resp.json()
        assert review["rating"] == 5
        assert review["companion_id"] == str(companion.id)

        # Verify order transitioned to reviewed
        resp = await authenticated_client.get(f"/api/v1/orders/{order.id}")
        assert resp.json()["status"] == "reviewed"

    async def test_review_updates_companion_profile(
        self, authenticated_client, seed_hospital, seed_user, seed_order, seed_companion_profile
    ):
        user = authenticated_client._test_user
        companion = await seed_user(phone="13500135601", role="companion")
        await seed_companion_profile(companion.id)
        hospital = await seed_hospital()
        order = await seed_order(
            user.id, hospital.id, companion_id=companion.id, status=OrderStatus.completed
        )
        await authenticated_client.post(
            f"/api/v1/orders/{order.id}/review",
            json={"rating": 4, "content": "服务还不错，比较满意"},
        )

        # Check companion stats
        saved = _switch_to_companion(authenticated_client, companion)
        resp = await authenticated_client.get("/api/v1/companions/me/stats")
        assert resp.status_code == 200
        stats = resp.json()
        assert stats["avg_rating"] == 4.0
        assert stats["total_orders"] >= 1
        _restore_auth(authenticated_client, saved)

    async def test_review_duplicate_rejected(
        self, authenticated_client, seed_hospital, seed_user, seed_order, seed_companion_profile
    ):
        user = authenticated_client._test_user
        companion = await seed_user(phone="13500135602", role="companion")
        await seed_companion_profile(companion.id)
        hospital = await seed_hospital()
        order = await seed_order(
            user.id, hospital.id, companion_id=companion.id, status=OrderStatus.completed
        )
        # First review succeeds
        resp = await authenticated_client.post(
            f"/api/v1/orders/{order.id}/review",
            json={"rating": 5, "content": "很好的服务体验！"},
        )
        assert resp.status_code == 201
        # Second review fails
        resp = await authenticated_client.post(
            f"/api/v1/orders/{order.id}/review",
            json={"rating": 3, "content": "再评一次试试看"},
        )
        assert resp.status_code == 400

    async def test_review_requires_completed(
        self, authenticated_client, seed_hospital, seed_user, seed_order, seed_companion_profile
    ):
        user = authenticated_client._test_user
        companion = await seed_user(phone="13500135603", role="companion")
        await seed_companion_profile(companion.id)
        hospital = await seed_hospital()
        order = await seed_order(
            user.id, hospital.id, companion_id=companion.id, status=OrderStatus.in_progress
        )
        resp = await authenticated_client.post(
            f"/api/v1/orders/{order.id}/review",
            json={"rating": 5, "content": "想提前评价一下"},
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Class 8: Stage 7 — Cancel & Refund
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestStage7_Cancel:
    async def test_cancel_created_no_refund(
        self, authenticated_client, seed_hospital
    ):
        """Cancel created order without payment — no refund record."""
        hospital = await seed_hospital()
        order = await _create_order(authenticated_client, hospital.id)
        resp = await authenticated_client.post(f"/api/v1/orders/{order['id']}/cancel")
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled_by_patient"

    async def test_cancel_created_paid_full_refund(
        self, authenticated_client, seed_hospital
    ):
        """Cancel created+paid order — full (100%) refund."""
        hospital = await seed_hospital()
        order = await _create_order(authenticated_client, hospital.id)
        await authenticated_client.post(f"/api/v1/orders/{order['id']}/pay")

        resp = await authenticated_client.post(f"/api/v1/orders/{order['id']}/cancel")
        assert resp.status_code == 200

        # Verify full refund
        resp = await authenticated_client.get(f"/api/v1/orders/{order['id']}")
        assert resp.json()["payment_status"] == "refunded"

        # Verify refund amount = 100%
        resp = await authenticated_client.get("/api/v1/wallet/transactions")
        refunds = [t for t in resp.json()["items"] if t["payment_type"] == "refund"]
        assert len(refunds) == 1
        assert refunds[0]["amount"] == 299.0

    async def test_cancel_accepted_paid_full_refund(
        self, authenticated_client, seed_hospital, seed_user, seed_companion_profile
    ):
        """Cancel accepted+paid order — full (100%) refund."""
        hospital = await seed_hospital()
        order = await _create_order(authenticated_client, hospital.id)
        await authenticated_client.post(f"/api/v1/orders/{order['id']}/pay")

        # Companion accepts
        companion = await seed_user(phone="13500135700", role="companion")
        await seed_companion_profile(companion.id)
        saved = _switch_to_companion(authenticated_client, companion)
        await authenticated_client.post(f"/api/v1/orders/{order['id']}/accept")
        _restore_auth(authenticated_client, saved)

        # Patient cancels
        resp = await authenticated_client.post(f"/api/v1/orders/{order['id']}/cancel")
        assert resp.status_code == 200

        resp = await authenticated_client.get("/api/v1/wallet/transactions")
        refunds = [t for t in resp.json()["items"] if t["payment_type"] == "refund"]
        assert len(refunds) == 1
        assert refunds[0]["amount"] == 299.0  # 100% refund for accepted

    async def test_cancel_in_progress_paid_half_refund(
        self, authenticated_client, seed_hospital, seed_user, seed_companion_profile
    ):
        """Cancel in_progress+paid order — 50% refund."""
        hospital = await seed_hospital()
        order = await _create_order(authenticated_client, hospital.id)
        await authenticated_client.post(f"/api/v1/orders/{order['id']}/pay")

        # Companion accepts and starts
        companion = await seed_user(phone="13500135701", role="companion")
        await seed_companion_profile(companion.id)
        saved = _switch_to_companion(authenticated_client, companion)
        await authenticated_client.post(f"/api/v1/orders/{order['id']}/accept")
        await authenticated_client.post(f"/api/v1/orders/{order['id']}/start")
        _restore_auth(authenticated_client, saved)

        # Patient cancels in_progress
        resp = await authenticated_client.post(f"/api/v1/orders/{order['id']}/cancel")
        assert resp.status_code == 200

        resp = await authenticated_client.get("/api/v1/wallet/transactions")
        refunds = [t for t in resp.json()["items"] if t["payment_type"] == "refund"]
        assert len(refunds) == 1
        assert refunds[0]["amount"] == 149.5  # 50% of 299


# ---------------------------------------------------------------------------
# Class 9: Stage 8 — Notifications
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestStage8_Notifications:
    async def test_accept_sends_notification(
        self, authenticated_client, seed_hospital, seed_user, seed_companion_profile
    ):
        hospital = await seed_hospital()
        order = await _create_order(authenticated_client, hospital.id)

        companion = await seed_user(phone="13500135800", role="companion")
        await seed_companion_profile(companion.id)
        saved = _switch_to_companion(authenticated_client, companion)
        await authenticated_client.post(f"/api/v1/orders/{order['id']}/accept")
        _restore_auth(authenticated_client, saved)

        # Patient should have order_status_changed notification
        resp = await authenticated_client.get("/api/v1/notifications")
        assert resp.status_code == 200
        types = [n["type"] for n in resp.json()["items"]]
        assert "order_status_changed" in types

    async def test_request_start_sends_notification(
        self, authenticated_client, seed_hospital, seed_user, seed_order, seed_companion_profile
    ):
        user = authenticated_client._test_user
        companion = await seed_user(phone="13500135801", role="companion")
        await seed_companion_profile(companion.id)
        hospital = await seed_hospital()
        order = await seed_order(
            user.id, hospital.id, companion_id=companion.id, status=OrderStatus.accepted
        )

        saved = _switch_to_companion(authenticated_client, companion)
        await authenticated_client.post(f"/api/v1/orders/{order.id}/request-start")
        _restore_auth(authenticated_client, saved)

        resp = await authenticated_client.get("/api/v1/notifications")
        types = [n["type"] for n in resp.json()["items"]]
        assert "start_service_request" in types

    async def test_complete_sends_notification(
        self, authenticated_client, seed_hospital, seed_user, seed_order, seed_companion_profile
    ):
        user = authenticated_client._test_user
        companion = await seed_user(phone="13500135802", role="companion")
        await seed_companion_profile(companion.id)
        hospital = await seed_hospital()
        order = await seed_order(
            user.id, hospital.id, companion_id=companion.id, status=OrderStatus.in_progress
        )

        saved = _switch_to_companion(authenticated_client, companion)
        await authenticated_client.post(f"/api/v1/orders/{order.id}/complete")
        _restore_auth(authenticated_client, saved)

        resp = await authenticated_client.get("/api/v1/notifications")
        types = [n["type"] for n in resp.json()["items"]]
        assert "order_status_changed" in types

    async def test_review_sends_notification(
        self, authenticated_client, seed_hospital, seed_user, seed_order, seed_companion_profile
    ):
        user = authenticated_client._test_user
        companion = await seed_user(phone="13500135803", role="companion")
        await seed_companion_profile(companion.id)
        hospital = await seed_hospital()
        order = await seed_order(
            user.id, hospital.id, companion_id=companion.id, status=OrderStatus.completed
        )

        # Patient submits review
        await authenticated_client.post(
            f"/api/v1/orders/{order.id}/review",
            json={"rating": 5, "content": "测试通知是否发送正确"},
        )

        # Companion should receive review_received notification
        saved = _switch_to_companion(authenticated_client, companion)
        resp = await authenticated_client.get("/api/v1/notifications")
        types = [n["type"] for n in resp.json()["items"]]
        assert "review_received" in types
        _restore_auth(authenticated_client, saved)
