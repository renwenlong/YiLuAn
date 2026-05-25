"""D-058: end-to-end idempotency coverage for the three hot paths.

Each test exercises a deliberate duplicate request and asserts the
**second** call did NOT cause a duplicate side-effect.
"""
from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import func, select

from app.models.idempotency_key import IdempotencyKey
from app.models.order import Order
from app.models.payment import Payment
from app.models.payment_callback_log import PaymentCallbackLog
from tests.conftest import test_session_factory


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# 1. POST /api/v1/orders — Idempotency-Key header
# ---------------------------------------------------------------------------

class TestCreateOrderIdempotency:
    """`Idempotency-Key` header dedupes client retries of POST /orders."""

    async def test_same_key_returns_cached_response_and_no_duplicate_order(
        self, authenticated_client, seed_hospital
    ):
        hospital = await seed_hospital()
        user = authenticated_client._test_user
        key = f"client-{uuid.uuid4()}"
        payload = {
            "service_type": "full_accompany",
            "hospital_id": str(hospital.id),
            "appointment_date": "2026-05-01",
            "appointment_time": "09:00",
            "description": "idempotent retry",
        }

        # First call: real create.
        r1 = await authenticated_client.post(
            "/api/v1/orders", json=payload, headers={"Idempotency-Key": key}
        )
        assert r1.status_code == 201
        body1 = r1.json()
        order_id = body1["id"]

        # Second call with the same key: byte-for-byte the same response,
        # and crucially NO new order in the DB.
        r2 = await authenticated_client.post(
            "/api/v1/orders", json=payload, headers={"Idempotency-Key": key}
        )
        assert r2.status_code == 201
        assert r2.json() == body1

        async with test_session_factory() as s:
            count = (
                await s.execute(
                    select(func.count(Order.id)).where(Order.patient_id == user.id)
                )
            ).scalar_one()
        assert count == 1, "duplicate request must not create a second order"

        # The idempotency_keys row exists exactly once.
        async with test_session_factory() as s:
            n_keys = (
                await s.execute(
                    select(func.count(IdempotencyKey.id)).where(
                        IdempotencyKey.user_id == user.id,
                        IdempotencyKey.key == key,
                    )
                )
            ).scalar_one()
        assert n_keys == 1
        assert body1["id"] == order_id

    async def test_no_key_header_keeps_legacy_behaviour(
        self, authenticated_client, seed_hospital
    ):
        """Missing header → original flow, including ORDER_HAS_UNPAID guard."""
        hospital = await seed_hospital()
        payload = {
            "service_type": "full_accompany",
            "hospital_id": str(hospital.id),
            "appointment_date": "2026-05-01",
            "appointment_time": "09:00",
        }
        r1 = await authenticated_client.post("/api/v1/orders", json=payload)
        assert r1.status_code == 201
        # Second call without a key triggers the existing unpaid-orders
        # guard (NOT a 201 replay) — proves we didn't accidentally enable
        # idempotency for keyless requests.
        r2 = await authenticated_client.post("/api/v1/orders", json=payload)
        assert r2.status_code == 400


# ---------------------------------------------------------------------------
# 2. POST /api/v1/orders/{id}/pay — pending retry returns cached sign params
# ---------------------------------------------------------------------------

class TestPayOrderIdempotency:
    """Retrying ``/pay`` on a ``pending`` payment returns the same prepay."""

    async def test_pending_retry_returns_cached_sign_params_without_psp_call(
        self,
        authenticated_client,
        seed_hospital,
        seed_order,
        monkeypatch,
    ):
        # Force the WeChat provider so create_prepay produces a ``pending``
        # row (mock provider auto-completes to ``success`` and we'd hit the
        # 400 "already paid" guard instead — which is the intended behaviour
        # for already-success retries, covered by test_pay_order_duplicate).
        from app.services.providers.payment import wechat as wechat_module
        from app.services import payment_service as ps_module

        fake_call_count = {"n": 0}
        fake_params = {
            "appId": "wx-test",
            "timeStamp": "1700000000",
            "nonceStr": "deadbeef",
            "package": "prepay_id=wx2025fake",
            "signType": "RSA",
            "paySign": "SIGNATURE-V1",
        }

        async def fake_create_prepay(self, **kwargs):
            fake_call_count["n"] += 1
            return {
                "prepay_id": "wx2025fake",
                "trade_no": kwargs.get("order_number", "T"),
                "sign_params": dict(fake_params),
            }

        monkeypatch.setattr(
            wechat_module.WechatPaymentProvider,
            "create_prepay",
            fake_create_prepay,
        )

        def fake_factory():
            return wechat_module.WechatPaymentProvider.__new__(
                wechat_module.WechatPaymentProvider
            )

        monkeypatch.setattr(ps_module, "get_payment_provider", fake_factory)

        user = authenticated_client._test_user
        hospital = await seed_hospital()
        order = await seed_order(user.id, hospital.id)

        r1 = await authenticated_client.post(f"/api/v1/orders/{order.id}/pay")
        assert r1.status_code == 200, r1.text
        body1 = r1.json()
        assert body1["provider"] == "wechat"
        assert body1["sign_params"] == fake_params
        assert fake_call_count["n"] == 1

        # Retry — must NOT call the provider again and must return the SAME
        # signing payload (paySign in particular).
        r2 = await authenticated_client.post(f"/api/v1/orders/{order.id}/pay")
        assert r2.status_code == 200, r2.text
        body2 = r2.json()
        assert body2["sign_params"] == body1["sign_params"]
        assert body2["prepay_id"] == body1["prepay_id"]
        assert body2["payment_id"] == body1["payment_id"]
        assert fake_call_count["n"] == 1, "PSP must not be re-hit on retry"

        # Only one Payment row exists for this order.
        async with test_session_factory() as s:
            n = (
                await s.execute(
                    select(func.count(Payment.id)).where(
                        Payment.order_id == order.id,
                        Payment.payment_type == "pay",
                    )
                )
            ).scalar_one()
        assert n == 1


# ---------------------------------------------------------------------------
# 3. POST /api/v1/payments/wechat/callback — duplicate notify dedup
# ---------------------------------------------------------------------------

class TestPaymentCallbackEndpointIdempotency:
    """Same `transaction_id` twice → second call is a no-op (SUCCESS ack)."""

    async def test_duplicate_callback_does_not_double_apply(
        self, client, seed_hospital, seed_user, seed_order
    ):
        user = await seed_user()
        hospital = await seed_hospital()
        order = await seed_order(user.id, hospital.id)

        # Seed a pending Payment row tied to a known trade_no.
        trade_no = f"MOCK-{uuid.uuid4().hex[:10]}"
        async with test_session_factory() as s:
            pay = Payment(
                order_id=order.id,
                user_id=user.id,
                amount=order.price,
                payment_type="pay",
                status="pending",
                trade_no=trade_no,
            )
            s.add(pay)
            await s.commit()
            pay_id = pay.id

        callback_body = {
            "resource": {
                "transaction_id": trade_no,
                "out_trade_no": order.order_number,
                "trade_state": "SUCCESS",
            }
        }
        body_bytes = json.dumps(callback_body).encode()

        # First delivery → success path.
        r1 = await client.post(
            "/api/v1/payments/wechat/callback",
            content=body_bytes,
            headers={"Content-Type": "application/json"},
        )
        assert r1.status_code == 200
        assert r1.json()["code"] == "SUCCESS"

        # Second delivery (WeChat retries up to 8 times) → also SUCCESS but
        # MUST NOT touch Payment.status (defence-in-depth) and MUST NOT
        # create a second payment_callback_log row.
        r2 = await client.post(
            "/api/v1/payments/wechat/callback",
            content=body_bytes,
            headers={"Content-Type": "application/json"},
        )
        assert r2.status_code == 200
        assert r2.json()["code"] == "SUCCESS"

        async with test_session_factory() as s:
            n_logs = (
                await s.execute(
                    select(func.count(PaymentCallbackLog.id)).where(
                        PaymentCallbackLog.transaction_id == trade_no
                    )
                )
            ).scalar_one()
            assert n_logs == 1, "duplicate callback wrote a second log row"

            pay_after = (
                await s.execute(select(Payment).where(Payment.id == pay_id))
            ).scalar_one()
            # Mock provider's verify_callback parses the body as-is, and
            # mark Payment.success via handle_pay_callback on the first
            # call only.
            assert pay_after.status == "success"
