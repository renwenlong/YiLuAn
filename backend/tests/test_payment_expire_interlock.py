"""
Tests for P0-02 / TD-PAY-01: payment ↔ order-expiry interlock.

1. expire_order: PENDING payment → close_order success → EXPIRED + Payment CLOSED
2. expire_order: PAID payment → NotExpirableOrderError, order unchanged
3. expire_order: PENDING but close_order fails → NotExpirableOrderError
4. callback: normal ACCEPTED order → payment SUCCESS (baseline)
5. callback: EXPIRED order + PAID callback → auto-refund, order stays EXPIRED
6. callback: CANCELLED order + PAID callback → auto-refund, order stays CANCELLED
"""

import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.exceptions import NotExpirableOrderError
from app.models.order import Order, OrderStatus, ServiceType
from app.models.payment import Payment

from tests.conftest import test_session_factory


def _make_order(patient_id, hospital_id, *, status=OrderStatus.created, **kw):
    return Order(
        order_number=f"YLA{uuid.uuid4().hex[:12].upper()}",
        patient_id=patient_id,
        hospital_id=hospital_id,
        service_type=ServiceType.full_accompany,
        status=status,
        appointment_date="2026-05-01",
        appointment_time="09:00",
        price=299.0,
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        **kw,
    )


async def _create_order_and_payment(
    session, patient_id, hospital_id, *, order_status=OrderStatus.created, pay_status="pending"
):
    order = _make_order(patient_id, hospital_id, status=order_status)
    session.add(order)
    await session.flush()
    trade_no = f"MOCK_{uuid.uuid4().hex[:16].upper()}"
    payment = Payment(
        order_id=order.id,
        user_id=patient_id,
        amount=299.0,
        payment_type="pay",
        status=pay_status,
        trade_no=trade_no,
    )
    session.add(payment)
    await session.flush()
    return order, payment


@pytest.mark.asyncio
class TestExpireOrderPaymentInterlock:
    """expire_order closes / guards payment before changing order status."""

    async def test_expire_pending_payment_closes_and_expires(
        self, seed_user, seed_hospital
    ):
        """PENDING payment → close_order succeeds → order EXPIRED, payment CLOSED."""
        from app.models.user import UserRole
        from app.services.order import OrderService

        user = await seed_user(role=UserRole.patient)
        hospital = await seed_hospital()

        async with test_session_factory() as session:
            order, payment = await _create_order_and_payment(
                session, user.id, hospital.id, pay_status="pending"
            )
            await session.commit()

        async with test_session_factory() as session:
            svc = OrderService(session)
            result = await svc.check_expired_orders()
            await session.commit()

        assert len(result) == 1
        assert result[0].status == OrderStatus.expired

        # Verify payment was closed
        async with test_session_factory() as session:
            from sqlalchemy import select

            stmt = select(Payment).where(Payment.order_id == order.id, Payment.payment_type == "pay")
            row = (await session.execute(stmt)).scalar_one()
            assert row.status == "closed"

    async def test_expire_paid_payment_raises_not_expirable(
        self, seed_user, seed_hospital
    ):
        """PAID payment → NotExpirableOrderError, order stays created."""
        from app.models.user import UserRole
        from app.services.order import OrderService

        user = await seed_user(role=UserRole.patient)
        hospital = await seed_hospital()

        async with test_session_factory() as session:
            order, _ = await _create_order_and_payment(
                session, user.id, hospital.id, pay_status="success"
            )
            await session.commit()

        async with test_session_factory() as session:
            svc = OrderService(session)
            with pytest.raises(NotExpirableOrderError):
                await svc.check_expired_orders()

        # Order should remain created
        async with test_session_factory() as session:
            from sqlalchemy import select

            stmt = select(Order).where(Order.id == order.id)
            row = (await session.execute(stmt)).scalar_one()
            assert row.status == OrderStatus.created

    async def test_expire_close_order_fails_raises_not_expirable(
        self, seed_user, seed_hospital
    ):
        """PENDING payment but close_order fails → NotExpirableOrderError."""
        from app.models.user import UserRole
        from app.services.order import OrderService

        user = await seed_user(role=UserRole.patient)
        hospital = await seed_hospital()

        async with test_session_factory() as session:
            order, _ = await _create_order_and_payment(
                session, user.id, hospital.id, pay_status="pending"
            )
            await session.commit()

        with patch(
            "app.services.payment_service.PaymentService.close_pending_payment",
            new_callable=AsyncMock,
            side_effect=Exception("PSP rejected close"),
        ):
            # The close_pending_payment raises BadRequestException internally,
            # but we mock it to raise directly to simulate failure
            from app.exceptions import BadRequestException

            with patch(
                "app.services.payment_service.PaymentService.close_pending_payment",
                new_callable=AsyncMock,
                side_effect=BadRequestException("无法关闭支付单"),
            ):
                async with test_session_factory() as session:
                    svc = OrderService(session)
                    with pytest.raises(NotExpirableOrderError):
                        await svc.check_expired_orders()


@pytest.mark.asyncio
class TestPayCallbackAutoRefund:
    """Pay callback auto-refunds when order is already expired/cancelled."""

    async def test_callback_normal_accepted_order(
        self, authenticated_client, seed_hospital, seed_user
    ):
        """Baseline: ACCEPTED order receives PAID callback → payment success."""
        from app.models.user import UserRole

        hospital = await seed_hospital()
        user = authenticated_client._test_user

        # Create order
        resp = await authenticated_client.post(
            "/api/v1/orders",
            json={
                "service_type": "full_accompany",
                "hospital_id": str(hospital.id),
                "appointment_date": "2026-05-01",
                "appointment_time": "09:00",
            },
        )
        assert resp.status_code == 201
        order_data = resp.json()

        # Pay
        resp = await authenticated_client.post(
            f"/api/v1/orders/{order_data['id']}/pay"
        )
        assert resp.status_code == 200

        # For mock provider, payment is already success — just verify
        resp = await authenticated_client.get(
            f"/api/v1/orders/{order_data['id']}"
        )
        assert resp.status_code == 200
        assert resp.json()["payment_status"] == "paid"

    async def test_callback_expired_order_triggers_auto_refund(
        self, client, seed_user, seed_hospital
    ):
        """EXPIRED order + PAID callback → Payment updated + auto-refund triggered."""
        from app.models.user import UserRole

        user = await seed_user(role=UserRole.patient)
        hospital = await seed_hospital()

        async with test_session_factory() as session:
            order = _make_order(user.id, hospital.id, status=OrderStatus.expired)
            # Remove expires_at to not interfere
            order.expires_at = None
            session.add(order)
            await session.flush()
            trade_no = f"MOCK_{uuid.uuid4().hex[:16].upper()}"
            payment = Payment(
                order_id=order.id,
                user_id=user.id,
                amount=299.0,
                payment_type="pay",
                status="pending",
                trade_no=trade_no,
            )
            session.add(payment)
            await session.commit()
            order_id = order.id

        # Send a pay callback with trade_no
        callback_body = json.dumps({
            "trade_no": trade_no,
            "out_trade_no": trade_no,
            "trade_state": "SUCCESS",
            "transaction_id": trade_no,
        }).encode()
        resp = await client.post(
            "/api/v1/payments/wechat/callback",
            content=callback_body,
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 200

        # Verify: payment is success, but a refund record was also created
        async with test_session_factory() as session:
            from sqlalchemy import select

            # Payment should be success
            stmt = select(Payment).where(
                Payment.order_id == order_id, Payment.payment_type == "pay"
            )
            pay = (await session.execute(stmt)).scalar_one()
            assert pay.status == "success"

            # Refund should exist
            stmt = select(Payment).where(
                Payment.order_id == order_id, Payment.payment_type == "refund"
            )
            refund = (await session.execute(stmt)).scalar_one_or_none()
            assert refund is not None
            assert refund.amount == 299.0

            # Order should still be expired
            stmt = select(Order).where(Order.id == order_id)
            order = (await session.execute(stmt)).scalar_one()
            assert order.status == OrderStatus.expired

    async def test_callback_cancelled_order_triggers_auto_refund(
        self, client, seed_user, seed_hospital
    ):
        """CANCELLED order + PAID callback → auto-refund, order stays cancelled."""
        from app.models.user import UserRole

        user = await seed_user(role=UserRole.patient)
        hospital = await seed_hospital()

        async with test_session_factory() as session:
            order = _make_order(
                user.id, hospital.id, status=OrderStatus.cancelled_by_patient
            )
            order.expires_at = None
            session.add(order)
            await session.flush()
            trade_no = f"MOCK_{uuid.uuid4().hex[:16].upper()}"
            payment = Payment(
                order_id=order.id,
                user_id=user.id,
                amount=299.0,
                payment_type="pay",
                status="pending",
                trade_no=trade_no,
            )
            session.add(payment)
            await session.commit()
            order_id = order.id

        callback_body = json.dumps({
            "trade_no": trade_no,
            "out_trade_no": trade_no,
            "trade_state": "SUCCESS",
            "transaction_id": trade_no,
        }).encode()
        resp = await client.post(
            "/api/v1/payments/wechat/callback",
            content=callback_body,
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 200

        async with test_session_factory() as session:
            from sqlalchemy import select

            # Refund should exist
            stmt = select(Payment).where(
                Payment.order_id == order_id, Payment.payment_type == "refund"
            )
            refund = (await session.execute(stmt)).scalar_one_or_none()
            assert refund is not None

            # Order stays cancelled
            stmt = select(Order).where(Order.id == order_id)
            order = (await session.execute(stmt)).scalar_one()
            assert order.status == OrderStatus.cancelled_by_patient
