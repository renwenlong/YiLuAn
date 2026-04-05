import uuid

import pytest

from app.models.order import OrderStatus, ServiceType


@pytest.mark.asyncio
class TestCreateOrder:
    async def test_create_order_success(self, authenticated_client, seed_hospital):
        hospital = await seed_hospital()
        resp = await authenticated_client.post(
            "/api/v1/orders",
            json={
                "service_type": "full_accompany",
                "hospital_id": str(hospital.id),
                "appointment_date": "2026-05-01",
                "appointment_time": "09:00",
                "description": "需要全程陪诊",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "created"
        assert data["price"] == 299.0
        assert data["service_type"] == "full_accompany"
        assert data["hospital_name"] == "测试医院"
        assert data["order_number"].startswith("YLA")

    async def test_create_order_half_accompany(
        self, authenticated_client, seed_hospital
    ):
        hospital = await seed_hospital()
        resp = await authenticated_client.post(
            "/api/v1/orders",
            json={
                "service_type": "half_accompany",
                "hospital_id": str(hospital.id),
                "appointment_date": "2026-05-01",
                "appointment_time": "14:00",
            },
        )
        assert resp.status_code == 201
        assert resp.json()["price"] == 199.0

    async def test_create_order_errand(self, authenticated_client, seed_hospital):
        hospital = await seed_hospital()
        resp = await authenticated_client.post(
            "/api/v1/orders",
            json={
                "service_type": "errand",
                "hospital_id": str(hospital.id),
                "appointment_date": "2026-05-01",
                "appointment_time": "10:00",
            },
        )
        assert resp.status_code == 201
        assert resp.json()["price"] == 149.0

    async def test_create_order_invalid_service_type(
        self, authenticated_client, seed_hospital
    ):
        hospital = await seed_hospital()
        resp = await authenticated_client.post(
            "/api/v1/orders",
            json={
                "service_type": "invalid",
                "hospital_id": str(hospital.id),
                "appointment_date": "2026-05-01",
                "appointment_time": "09:00",
            },
        )
        assert resp.status_code == 422

    async def test_create_order_hospital_not_found(self, authenticated_client):
        resp = await authenticated_client.post(
            "/api/v1/orders",
            json={
                "service_type": "full_accompany",
                "hospital_id": str(uuid.uuid4()),
                "appointment_date": "2026-05-01",
                "appointment_time": "09:00",
            },
        )
        assert resp.status_code == 404

    async def test_create_order_no_auth(self, client, seed_hospital):
        hospital = await seed_hospital()
        resp = await client.post(
            "/api/v1/orders",
            json={
                "service_type": "full_accompany",
                "hospital_id": str(hospital.id),
                "appointment_date": "2026-05-01",
                "appointment_time": "09:00",
            },
        )
        assert resp.status_code in (401, 403)

    async def test_create_order_invalid_date_format(
        self, authenticated_client, seed_hospital
    ):
        hospital = await seed_hospital()
        resp = await authenticated_client.post(
            "/api/v1/orders",
            json={
                "service_type": "full_accompany",
                "hospital_id": str(hospital.id),
                "appointment_date": "05/01/2026",
                "appointment_time": "09:00",
            },
        )
        assert resp.status_code == 422


@pytest.mark.asyncio
class TestListOrders:
    async def test_list_orders_empty(self, authenticated_client):
        resp = await authenticated_client.get("/api/v1/orders")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    async def test_list_orders_patient(
        self, authenticated_client, seed_hospital, seed_order
    ):
        user = authenticated_client._test_user
        hospital = await seed_hospital()
        await seed_order(user.id, hospital.id)
        await seed_order(user.id, hospital.id)
        resp = await authenticated_client.get("/api/v1/orders")
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

    async def test_list_orders_filter_status(
        self, authenticated_client, seed_hospital, seed_order, seed_user
    ):
        user = authenticated_client._test_user
        hospital = await seed_hospital()
        companion = await seed_user(phone="13600136099", role="companion")
        await seed_order(user.id, hospital.id, status=OrderStatus.created)
        await seed_order(
            user.id,
            hospital.id,
            status=OrderStatus.accepted,
            companion_id=companion.id,
        )
        resp = await authenticated_client.get("/api/v1/orders?status=created")
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["status"] == "created"


@pytest.mark.asyncio
class TestGetOrder:
    async def test_get_order_detail(
        self, authenticated_client, seed_hospital, seed_order
    ):
        user = authenticated_client._test_user
        hospital = await seed_hospital()
        order = await seed_order(user.id, hospital.id)
        resp = await authenticated_client.get(f"/api/v1/orders/{order.id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == str(order.id)

    async def test_get_order_not_found(self, authenticated_client):
        resp = await authenticated_client.get(f"/api/v1/orders/{uuid.uuid4()}")
        assert resp.status_code == 404

    async def test_get_other_patient_order(
        self, authenticated_client, seed_hospital, seed_order, seed_user
    ):
        other = await seed_user(phone="13500135000")
        hospital = await seed_hospital()
        order = await seed_order(other.id, hospital.id)
        resp = await authenticated_client.get(f"/api/v1/orders/{order.id}")
        assert resp.status_code == 403


@pytest.mark.asyncio
class TestOrderStateMachine:
    async def test_accept_order(
        self, companion_client, seed_hospital, seed_order, seed_user
    ):
        patient = await seed_user(phone="13500135010")
        hospital = await seed_hospital()
        order = await seed_order(patient.id, hospital.id)
        resp = await companion_client.post(f"/api/v1/orders/{order.id}/accept")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "accepted"
        assert data["companion_id"] is not None

    async def test_start_order(
        self, companion_client, seed_hospital, seed_order, seed_user
    ):
        patient = await seed_user(phone="13500135001")
        companion = companion_client._test_user
        hospital = await seed_hospital()
        order = await seed_order(
            patient.id,
            hospital.id,
            companion_id=companion.id,
            status=OrderStatus.accepted,
        )
        resp = await companion_client.post(f"/api/v1/orders/{order.id}/start")
        assert resp.status_code == 200
        assert resp.json()["status"] == "in_progress"

    async def test_complete_order(
        self, companion_client, seed_hospital, seed_order, seed_user
    ):
        patient = await seed_user(phone="13500135002")
        companion = companion_client._test_user
        hospital = await seed_hospital()
        order = await seed_order(
            patient.id,
            hospital.id,
            companion_id=companion.id,
            status=OrderStatus.in_progress,
        )
        resp = await companion_client.post(f"/api/v1/orders/{order.id}/complete")
        assert resp.status_code == 200
        assert resp.json()["status"] == "completed"

    async def test_cancel_by_patient(
        self, authenticated_client, seed_hospital, seed_order
    ):
        user = authenticated_client._test_user
        hospital = await seed_hospital()
        order = await seed_order(user.id, hospital.id)
        resp = await authenticated_client.post(f"/api/v1/orders/{order.id}/cancel")
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled_by_patient"

    async def test_cancel_by_companion(
        self, companion_client, seed_hospital, seed_order, seed_user
    ):
        patient = await seed_user(phone="13500135003")
        companion = companion_client._test_user
        hospital = await seed_hospital()
        order = await seed_order(
            patient.id,
            hospital.id,
            companion_id=companion.id,
            status=OrderStatus.accepted,
        )
        resp = await companion_client.post(f"/api/v1/orders/{order.id}/cancel")
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled_by_companion"

    async def test_invalid_transition_accept_in_progress(
        self, companion_client, seed_hospital, seed_order, seed_user
    ):
        patient = await seed_user(phone="13500135004")
        companion = companion_client._test_user
        hospital = await seed_hospital()
        order = await seed_order(
            patient.id,
            hospital.id,
            companion_id=companion.id,
            status=OrderStatus.in_progress,
        )
        resp = await companion_client.post(f"/api/v1/orders/{order.id}/accept")
        assert resp.status_code == 400

    async def test_invalid_transition_complete_created(
        self, companion_client, seed_hospital, seed_order, seed_user
    ):
        patient = await seed_user(phone="13500135005")
        companion = companion_client._test_user
        hospital = await seed_hospital()
        order = await seed_order(
            patient.id,
            hospital.id,
            companion_id=companion.id,
            status=OrderStatus.created,
        )
        resp = await companion_client.post(f"/api/v1/orders/{order.id}/complete")
        assert resp.status_code == 400

    async def test_cannot_cancel_completed(
        self, authenticated_client, seed_hospital, seed_order, seed_user
    ):
        user = authenticated_client._test_user
        companion = await seed_user(phone="13500135006", role="companion")
        hospital = await seed_hospital()
        order = await seed_order(
            user.id,
            hospital.id,
            companion_id=companion.id,
            status=OrderStatus.completed,
        )
        resp = await authenticated_client.post(f"/api/v1/orders/{order.id}/cancel")
        assert resp.status_code == 400

    async def test_patient_cannot_accept(
        self, authenticated_client, seed_hospital, seed_order
    ):
        user = authenticated_client._test_user
        hospital = await seed_hospital()
        order = await seed_order(user.id, hospital.id)
        resp = await authenticated_client.post(f"/api/v1/orders/{order.id}/accept")
        assert resp.status_code == 403

    async def test_request_start_by_companion(
        self, companion_client, seed_hospital, seed_order, seed_user
    ):
        """Companion can request start — no status change, just notification."""
        patient = await seed_user(phone="13500135040")
        companion = companion_client._test_user
        hospital = await seed_hospital()
        order = await seed_order(
            patient.id,
            hospital.id,
            companion_id=companion.id,
            status=OrderStatus.accepted,
        )
        resp = await companion_client.post(
            f"/api/v1/orders/{order.id}/request-start"
        )
        assert resp.status_code == 200
        # Status should stay accepted (notification only)
        assert resp.json()["status"] == "accepted"

    async def test_request_start_wrong_companion(
        self, companion_client, seed_hospital, seed_order, seed_user
    ):
        """Only the assigned companion can request start."""
        patient = await seed_user(phone="13500135041")
        other_companion = await seed_user(phone="13500135042", role="companion")
        hospital = await seed_hospital()
        order = await seed_order(
            patient.id,
            hospital.id,
            companion_id=other_companion.id,
            status=OrderStatus.accepted,
        )
        resp = await companion_client.post(
            f"/api/v1/orders/{order.id}/request-start"
        )
        assert resp.status_code == 403

    async def test_request_start_wrong_status(
        self, companion_client, seed_hospital, seed_order, seed_user
    ):
        """Cannot request start when order is not accepted."""
        patient = await seed_user(phone="13500135043")
        companion = companion_client._test_user
        hospital = await seed_hospital()
        order = await seed_order(
            patient.id,
            hospital.id,
            companion_id=companion.id,
            status=OrderStatus.in_progress,
        )
        resp = await companion_client.post(
            f"/api/v1/orders/{order.id}/request-start"
        )
        assert resp.status_code == 400

    async def test_confirm_start_by_patient(
        self, authenticated_client, seed_hospital, seed_order, seed_user
    ):
        """Patient confirms start — order transitions accepted → in_progress."""
        user = authenticated_client._test_user
        companion = await seed_user(phone="13500135044", role="companion")
        hospital = await seed_hospital()
        order = await seed_order(
            user.id,
            hospital.id,
            companion_id=companion.id,
            status=OrderStatus.accepted,
        )
        resp = await authenticated_client.post(
            f"/api/v1/orders/{order.id}/confirm-start"
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "in_progress"

    async def test_confirm_start_wrong_patient(
        self, authenticated_client, seed_hospital, seed_order, seed_user
    ):
        """Only the order's patient can confirm start."""
        other_patient = await seed_user(phone="13500135045")
        companion = await seed_user(phone="13500135046", role="companion")
        hospital = await seed_hospital()
        order = await seed_order(
            other_patient.id,
            hospital.id,
            companion_id=companion.id,
            status=OrderStatus.accepted,
        )
        resp = await authenticated_client.post(
            f"/api/v1/orders/{order.id}/confirm-start"
        )
        assert resp.status_code == 403

    async def test_confirm_start_wrong_status(
        self, authenticated_client, seed_hospital, seed_order, seed_user
    ):
        """Cannot confirm start when order is not accepted."""
        user = authenticated_client._test_user
        companion = await seed_user(phone="13500135047", role="companion")
        hospital = await seed_hospital()
        order = await seed_order(
            user.id,
            hospital.id,
            companion_id=companion.id,
            status=OrderStatus.created,
        )
        resp = await authenticated_client.post(
            f"/api/v1/orders/{order.id}/confirm-start"
        )
        assert resp.status_code == 400

    async def test_patient_cannot_request_start(
        self, authenticated_client, seed_hospital, seed_order, seed_user
    ):
        """Patient cannot call request-start (companion-only action)."""
        user = authenticated_client._test_user
        companion = await seed_user(phone="13500135048", role="companion")
        hospital = await seed_hospital()
        order = await seed_order(
            user.id,
            hospital.id,
            companion_id=companion.id,
            status=OrderStatus.accepted,
        )
        resp = await authenticated_client.post(
            f"/api/v1/orders/{order.id}/request-start"
        )
        assert resp.status_code == 403

    async def test_full_lifecycle(
        self, authenticated_client, seed_hospital, seed_user
    ):
        hospital = await seed_hospital()
        # Create order as patient
        resp = await authenticated_client.post(
            "/api/v1/orders",
            json={
                "service_type": "full_accompany",
                "hospital_id": str(hospital.id),
                "appointment_date": "2026-06-01",
                "appointment_time": "10:00",
            },
        )
        assert resp.status_code == 201
        order_id = resp.json()["id"]

        # Switch to companion — reuse same client with different token
        from app.core.security import create_access_token

        companion = await seed_user(phone="13500135099", role="companion")
        companion_token = create_access_token(
            {"sub": str(companion.id), "role": "companion"}
        )
        saved_auth = authenticated_client.headers.get("Authorization")
        authenticated_client.headers["Authorization"] = f"Bearer {companion_token}"

        # Accept
        resp = await authenticated_client.post(f"/api/v1/orders/{order_id}/accept")
        assert resp.status_code == 200
        assert resp.json()["status"] == "accepted"
        # Start
        resp = await authenticated_client.post(f"/api/v1/orders/{order_id}/start")
        assert resp.status_code == 200
        assert resp.json()["status"] == "in_progress"
        # Complete
        resp = await authenticated_client.post(f"/api/v1/orders/{order_id}/complete")
        assert resp.status_code == 200
        assert resp.json()["status"] == "completed"

        # Restore patient token
        authenticated_client.headers["Authorization"] = saved_auth

    async def test_full_lifecycle_with_confirm_start(
        self, authenticated_client, seed_hospital, seed_user
    ):
        """Full lifecycle using request-start + confirm-start flow."""
        hospital = await seed_hospital()
        from app.core.security import create_access_token

        # Create order as patient
        resp = await authenticated_client.post(
            "/api/v1/orders",
            json={
                "service_type": "full_accompany",
                "hospital_id": str(hospital.id),
                "appointment_date": "2026-06-01",
                "appointment_time": "11:00",
            },
        )
        assert resp.status_code == 201
        order_id = resp.json()["id"]

        # Switch to companion
        companion = await seed_user(phone="13500135098", role="companion")
        companion_token = create_access_token(
            {"sub": str(companion.id), "role": "companion"}
        )
        saved_auth = authenticated_client.headers.get("Authorization")
        authenticated_client.headers["Authorization"] = f"Bearer {companion_token}"

        # Accept
        resp = await authenticated_client.post(f"/api/v1/orders/{order_id}/accept")
        assert resp.status_code == 200
        assert resp.json()["status"] == "accepted"

        # Companion requests start — status stays accepted
        resp = await authenticated_client.post(
            f"/api/v1/orders/{order_id}/request-start"
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "accepted"

        # Switch back to patient
        authenticated_client.headers["Authorization"] = saved_auth

        # Patient confirms start — status becomes in_progress
        resp = await authenticated_client.post(
            f"/api/v1/orders/{order_id}/confirm-start"
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "in_progress"

        # Switch to companion for completion
        authenticated_client.headers["Authorization"] = f"Bearer {companion_token}"
        resp = await authenticated_client.post(
            f"/api/v1/orders/{order_id}/complete"
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "completed"

        # Restore patient token
        authenticated_client.headers["Authorization"] = saved_auth


@pytest.mark.asyncio
class TestPayment:
    async def test_pay_order(self, authenticated_client, seed_hospital, seed_order):
        user = authenticated_client._test_user
        hospital = await seed_hospital()
        order = await seed_order(user.id, hospital.id)
        resp = await authenticated_client.post(f"/api/v1/orders/{order.id}/pay")
        assert resp.status_code == 200
        data = resp.json()
        assert data["payment_type"] == "pay"
        assert data["amount"] == 299.0
        assert data["status"] == "success"

    async def test_pay_order_duplicate(
        self, authenticated_client, seed_hospital, seed_order
    ):
        user = authenticated_client._test_user
        hospital = await seed_hospital()
        order = await seed_order(user.id, hospital.id)
        await authenticated_client.post(f"/api/v1/orders/{order.id}/pay")
        resp = await authenticated_client.post(f"/api/v1/orders/{order.id}/pay")
        assert resp.status_code == 400

    async def test_pay_cancelled_order(
        self, authenticated_client, seed_hospital, seed_order
    ):
        user = authenticated_client._test_user
        hospital = await seed_hospital()
        order = await seed_order(
            user.id, hospital.id, status=OrderStatus.cancelled_by_patient
        )
        resp = await authenticated_client.post(f"/api/v1/orders/{order.id}/pay")
        assert resp.status_code == 400

    async def test_refund_cancelled_order(
        self, authenticated_client, seed_hospital, seed_order
    ):
        user = authenticated_client._test_user
        hospital = await seed_hospital()
        order = await seed_order(user.id, hospital.id)
        # Pay first
        await authenticated_client.post(f"/api/v1/orders/{order.id}/pay")
        # Cancel — should auto-refund
        await authenticated_client.post(f"/api/v1/orders/{order.id}/cancel")
        # Manual refund should fail (already refunded by auto-refund)
        resp = await authenticated_client.post(f"/api/v1/orders/{order.id}/refund")
        assert resp.status_code == 400

    async def test_refund_not_cancelled(
        self, authenticated_client, seed_hospital, seed_order
    ):
        user = authenticated_client._test_user
        hospital = await seed_hospital()
        order = await seed_order(user.id, hospital.id)
        await authenticated_client.post(f"/api/v1/orders/{order.id}/pay")
        resp = await authenticated_client.post(f"/api/v1/orders/{order.id}/refund")
        assert resp.status_code == 400

    async def test_refund_no_payment(
        self, authenticated_client, seed_hospital, seed_order
    ):
        user = authenticated_client._test_user
        hospital = await seed_hospital()
        order = await seed_order(
            user.id, hospital.id, status=OrderStatus.cancelled_by_patient
        )
        resp = await authenticated_client.post(f"/api/v1/orders/{order.id}/refund")
        assert resp.status_code == 400

    async def test_companion_cannot_pay(
        self, companion_client, seed_hospital, seed_order, seed_user
    ):
        patient = await seed_user(phone="13500135007")
        hospital = await seed_hospital()
        order = await seed_order(patient.id, hospital.id)
        resp = await companion_client.post(f"/api/v1/orders/{order.id}/pay")
        assert resp.status_code == 403

    async def test_cancel_auto_refunds(
        self, authenticated_client, seed_hospital, seed_order
    ):
        user = authenticated_client._test_user
        hospital = await seed_hospital()
        order = await seed_order(user.id, hospital.id)
        # Pay
        await authenticated_client.post(f"/api/v1/orders/{order.id}/pay")
        # Cancel — should auto-refund
        resp = await authenticated_client.post(f"/api/v1/orders/{order.id}/cancel")
        assert resp.status_code == 200
        # Verify order shows refunded payment status
        resp = await authenticated_client.get(f"/api/v1/orders/{order.id}")
        assert resp.status_code == 200
        assert resp.json()["payment_status"] == "refunded"

    async def test_cancel_no_payment_no_refund(
        self, authenticated_client, seed_hospital, seed_order
    ):
        user = authenticated_client._test_user
        hospital = await seed_hospital()
        order = await seed_order(user.id, hospital.id)
        # Cancel without paying — no auto-refund
        resp = await authenticated_client.post(f"/api/v1/orders/{order.id}/cancel")
        assert resp.status_code == 200

    async def test_payment_status_unpaid(
        self, authenticated_client, seed_hospital, seed_order
    ):
        user = authenticated_client._test_user
        hospital = await seed_hospital()
        order = await seed_order(user.id, hospital.id)
        resp = await authenticated_client.get(f"/api/v1/orders/{order.id}")
        assert resp.status_code == 200
        assert resp.json()["payment_status"] == "unpaid"

    async def test_payment_status_paid(
        self, authenticated_client, seed_hospital, seed_order
    ):
        user = authenticated_client._test_user
        hospital = await seed_hospital()
        order = await seed_order(user.id, hospital.id)
        await authenticated_client.post(f"/api/v1/orders/{order.id}/pay")
        resp = await authenticated_client.get(f"/api/v1/orders/{order.id}")
        assert resp.status_code == 200
        assert resp.json()["payment_status"] == "paid"

    async def test_payment_status_in_list(
        self, authenticated_client, seed_hospital, seed_order
    ):
        user = authenticated_client._test_user
        hospital = await seed_hospital()
        await seed_order(user.id, hospital.id)
        resp = await authenticated_client.get("/api/v1/orders")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) > 0
        assert "payment_status" in items[0]

    async def test_accept_unpaid_order_rejected(
        self, companion_client, seed_hospital, seed_order, seed_user
    ):
        """Companion CAN accept unpaid orders — no payment check on accept."""
        patient = await seed_user(phone="13500135030")
        hospital = await seed_hospital()
        order = await seed_order(patient.id, hospital.id)
        resp = await companion_client.post(f"/api/v1/orders/{order.id}/accept")
        assert resp.status_code == 200

    async def test_accept_paid_order_succeeds(
        self, companion_client, seed_hospital, seed_order, seed_user, seed_payment
    ):
        patient = await seed_user(phone="13500135031")
        hospital = await seed_hospital()
        order = await seed_order(patient.id, hospital.id)
        await seed_payment(order.id, patient.id)
        resp = await companion_client.post(f"/api/v1/orders/{order.id}/accept")
        assert resp.status_code == 200
        assert resp.json()["status"] == "accepted"

    async def test_create_order_blocked_by_unpaid(
        self, authenticated_client, seed_hospital, seed_order
    ):
        """Patient cannot create a new order if they have an unpaid one."""
        user = authenticated_client._test_user
        hospital = await seed_hospital()
        # Create first order (unpaid)
        await seed_order(user.id, hospital.id)
        # Try to create second order — should fail
        resp = await authenticated_client.post(
            "/api/v1/orders",
            json={
                "service_type": "full_accompany",
                "hospital_id": str(hospital.id),
                "appointment_date": "2026-05-01",
                "appointment_time": "09:00",
            },
        )
        assert resp.status_code == 400

    async def test_create_order_allowed_after_payment(
        self, authenticated_client, seed_hospital, seed_order, seed_payment
    ):
        """Patient can create a new order after paying the previous one."""
        user = authenticated_client._test_user
        hospital = await seed_hospital()
        # Create and pay first order
        order = await seed_order(user.id, hospital.id)
        await seed_payment(order.id, user.id)
        # Create second order — should succeed
        resp = await authenticated_client.post(
            "/api/v1/orders",
            json={
                "service_type": "half_accompany",
                "hospital_id": str(hospital.id),
                "appointment_date": "2026-05-02",
                "appointment_time": "10:00",
            },
        )
        assert resp.status_code == 201

    async def test_cancel_accepted_full_refund(
        self, authenticated_client, seed_hospital, seed_order, seed_user
    ):
        user = authenticated_client._test_user
        companion = await seed_user(phone="13500135032", role="companion")
        hospital = await seed_hospital()
        order = await seed_order(
            user.id, hospital.id,
            companion_id=companion.id,
            status=OrderStatus.accepted,
        )
        # Pay first
        await authenticated_client.post(f"/api/v1/orders/{order.id}/pay")
        # Cancel accepted order
        resp = await authenticated_client.post(f"/api/v1/orders/{order.id}/cancel")
        assert resp.status_code == 200
        # Verify full refund
        resp = await authenticated_client.get(f"/api/v1/orders/{order.id}")
        assert resp.json()["payment_status"] == "refunded"

    async def test_cancel_in_progress_half_refund(
        self, authenticated_client, seed_hospital, seed_order, seed_user
    ):
        user = authenticated_client._test_user
        companion = await seed_user(phone="13500135033", role="companion")
        hospital = await seed_hospital()
        order = await seed_order(
            user.id, hospital.id,
            companion_id=companion.id,
            status=OrderStatus.in_progress,
        )
        # Pay first
        await authenticated_client.post(f"/api/v1/orders/{order.id}/pay")
        # Cancel in-progress order
        resp = await authenticated_client.post(f"/api/v1/orders/{order.id}/cancel")
        assert resp.status_code == 200
        # Verify 50% refund via wallet transactions
        resp = await authenticated_client.get("/api/v1/wallet/transactions")
        data = resp.json()
        refund_tx = [t for t in data["items"] if t["payment_type"] == "refund"]
        assert len(refund_tx) == 1
        assert refund_tx[0]["amount"] == 149.5  # 50% of 299.0


@pytest.mark.asyncio
class TestWallet:
    async def test_wallet_summary_patient(self, authenticated_client):
        resp = await authenticated_client.get("/api/v1/wallet")
        assert resp.status_code == 200
        data = resp.json()
        assert "balance" in data
        assert data["balance"] == 0.0

    async def test_wallet_transactions_empty(self, authenticated_client):
        resp = await authenticated_client.get("/api/v1/wallet/transactions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    async def test_wallet_transactions_after_payment(
        self, authenticated_client, seed_hospital, seed_order
    ):
        user = authenticated_client._test_user
        hospital = await seed_hospital()
        order = await seed_order(user.id, hospital.id)
        await authenticated_client.post(f"/api/v1/orders/{order.id}/pay")
        resp = await authenticated_client.get("/api/v1/wallet/transactions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["payment_type"] == "pay"
        assert data["items"][0]["amount"] == 299.0

    async def test_wallet_summary_companion(
        self, companion_client, seed_hospital, seed_order, seed_user
    ):
        companion = companion_client._test_user
        patient = await seed_user(phone="13500135020")
        hospital = await seed_hospital()
        await seed_order(
            patient.id,
            hospital.id,
            companion_id=companion.id,
            status=OrderStatus.completed,
        )
        resp = await companion_client.get("/api/v1/wallet")
        assert resp.status_code == 200
        data = resp.json()
        assert data["balance"] == 299.0
        assert data["total_income"] == 299.0
