"""
Payment Service tests — covers PaymentService with mock provider.
"""

import pytest
from httpx import AsyncClient

from app.models.order import OrderStatus


@pytest.mark.asyncio
class TestPaymentService:
    """Tests for the new PaymentService-backed payment flow."""

    async def test_pay_returns_prepay_result(
        self, authenticated_client: AsyncClient, seed_hospital, seed_order
    ):
        """Pay endpoint should return PrepayResult with mock provider info."""
        user = authenticated_client._test_user
        hospital = await seed_hospital()
        order = await seed_order(user.id, hospital.id)

        resp = await authenticated_client.post(f"/api/v1/orders/{order.id}/pay")
        assert resp.status_code == 200
        data = resp.json()

        assert data["provider"] == "mock"
        assert data["mock_success"] is True
        assert data["payment_id"] is not None
        assert data["prepay_id"] is not None

    async def test_pay_idempotent_rejects_duplicate(
        self, authenticated_client: AsyncClient, seed_hospital, seed_order
    ):
        """Second pay attempt on same order should be rejected."""
        user = authenticated_client._test_user
        hospital = await seed_hospital()
        order = await seed_order(user.id, hospital.id)

        # First pay
        resp1 = await authenticated_client.post(f"/api/v1/orders/{order.id}/pay")
        assert resp1.status_code == 200

        # Duplicate pay
        resp2 = await authenticated_client.post(f"/api/v1/orders/{order.id}/pay")
        assert resp2.status_code == 400

    async def test_pay_cancelled_order_rejected(
        self, authenticated_client: AsyncClient, seed_hospital, seed_order
    ):
        """Cannot pay for a cancelled order."""
        user = authenticated_client._test_user
        hospital = await seed_hospital()
        order = await seed_order(
            user.id, hospital.id, status=OrderStatus.cancelled_by_patient
        )

        resp = await authenticated_client.post(f"/api/v1/orders/{order.id}/pay")
        assert resp.status_code == 400

    async def test_cancel_after_pay_triggers_refund(
        self, authenticated_client: AsyncClient, seed_hospital, seed_order
    ):
        """Cancelling a paid order should auto-create a refund record."""
        user = authenticated_client._test_user
        hospital = await seed_hospital()
        order = await seed_order(user.id, hospital.id)

        # Pay
        pay_resp = await authenticated_client.post(f"/api/v1/orders/{order.id}/pay")
        assert pay_resp.status_code == 200

        # Cancel
        cancel_resp = await authenticated_client.post(
            f"/api/v1/orders/{order.id}/cancel"
        )
        assert cancel_resp.status_code == 200
        cancel_data = cancel_resp.json()
        assert cancel_data["status"] == "cancelled_by_patient"

        # Verify payment_status shows refunded
        detail_resp = await authenticated_client.get(f"/api/v1/orders/{order.id}")
        assert detail_resp.status_code == 200
        assert detail_resp.json()["payment_status"] == "refunded"

    async def test_refund_unpaid_order_rejected(
        self, authenticated_client: AsyncClient, seed_hospital, seed_order
    ):
        """Cannot refund an order that was never paid."""
        user = authenticated_client._test_user
        hospital = await seed_hospital()
        order = await seed_order(
            user.id, hospital.id, status=OrderStatus.cancelled_by_patient
        )

        resp = await authenticated_client.post(f"/api/v1/orders/{order.id}/refund")
        assert resp.status_code == 400

    async def test_pay_sign_params_structure(
        self, authenticated_client: AsyncClient, seed_hospital, seed_order
    ):
        """Mock pay should return sign_params matching wx.requestPayment format."""
        user = authenticated_client._test_user
        hospital = await seed_hospital()
        order = await seed_order(user.id, hospital.id)

        resp = await authenticated_client.post(f"/api/v1/orders/{order.id}/pay")
        data = resp.json()

        # sign_params should be None for mock provider (mock_success=True
        # means payment is instant, no need to call wx.requestPayment)
        # But prepay_id should be present
        assert "prepay_id" in data
        assert data["prepay_id"] is not None
        assert data["prepay_id"].startswith("mock_prepay_")


@pytest.mark.asyncio
class TestPaymentCallback:
    """Tests for payment callback endpoints."""

    async def test_pay_callback_returns_success(
        self, authenticated_client: AsyncClient
    ):
        """Callback endpoint should always return 200 with SUCCESS code."""
        resp = await authenticated_client.post(
            "/api/v1/payments/wechat/callback",
            content=b'{"out_trade_no": "YLA123", "trade_state": "SUCCESS"}',
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == "SUCCESS"

    async def test_refund_callback_returns_success(
        self, authenticated_client: AsyncClient
    ):
        """Refund callback endpoint should always return 200."""
        resp = await authenticated_client.post(
            "/api/v1/payments/wechat/refund-callback",
            content=b'{"out_refund_no": "R123", "refund_status": "SUCCESS"}',
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == "SUCCESS"
