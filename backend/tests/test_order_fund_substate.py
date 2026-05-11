"""H2-be · order fund sub-state tests.

Covers:

* ``payment_state`` flips to ``paid`` after mock prepay
* ``payment_state`` becomes ``failed`` on a failed payment callback
* ``refund_state`` flips to ``refunded`` after mock refund
* ``refund_state`` becomes ``failed`` on non-SUCCESS refund callback
* recon-cron persisted diff promotes ``refund_state`` to ``manual_review``
* ``OrderResponse`` schema exposes both fields
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.order import Order, PaymentState, RefundState
from app.models.payment import Payment
from app.services.payment_service import PaymentService

from tests.conftest import test_session_factory


@pytest.mark.asyncio
class TestOrderPaymentStateField:
    async def test_default_is_none(self, seed_user, seed_hospital, seed_order):
        user = await seed_user(phone="13700100001")
        hosp = await seed_hospital()
        order = await seed_order(user.id, hosp.id)
        async with test_session_factory() as s:
            o = (await s.execute(select(Order).where(Order.id == order.id))).scalar_one()
            assert o.payment_state == PaymentState.none
            assert o.refund_state == RefundState.none

    async def test_mock_prepay_sets_paid(
        self, authenticated_client, seed_hospital, seed_order
    ):
        user = authenticated_client._test_user
        hosp = await seed_hospital()
        order = await seed_order(user.id, hosp.id)
        resp = await authenticated_client.post(f"/api/v1/orders/{order.id}/pay")
        assert resp.status_code == 200
        async with test_session_factory() as s:
            o = (await s.execute(select(Order).where(Order.id == order.id))).scalar_one()
            assert o.payment_state == PaymentState.paid

    async def test_failed_callback_sets_failed(
        self, seed_user, seed_hospital, seed_order
    ):
        user = await seed_user(phone="13700100002")
        hosp = await seed_hospital()
        order = await seed_order(user.id, hosp.id)
        async with test_session_factory() as s:
            svc = PaymentService(s)
            # seed a pending payment row directly
            p = Payment(
                order_id=order.id,
                user_id=user.id,
                amount=Decimal("199.00"),
                payment_type="pay",
                status="pending",
                trade_no="MOCK_FAILCB_001",
            )
            s.add(p)
            await s.commit()

        async with test_session_factory() as s:
            svc = PaymentService(s)
            await svc.handle_pay_callback(
                trade_no="MOCK_FAILCB_001", order_number="YLA_FAILCB_001", success=False
            )
            await s.commit()

        async with test_session_factory() as s:
            o = (await s.execute(select(Order).where(Order.id == order.id))).scalar_one()
            assert o.payment_state == PaymentState.failed

    async def test_mock_refund_sets_refunded(
        self, authenticated_client, seed_hospital, seed_order
    ):
        user = authenticated_client._test_user
        hosp = await seed_hospital()
        order = await seed_order(user.id, hosp.id)
        # pay first (mock = instant success)
        r = await authenticated_client.post(f"/api/v1/orders/{order.id}/pay")
        assert r.status_code == 200

        async with test_session_factory() as s:
            svc = PaymentService(s)
            await svc.create_refund(
                order_id=order.id,
                user_id=user.id,
                original_amount=Decimal("199.00"),
                refund_amount=Decimal("199.00"),
            )
            await s.commit()

        async with test_session_factory() as s:
            o = (await s.execute(select(Order).where(Order.id == order.id))).scalar_one()
            assert o.refund_state == RefundState.refunded

    async def test_failed_refund_callback_sets_failed(
        self, seed_user, seed_hospital, seed_order
    ):
        user = await seed_user(phone="13700100003")
        hosp = await seed_hospital()
        order = await seed_order(user.id, hosp.id)
        rid = "REFUND_FAIL_001"
        async with test_session_factory() as s:
            s.add(
                Payment(
                    order_id=order.id,
                    user_id=user.id,
                    amount=Decimal("199.00"),
                    payment_type="refund",
                    status="pending",
                    trade_no="MOCK_REF_TX",
                    refund_id=rid,
                )
            )
            await s.commit()

        async with test_session_factory() as s:
            svc = PaymentService(s)
            await svc.handle_refund_callback(
                refund_id=rid, refund_status="ABNORMAL"
            )
            await s.commit()

        async with test_session_factory() as s:
            o = (await s.execute(select(Order).where(Order.id == order.id))).scalar_one()
            assert o.refund_state == RefundState.failed


@pytest.mark.asyncio
class TestReconciliationPromotesManualReview:
    async def test_persisted_diff_flips_order_to_manual_review(
        self, seed_user, seed_hospital, seed_order
    ):
        from app.cron.reconcile_money import _persist_diffs
        from app.services.reconciliation.diff import ReconDiff
        from app.models.reconciliation import (
            ReconciliationRun,
            ReconRunKind,
        )
        from app.models.reconciliation import ReconDiffKind
        from datetime import datetime, timezone, timedelta

        user = await seed_user(phone="13700100004")
        hosp = await seed_hospital()
        order = await seed_order(user.id, hosp.id)

        async with test_session_factory() as s:
            now = datetime.now(timezone.utc)
            run = ReconciliationRun(
                kind=ReconRunKind.full_t1,
                triggered_by="test",
                window_start=now - timedelta(hours=24),
                window_end=now,
            )
            s.add(run)
            await s.flush()
            run_id = run.id

            diff = ReconDiff(
                order_id=order.id,
                provider="wechat",
                provider_txn_id="TX_X",
                kind=ReconDiffKind.amount_mismatch,
                business_amount=Decimal("199.00"),
                payment_amount=Decimal("100.00"),
            )
            inserted = await _persist_diffs(s, run_id=run_id, diffs=[diff])
            assert inserted == 1
            await s.commit()

        async with test_session_factory() as s:
            o = (await s.execute(select(Order).where(Order.id == order.id))).scalar_one()
            assert o.refund_state == RefundState.manual_review

    async def test_diff_does_not_overwrite_refunded(
        self, seed_user, seed_hospital, seed_order
    ):
        from app.cron.reconcile_money import _persist_diffs
        from app.services.reconciliation.diff import ReconDiff
        from app.models.reconciliation import (
            ReconciliationRun,
            ReconRunKind,
            ReconDiffKind,
        )
        from datetime import datetime, timezone, timedelta

        user = await seed_user(phone="13700100005")
        hosp = await seed_hospital()
        order = await seed_order(user.id, hosp.id)

        async with test_session_factory() as s:
            o = (await s.execute(select(Order).where(Order.id == order.id))).scalar_one()
            o.refund_state = RefundState.refunded
            await s.commit()

        async with test_session_factory() as s:
            now = datetime.now(timezone.utc)
            run = ReconciliationRun(
                kind=ReconRunKind.full_t1,
                triggered_by="test",
                window_start=now - timedelta(hours=24),
                window_end=now,
            )
            s.add(run)
            await s.flush()
            await _persist_diffs(
                s,
                run_id=run.id,
                diffs=[
                    ReconDiff(
                        order_id=order.id,
                        provider="wechat",
                        provider_txn_id="TX_Y",
                        kind=ReconDiffKind.status_mismatch,
                    )
                ],
            )
            await s.commit()

        async with test_session_factory() as s:
            o = (await s.execute(select(Order).where(Order.id == order.id))).scalar_one()
            assert o.refund_state == RefundState.refunded


@pytest.mark.asyncio
class TestOrderResponseExposesSubstates:
    async def test_get_order_returns_payment_and_refund_state(
        self, authenticated_client, seed_hospital, seed_order
    ):
        user = authenticated_client._test_user
        hosp = await seed_hospital()
        order = await seed_order(user.id, hosp.id)
        # pay so payment_state=paid
        await authenticated_client.post(f"/api/v1/orders/{order.id}/pay")

        resp = await authenticated_client.get(f"/api/v1/orders/{order.id}")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body.get("payment_state") == "paid"
        assert body.get("refund_state") == "none"
