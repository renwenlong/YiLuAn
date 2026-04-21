"""
Payment callback idempotency + provider-abstraction tests (P0-1).

Covers:
  * Duplicate callback delivery doesn't double-process the order.
  * Bad signature → callback rejected (FAIL response, no log row written).
  * Refund failure path persists a "failed" Payment row & raises 400.
  * Callback arriving after order is closed/cancelled doesn't flip state.
  * Provider factory honours ``settings.payment_provider`` switch.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.config import settings
from app.exceptions import BadRequestException
from app.models.order import Order, OrderStatus
from app.models.payment import Payment
from app.models.payment_callback_log import PaymentCallbackLog
from app.services.payment_service import PaymentService
from app.services.providers.payment import (
    MockPaymentProvider,
    WechatPaymentProvider,
    get_payment_provider,
)
from app.services.providers.payment.base import OrderDTO, RefundDTO
from tests.conftest import test_session_factory


# ---------------------------------------------------------------------------
# Provider factory + abstraction
# ---------------------------------------------------------------------------

class TestProviderFactory:
    def test_default_is_mock(self):
        # settings.payment_provider defaults to "mock" in dev/test.
        assert settings.payment_provider == "mock"
        provider = get_payment_provider()
        assert isinstance(provider, MockPaymentProvider)

    def test_wechat_when_configured(self, monkeypatch):
        monkeypatch.setattr(settings, "payment_provider", "wechat")
        try:
            provider = get_payment_provider()
            assert isinstance(provider, WechatPaymentProvider)
        finally:
            monkeypatch.setattr(settings, "payment_provider", "mock")

    def test_unknown_falls_back_to_mock(self, monkeypatch):
        monkeypatch.setattr(settings, "payment_provider", "alipay-future")
        provider = get_payment_provider()
        assert isinstance(provider, MockPaymentProvider)


@pytest.mark.asyncio
class TestProviderInterface:
    """Verify the new high-level API surface on providers."""

    async def test_mock_create_order(self):
        p = MockPaymentProvider()
        result = await p.create_order(
            OrderDTO(order_number="YLA-1", amount_yuan=99.0)
        )
        assert result["status"] == "success"
        assert result["trade_no"].startswith("MOCK_")

    async def test_mock_refund_dto(self):
        p = MockPaymentProvider()
        result = await p.refund(
            RefundDTO(
                trade_no="MOCK_X",
                refund_id="R1",
                total_yuan=99.0,
                refund_yuan=99.0,
            )
        )
        assert result["status"] == "success"
        assert result["refund_id"] == "R1"

    async def test_mock_query(self):
        p = MockPaymentProvider()
        result = await p.query(OrderDTO(order_number="YLA-1", amount_yuan=99.0))
        assert result["trade_state"] == "SUCCESS"

    async def test_wechat_query_not_implemented(self):
        p = WechatPaymentProvider()
        with pytest.raises(NotImplementedError):
            await p.query(OrderDTO(order_number="YLA-1", amount_yuan=99.0))

    async def test_required_production_settings_listed(self):
        from app.services.providers.payment.wechat import (
            REQUIRED_PRODUCTION_SETTINGS,
        )

        # The constant exists and lists every credential ops needs.
        for key in (
            "WECHAT_APP_ID",
            "WECHAT_PAY_MCH_ID",
            "WECHAT_PAY_API_KEY_V3",
            "WECHAT_PAY_CERT_SERIAL",
            "WECHAT_PAY_PRIVATE_KEY_PATH",
            "WECHAT_PAY_NOTIFY_URL",
            "WECHAT_PAY_PLATFORM_CERT_PATH",
        ):
            assert key in REQUIRED_PRODUCTION_SETTINGS


# ---------------------------------------------------------------------------
# Idempotency: duplicate callback
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestCallbackIdempotency:
    async def test_duplicate_callback_logged_once(
        self,
        authenticated_client: AsyncClient,
        seed_hospital,
        seed_order,
    ):
        """
        Two identical callbacks for the same trade_no:
        * first one inserts a PaymentCallbackLog row & flips Payment.status
        * second one short-circuits (no extra log row, status unchanged)
        """
        user = authenticated_client._test_user
        hospital = await seed_hospital()
        order = await seed_order(user.id, hospital.id)

        # Pay first to create a Payment row with a known trade_no.
        pay_resp = await authenticated_client.post(
            f"/api/v1/orders/{order.id}/pay"
        )
        assert pay_resp.status_code == 200

        # Look up the trade_no the mock provider assigned.
        async with test_session_factory() as s:
            row = (
                await s.execute(
                    select(Payment).where(
                        Payment.order_id == order.id,
                        Payment.payment_type == "pay",
                    )
                )
            ).scalar_one()
            trade_no = row.trade_no

        body = (
            f'{{"out_trade_no": "{trade_no}", '
            f'"transaction_id": "{trade_no}", '
            f'"trade_state": "SUCCESS"}}'
        ).encode()

        # First delivery
        r1 = await authenticated_client.post(
            "/api/v1/payments/wechat/callback",
            content=body,
            headers={"content-type": "application/json"},
        )
        assert r1.status_code == 200
        assert r1.json()["code"] == "SUCCESS"

        # Second delivery — duplicate
        r2 = await authenticated_client.post(
            "/api/v1/payments/wechat/callback",
            content=body,
            headers={"content-type": "application/json"},
        )
        assert r2.status_code == 200
        assert r2.json()["code"] == "SUCCESS"

        # Exactly one log row exists for this transaction.
        async with test_session_factory() as s:
            logs = (
                await s.execute(
                    select(PaymentCallbackLog).where(
                        PaymentCallbackLog.transaction_id == trade_no
                    )
                )
            ).scalars().all()
        assert len(logs) == 1
        assert logs[0].callback_type == "pay"
        assert logs[0].status == "processed"

    async def test_record_callback_or_skip_returns_false_on_duplicate(
        self
    ):
        """Direct unit test for the idempotency helper."""
        async with test_session_factory() as s:
            svc = PaymentService(s)
            txn = "MOCK_DUPLICATE_PROBE_001"

            ok1 = await svc.record_callback_or_skip(
                provider="mock",
                transaction_id=txn,
                callback_type="pay",
                out_trade_no="YLA-PROBE-001",
                raw_body=b'{"probe": true}',
            )
            assert ok1 is True

            ok2 = await svc.record_callback_or_skip(
                provider="mock",
                transaction_id=txn,
                callback_type="pay",
                out_trade_no="YLA-PROBE-001",
                raw_body=b'{"probe": true}',
            )
            assert ok2 is False

            # Must still be able to commit — i.e. SAVEPOINT cleanup worked.
            await s.commit()


# ---------------------------------------------------------------------------
# Bad signature rejection
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestCallbackSignatureRejection:
    async def test_bad_signature_rejected_with_fail(
        self,
        authenticated_client: AsyncClient,
    ):
        """
        Force the provider's ``verify_callback`` to raise — the endpoint
        must respond with code=FAIL and must NOT write an idempotency log.
        """
        async def boom(headers, body):
            raise BadRequestException("微信回调签名验证失败")

        with patch(
            "app.services.providers.payment.mock.MockPaymentProvider.verify_callback",
            side_effect=boom,
        ):
            resp = await authenticated_client.post(
                "/api/v1/payments/wechat/callback",
                content=b'{"out_trade_no": "BAD-SIG-001"}',
                headers={"content-type": "application/json"},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == "FAIL"
        assert "签名" in body["message"]

        # No log row should have been persisted.
        async with test_session_factory() as s:
            logs = (
                await s.execute(
                    select(PaymentCallbackLog).where(
                        PaymentCallbackLog.out_trade_no == "BAD-SIG-001"
                    )
                )
            ).scalars().all()
        assert logs == []


# ---------------------------------------------------------------------------
# Refund failure path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestRefundFailure:
    async def test_provider_refund_failure_is_atomic_and_recoverable(
        self,
        authenticated_client: AsyncClient,
        seed_hospital,
        seed_order,
    ):
        """
        Replaces the previous ``_persists_failed_record`` test.

        C6 (commit d06867a) flipped the cancel-with-broken-refund semantics:

          * Old behaviour  : swallow the refund error, return 200, persist a
            ``failed`` refund row so callers can replay.
          * New behaviour  : surface the refund failure as an explicit 400 on
            ``/cancel``; the request session is rolled back wholesale by
            ``app.database.get_db`` so the order stays in its pre-cancel
            status (``created``/``accepted``) and no partial refund row is
            left behind. The client retries by calling ``/cancel`` again
            once the provider recovers.

        The old "persist a failed refund_log row" semantic is no longer
        achievable inside the request transaction — it would require an
        outbox table or a dedicated SAVEPOINT escape hatch. That work is
        tracked as follow-up TD-PAY-02 in ``docs/DECISION_LOG.md``.

        Invariants this test pins down:
          1. Provider failure surfaces as a 400 with a Chinese refund-related
             error message (no silent 200).
          2. The whole cancel transaction rolls back: order status stays
             ``paid`` and zero refund rows of any status exist.
          3. Retrying ``/cancel`` after the provider recovers atomically
             flips the order to cancelled AND persists a successful refund.
        """
        user = authenticated_client._test_user
        hospital = await seed_hospital()
        order = await seed_order(user.id, hospital.id)

        pay_resp = await authenticated_client.post(
            f"/api/v1/orders/{order.id}/pay"
        )
        assert pay_resp.status_code == 200

        async def boom(*args, **kwargs):
            raise RuntimeError("simulated network outage")

        # 1) Cancel with provider broken — must explicitly fail (C6).
        with patch(
            "app.services.providers.payment.mock.MockPaymentProvider.refund",
            side_effect=boom,
        ):
            cancel_resp = await authenticated_client.post(
                f"/api/v1/orders/{order.id}/cancel"
            )

        assert cancel_resp.status_code == 400
        body = cancel_resp.json()
        # Error message must mention the refund failure so operators can
        # tell this 400 apart from a generic "cannot transition" 400.
        assert "退款" in body["detail"]

        # 2) Whole transaction rolled back: order still paid, no refund rows.
        async with test_session_factory() as s:
            order_after = (
                await s.execute(select(Order).where(Order.id == order.id))
            ).scalar_one()
            assert order_after.status == OrderStatus.created, (
                "cancel rollback failed — order status leaked through"
            )

            refund_rows = (
                await s.execute(
                    select(Payment).where(
                        Payment.order_id == order.id,
                        Payment.payment_type == "refund",
                    )
                )
            ).scalars().all()
            assert refund_rows == [], (
                "no partial refund row of any status should be persisted"
            )

        # 3) Retry cancel with provider recovered — must atomically succeed:
        #    order flips to cancelled AND a successful refund row appears.
        retry = await authenticated_client.post(
            f"/api/v1/orders/{order.id}/cancel"
        )
        assert retry.status_code == 200

        async with test_session_factory() as s:
            order_final = (
                await s.execute(select(Order).where(Order.id == order.id))
            ).scalar_one()
            assert order_final.status in (
                OrderStatus.cancelled_by_patient,
                OrderStatus.cancelled_by_companion,
            )

            refund_final = (
                await s.execute(
                    select(Payment).where(
                        Payment.order_id == order.id,
                        Payment.payment_type == "refund",
                        Payment.status == "success",
                    )
                )
            ).scalar_one()
            assert refund_final is not None


# ---------------------------------------------------------------------------
# Callback after order closed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestCallbackAfterOrderClosed:
    async def test_callback_after_cancel_does_not_revert_status(
        self,
        authenticated_client: AsyncClient,
        seed_hospital,
        seed_order,
    ):
        """
        Realistic ordering issue: WeChat finally delivers a SUCCESS
        callback after the user has already cancelled the order. We must
        not reopen the order or wipe the refund record; the callback
        is logged for audit but does not flip ``Payment.status`` away
        from its terminal state.
        """
        user = authenticated_client._test_user
        hospital = await seed_hospital()
        order = await seed_order(user.id, hospital.id)

        # Pay → cancel (auto-refund).
        await authenticated_client.post(f"/api/v1/orders/{order.id}/pay")
        cancel_resp = await authenticated_client.post(
            f"/api/v1/orders/{order.id}/cancel"
        )
        assert cancel_resp.status_code == 200

        async with test_session_factory() as s:
            pay_row = (
                await s.execute(
                    select(Payment).where(
                        Payment.order_id == order.id,
                        Payment.payment_type == "pay",
                    )
                )
            ).scalar_one()
            trade_no = pay_row.trade_no
            status_before = pay_row.status

        # Late callback arrives (use a *different* transaction id so the
        # idempotency log has a free slot — this models a genuinely-new
        # provider notification arriving after the order is closed).
        late_txn = f"LATE_{trade_no}"
        body = (
            f'{{"out_trade_no": "{trade_no}", '
            f'"transaction_id": "{late_txn}", '
            f'"trade_state": "SUCCESS"}}'
        ).encode()

        resp = await authenticated_client.post(
            "/api/v1/payments/wechat/callback",
            content=body,
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 200
        assert resp.json()["code"] == "SUCCESS"

        # Pay row status must be unchanged (already terminal).
        async with test_session_factory() as s:
            pay_row_after = (
                await s.execute(
                    select(Payment).where(
                        Payment.order_id == order.id,
                        Payment.payment_type == "pay",
                    )
                )
            ).scalar_one()
            assert pay_row_after.status == status_before

            # Refund row must still be present (i.e. cancel was honoured).
            refund_row = (
                await s.execute(
                    select(Payment).where(
                        Payment.order_id == order.id,
                        Payment.payment_type == "refund",
                    )
                )
            ).scalar_one()
            assert refund_row is not None

            # And the late callback was logged for audit.
            log = (
                await s.execute(
                    select(PaymentCallbackLog).where(
                        PaymentCallbackLog.transaction_id == late_txn
                    )
                )
            ).scalar_one()
            assert log.callback_type == "pay"

        # Order itself should remain cancelled.
        detail = await authenticated_client.get(
            f"/api/v1/orders/{order.id}"
        )
        assert detail.status_code == 200
        assert detail.json()["status"] == OrderStatus.cancelled_by_patient.value
