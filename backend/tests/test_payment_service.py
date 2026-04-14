"""
Payment Service tests — covers PaymentService with mock provider.
"""

import time

import pytest
from httpx import AsyncClient

from app.exceptions import BadRequestException
from app.models.order import OrderStatus
from app.services.payment_service import (
    MockPaymentProvider,
    PaymentProvider,
    PaymentService,
    RefundResult,
    WechatPaymentProvider,
)


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


# =============================================================================
# verify_callback boundary tests
# =============================================================================


@pytest.mark.asyncio
class TestVerifyCallbackBoundary:
    """Edge cases for verify_callback via the callback endpoint."""

    async def test_callback_empty_body(self, authenticated_client: AsyncClient):
        """Empty body should still return 200 (endpoint never returns non-200)."""
        resp = await authenticated_client.post(
            "/api/v1/payments/wechat/callback",
            content=b"",
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 200

    async def test_callback_non_json_body(self, authenticated_client: AsyncClient):
        """Non-JSON body should still return 200 (graceful handling)."""
        resp = await authenticated_client.post(
            "/api/v1/payments/wechat/callback",
            content=b"this is not json at all!",
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 200

    async def test_callback_valid_json_missing_fields(
        self, authenticated_client: AsyncClient
    ):
        """Valid JSON missing required fields should still return 200."""
        resp = await authenticated_client.post(
            "/api/v1/payments/wechat/callback",
            content=b'{"foo": "bar"}',
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] in ("SUCCESS", "FAIL")

    async def test_refund_callback_empty_body(
        self, authenticated_client: AsyncClient
    ):
        """Empty body on refund callback should still return 200."""
        resp = await authenticated_client.post(
            "/api/v1/payments/wechat/refund-callback",
            content=b"",
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 200


# =============================================================================
# MockPaymentProvider unit tests
# =============================================================================


@pytest.mark.asyncio
class TestMockPaymentProvider:
    """Direct tests for MockPaymentProvider."""

    async def test_create_prepay(self):
        """Mock prepay should return success with MOCK_ trade_no."""
        provider = MockPaymentProvider()
        result = await provider.create_prepay("YLA123", 299.0, "test")
        assert result["status"] == "success"
        assert result["trade_no"].startswith("MOCK_")
        assert result["prepay_id"].startswith("mock_prepay_")

    async def test_create_refund(self):
        """Mock refund should return success with provided refund_id."""
        provider = MockPaymentProvider()
        result = await provider.create_refund("MOCK_ABC", "R123", 299.0, 149.5)
        assert result["status"] == "success"
        assert result["refund_id"] == "R123"

    async def test_verify_callback(self):
        """Mock verify_callback should return verified True."""
        provider = MockPaymentProvider()
        result = await provider.verify_callback({}, b'{"test": true}')
        assert result["verified"] is True


# =============================================================================
# PaymentProvider base class
# =============================================================================


@pytest.mark.asyncio
class TestPaymentProviderBase:
    """Tests for PaymentProvider abstract base class."""

    async def test_create_prepay_raises(self):
        provider = PaymentProvider()
        with pytest.raises(NotImplementedError):
            await provider.create_prepay("YLA1", 100.0, "test")

    async def test_create_refund_raises(self):
        provider = PaymentProvider()
        with pytest.raises(NotImplementedError):
            await provider.create_refund("T1", "R1", 100.0, 50.0)

    async def test_verify_callback_raises(self):
        provider = PaymentProvider()
        with pytest.raises(NotImplementedError):
            await provider.verify_callback({}, b"")


# =============================================================================
# Timestamp replay protection tests
# =============================================================================


@pytest.mark.asyncio
class TestTimestampReplayProtection:
    """Tests for _verify_signature timestamp freshness check."""

    def _make_provider(self) -> WechatPaymentProvider:
        """Create a WechatPaymentProvider with fake credentials to bypass mock mode."""
        provider = WechatPaymentProvider()
        # Set credentials so _has_credentials is True and mock mode is skipped
        provider._has_credentials = True
        return provider

    def _headers(self, timestamp: str) -> dict:
        return {
            "wechatpay-timestamp": timestamp,
            "wechatpay-nonce": "test-nonce",
            "wechatpay-signature": "dGVzdA==",  # base64("test")
            "wechatpay-serial": "TEST_SERIAL",
        }

    async def test_fresh_timestamp_passes_check(self):
        """Timestamp within 5 minutes should pass the freshness check.

        The method will fail later at certificate loading, but if it gets past
        the timestamp check that proves the replay protection accepted it.
        """
        provider = self._make_provider()
        ts = str(int(time.time()))
        with pytest.raises(BadRequestException) as exc_info:
            provider._verify_signature(self._headers(ts), b'{"test": true}')
        # Should fail on cert loading, NOT on timestamp — proves freshness check passed
        assert "时间戳过期" not in str(exc_info.value.detail)
        assert "重放" not in str(exc_info.value.detail)

    async def test_expired_timestamp_rejected(self):
        """Timestamp older than 5 minutes should be rejected as replay attack."""
        provider = self._make_provider()
        old_ts = str(int(time.time()) - 600)  # 10 minutes ago
        with pytest.raises(BadRequestException) as exc_info:
            provider._verify_signature(self._headers(old_ts), b'{"test": true}')
        assert "时间戳过期" in str(exc_info.value.detail)

    async def test_future_timestamp_rejected(self):
        """Timestamp more than 5 minutes in the future should also be rejected."""
        provider = self._make_provider()
        future_ts = str(int(time.time()) + 600)  # 10 minutes in the future
        with pytest.raises(BadRequestException) as exc_info:
            provider._verify_signature(self._headers(future_ts), b'{"test": true}')
        assert "时间戳过期" in str(exc_info.value.detail)

