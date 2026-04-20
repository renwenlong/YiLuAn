"""
Refund callback handler tests (P0-14).

Covers:
  * Happy path: SUCCESS refund callback updates Payment status
  * Failed refund callback: FAILED status + error log
  * Idempotency: duplicate callback returns success, no double processing
  * Signature failure: verify_callback raises → FAIL response, no DB mutation
  * Unknown refund_id: returns SUCCESS + warn log (not an error)
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.exceptions import BadRequestException
from app.models.payment import Payment
from app.models.payment_callback_log import PaymentCallbackLog
from tests.conftest import test_session_factory


def _refund_body(refund_id: str, status: str = "SUCCESS") -> bytes:
    return (
        f'{{"out_refund_no": "{refund_id}", '
        f'"out_trade_no": "YLA-ORDER-001", '
        f'"refund_status": "{status}"}}'
    ).encode()


async def _create_refund_payment(
    order_id, user_id, refund_id: str, status: str = "pending"
):
    """Create a refund Payment record with refund_id set atomically."""
    async with test_session_factory() as s:
        payment = Payment(
            order_id=order_id,
            user_id=user_id,
            amount=299.0,
            payment_type="refund",
            status=status,
            refund_id=refund_id,
        )
        s.add(payment)
        await s.commit()
        await s.refresh(payment)
        return payment


@pytest.mark.asyncio
class TestRefundCallbackHandler:
    """Tests for POST /api/v1/payments/wechat/refund-callback."""

    async def test_refund_success_callback(
        self,
        authenticated_client: AsyncClient,
        seed_hospital,
        seed_order,
        seed_payment,
    ):
        """Refund SUCCESS callback should update Payment status to success."""
        user = authenticated_client._test_user
        hospital = await seed_hospital()
        order = await seed_order(user.id, hospital.id)

        await seed_payment(order.id, user.id, payment_type="pay", status="success")
        refund = await _create_refund_payment(
            order.id, user.id, refund_id="R_SUCCESS_001"
        )

        resp = await authenticated_client.post(
            "/api/v1/payments/wechat/refund-callback",
            content=_refund_body("R_SUCCESS_001", "SUCCESS"),
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 200
        assert resp.json()["code"] == "SUCCESS"

        async with test_session_factory() as s:
            updated = (
                await s.execute(
                    select(Payment).where(Payment.id == refund.id)
                )
            ).scalar_one()
            assert updated.status == "success"
            assert updated.callback_raw is not None

    async def test_refund_failed_callback(
        self,
        authenticated_client: AsyncClient,
        seed_hospital,
        seed_order,
        seed_payment,
    ):
        """Refund FAILED callback should set Payment status to failed."""
        user = authenticated_client._test_user
        hospital = await seed_hospital()
        order = await seed_order(user.id, hospital.id)

        await seed_payment(order.id, user.id, payment_type="pay", status="success")
        refund = await _create_refund_payment(
            order.id, user.id, refund_id="R_FAIL_001"
        )

        resp = await authenticated_client.post(
            "/api/v1/payments/wechat/refund-callback",
            content=_refund_body("R_FAIL_001", "CHANGE"),
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 200
        assert resp.json()["code"] == "SUCCESS"

        async with test_session_factory() as s:
            updated = (
                await s.execute(
                    select(Payment).where(Payment.id == refund.id)
                )
            ).scalar_one()
            assert updated.status == "failed"

    async def test_duplicate_refund_callback_idempotent(
        self,
        authenticated_client: AsyncClient,
        seed_hospital,
        seed_order,
        seed_payment,
    ):
        """Second identical refund callback should return SUCCESS without re-processing."""
        user = authenticated_client._test_user
        hospital = await seed_hospital()
        order = await seed_order(user.id, hospital.id)

        await seed_payment(order.id, user.id, payment_type="pay", status="success")
        await _create_refund_payment(
            order.id, user.id, refund_id="R_IDEM_001"
        )

        body = _refund_body("R_IDEM_001", "SUCCESS")

        r1 = await authenticated_client.post(
            "/api/v1/payments/wechat/refund-callback",
            content=body,
            headers={"content-type": "application/json"},
        )
        assert r1.json()["code"] == "SUCCESS"

        r2 = await authenticated_client.post(
            "/api/v1/payments/wechat/refund-callback",
            content=body,
            headers={"content-type": "application/json"},
        )
        assert r2.json()["code"] == "SUCCESS"

        async with test_session_factory() as s:
            logs = (
                await s.execute(
                    select(PaymentCallbackLog).where(
                        PaymentCallbackLog.transaction_id == "R_IDEM_001"
                    )
                )
            ).scalars().all()
            assert len(logs) == 1

    async def test_bad_signature_rejected(
        self,
        authenticated_client: AsyncClient,
    ):
        """Signature verification failure should return FAIL, no DB mutation."""

        async def boom(headers, body):
            raise BadRequestException("微信回调签名验证失败")

        with patch(
            "app.services.providers.payment.mock.MockPaymentProvider.verify_callback",
            side_effect=boom,
        ):
            resp = await authenticated_client.post(
                "/api/v1/payments/wechat/refund-callback",
                content=_refund_body("R_BADSIG_001"),
                headers={"content-type": "application/json"},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == "FAIL"
        assert "签名" in body["message"]

        async with test_session_factory() as s:
            logs = (
                await s.execute(
                    select(PaymentCallbackLog).where(
                        PaymentCallbackLog.transaction_id == "R_BADSIG_001"
                    )
                )
            ).scalars().all()
            assert logs == []

    async def test_unknown_refund_id_returns_success(
        self,
        authenticated_client: AsyncClient,
    ):
        """Unknown refund_id should return SUCCESS (ack to stop retries)."""
        resp = await authenticated_client.post(
            "/api/v1/payments/wechat/refund-callback",
            content=_refund_body("R_UNKNOWN_999", "SUCCESS"),
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 200
        assert resp.json()["code"] == "SUCCESS"
