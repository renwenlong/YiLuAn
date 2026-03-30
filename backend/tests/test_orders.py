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
        # Cancel
        await authenticated_client.post(f"/api/v1/orders/{order.id}/cancel")
        # Refund
        resp = await authenticated_client.post(f"/api/v1/orders/{order.id}/refund")
        assert resp.status_code == 200
        data = resp.json()
        assert data["payment_type"] == "refund"
        assert data["amount"] == 299.0

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
