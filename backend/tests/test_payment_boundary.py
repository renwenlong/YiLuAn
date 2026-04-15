"""
Payment boundary value tests — covers edge cases for payment amounts,
order state transitions, and input validation.
"""

import pytest
from httpx import AsyncClient

from app.models.order import OrderStatus


@pytest.mark.asyncio
class TestPaymentAmountBoundary:
    """Tests for payment amount edge cases."""

    async def test_pay_minimum_amount(
        self, authenticated_client: AsyncClient, seed_hospital, seed_order
    ):
        """Minimum valid payment amount (0.01 yuan = 1 fen)."""
        user = authenticated_client._test_user
        hospital = await seed_hospital()
        order = await seed_order(user.id, hospital.id, price=0.01)

        resp = await authenticated_client.post(f"/api/v1/orders/{order.id}/pay")
        assert resp.status_code == 200
        data = resp.json()
        assert data["provider"] == "mock"
        assert data["payment_id"] is not None

    async def test_pay_large_amount(
        self, authenticated_client: AsyncClient, seed_hospital, seed_order
    ):
        """Large payment amount (99999.99 yuan)."""
        user = authenticated_client._test_user
        hospital = await seed_hospital()
        order = await seed_order(user.id, hospital.id, price=99999.99)

        resp = await authenticated_client.post(f"/api/v1/orders/{order.id}/pay")
        assert resp.status_code == 200
        data = resp.json()
        assert data["payment_id"] is not None

    async def test_pay_one_fen_amount(
        self, authenticated_client: AsyncClient, seed_hospital, seed_order
    ):
        """Payment of exactly 1 fen (0.01 yuan) — the smallest unit."""
        user = authenticated_client._test_user
        hospital = await seed_hospital()
        order = await seed_order(user.id, hospital.id, price=0.01)

        resp = await authenticated_client.post(f"/api/v1/orders/{order.id}/pay")
        assert resp.status_code == 200

    async def test_pay_round_amount(
        self, authenticated_client: AsyncClient, seed_hospital, seed_order
    ):
        """Payment with whole-number amount (100.00 yuan)."""
        user = authenticated_client._test_user
        hospital = await seed_hospital()
        order = await seed_order(user.id, hospital.id, price=100.00)

        resp = await authenticated_client.post(f"/api/v1/orders/{order.id}/pay")
        assert resp.status_code == 200


@pytest.mark.asyncio
class TestPaymentStateTransitions:
    """Tests for invalid payment state transitions."""

    async def test_pay_completed_order_allowed(
        self, authenticated_client: AsyncClient, seed_hospital, seed_order
    ):
        """Currently, paying for a completed order is not explicitly blocked.

        This documents current behavior — the pay endpoint only rejects
        cancelled orders. Consider adding status validation as a future
        improvement (completed/reviewed orders should not accept payment).
        """
        user = authenticated_client._test_user
        hospital = await seed_hospital()
        order = await seed_order(
            user.id, hospital.id, status=OrderStatus.completed
        )

        resp = await authenticated_client.post(f"/api/v1/orders/{order.id}/pay")
        # Current behavior: 200 (not blocked)
        # TODO: Consider returning 400 for completed/reviewed orders
        assert resp.status_code == 200

    async def test_pay_reviewed_order_allowed(
        self, authenticated_client: AsyncClient, seed_hospital, seed_order
    ):
        """Currently, paying for a reviewed order is not explicitly blocked.

        Same as completed — documents current behavior.
        TODO: Consider blocking payment for orders past 'accepted' state.
        """
        user = authenticated_client._test_user
        hospital = await seed_hospital()
        order = await seed_order(
            user.id, hospital.id, status=OrderStatus.reviewed
        )

        resp = await authenticated_client.post(f"/api/v1/orders/{order.id}/pay")
        assert resp.status_code == 200

    async def test_pay_nonexistent_order(
        self, authenticated_client: AsyncClient
    ):
        """Pay for a non-existent order should return 404."""
        import uuid

        fake_id = uuid.uuid4()
        resp = await authenticated_client.post(f"/api/v1/orders/{fake_id}/pay")
        assert resp.status_code == 404

    async def test_double_refund_rejected(
        self, authenticated_client: AsyncClient, seed_hospital, seed_order
    ):
        """Cannot refund the same order twice."""
        user = authenticated_client._test_user
        hospital = await seed_hospital()
        order = await seed_order(user.id, hospital.id)

        # Pay
        pay_resp = await authenticated_client.post(f"/api/v1/orders/{order.id}/pay")
        assert pay_resp.status_code == 200

        # Cancel (triggers refund)
        cancel_resp = await authenticated_client.post(
            f"/api/v1/orders/{order.id}/cancel"
        )
        assert cancel_resp.status_code == 200

        # Try to refund again
        refund_resp = await authenticated_client.post(
            f"/api/v1/orders/{order.id}/refund"
        )
        assert refund_resp.status_code == 400


@pytest.mark.asyncio
class TestCallbackBoundaryValues:
    """Tests for callback edge cases."""

    async def test_callback_oversized_body(
        self, authenticated_client: AsyncClient
    ):
        """Very large callback body should be handled gracefully."""
        large_body = b'{"data": "' + b"x" * 100000 + b'"}'
        resp = await authenticated_client.post(
            "/api/v1/payments/wechat/callback",
            content=large_body,
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 200

    async def test_callback_unicode_body(
        self, authenticated_client: AsyncClient
    ):
        """Callback with Unicode characters in body."""
        resp = await authenticated_client.post(
            "/api/v1/payments/wechat/callback",
            content='{"description": "测试支付回调中文内容"}'.encode("utf-8"),
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 200

    async def test_callback_duplicate_notification(
        self, authenticated_client: AsyncClient
    ):
        """Same callback sent twice should be handled idempotently."""
        body = b'{"out_trade_no": "YLA_DUP_001", "trade_state": "SUCCESS"}'
        for _ in range(2):
            resp = await authenticated_client.post(
                "/api/v1/payments/wechat/callback",
                content=body,
                headers={"content-type": "application/json"},
            )
            assert resp.status_code == 200
            assert resp.json()["code"] == "SUCCESS"

    async def test_refund_callback_partial_amount(
        self, authenticated_client: AsyncClient
    ):
        """Refund callback with partial refund amount."""
        resp = await authenticated_client.post(
            "/api/v1/payments/wechat/refund-callback",
            content=b'{"out_refund_no": "R_PART_001", "refund_status": "SUCCESS", "amount": {"refund": 5000, "total": 10000}}',
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 200
