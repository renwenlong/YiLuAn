"""TD-ORDER-01 regression: close_pending_payment must run exactly once per
expired order per expiry tick.

Background
----------
``backend/app/services/order/expiry.py`` previously contained the entire
"pending close" block twice in a row, so each expiry cycle invoked
``PaymentService.close_pending_payment`` *twice* per order. The mock PSP's
idempotency hid the bug; against a real WeChat PSP the second close would
overwrite the first ``[order_expired]`` audit trace with ``close_failed``.

These tests pin the contract: one close call per expired order, even
when the batch contains many orders.
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.models.order import Order, OrderStatus, ServiceType
from app.models.payment import Payment

from tests.conftest import test_session_factory


def _make_expired_order(patient_id, hospital_id):
    return Order(
        order_number=f"YLA{uuid.uuid4().hex[:12].upper()}",
        patient_id=patient_id,
        hospital_id=hospital_id,
        service_type=ServiceType.full_accompany,
        status=OrderStatus.created,
        appointment_date="2026-05-01",
        appointment_time="09:00",
        price=299.0,
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )


async def _seed_pending(session, patient_id, hospital_id):
    order = _make_expired_order(patient_id, hospital_id)
    session.add(order)
    await session.flush()
    payment = Payment(
        order_id=order.id,
        user_id=patient_id,
        amount=299.0,
        payment_type="pay",
        status="pending",
        trade_no=f"MOCK_{uuid.uuid4().hex[:16].upper()}",
    )
    session.add(payment)
    await session.flush()
    return order


@pytest.mark.asyncio
class TestExpiryCloseCalledOnce:
    """TD-ORDER-01: pin call-count invariant for close_pending_payment."""

    async def test_close_pending_payment_called_exactly_once_per_expired_order(
        self, seed_user, seed_hospital
    ):
        """Single expired order with a pending payment → exactly one close call."""
        from app.models.user import UserRole
        from app.services.order import OrderService

        user = await seed_user(role=UserRole.patient)
        hospital = await seed_hospital()

        async with test_session_factory() as session:
            order = await _seed_pending(session, user.id, hospital.id)
            await session.commit()
            order_id = order.id

        with patch(
            "app.services.payment_service.PaymentService.close_pending_payment",
            new_callable=AsyncMock,
            return_value=None,
        ) as mock_close:
            async with test_session_factory() as session:
                svc = OrderService(session)
                result = await svc.check_expired_orders()
                await session.commit()

        assert len(result) == 1
        assert result[0].status == OrderStatus.expired
        mock_close.assert_called_once()
        called_order_ids = [c.args[0] for c in mock_close.call_args_list]
        assert called_order_ids == [order_id], (
            "TD-ORDER-01: close_pending_payment must run exactly once per "
            f"expired order; observed call args: {called_order_ids}"
        )

    async def test_batch_expired_orders_each_closed_exactly_once(
        self, seed_user, seed_hospital
    ):
        """Multiple expired orders in one tick → each gets exactly one close."""
        from app.models.user import UserRole
        from app.services.order import OrderService

        hospital = await seed_hospital()
        users = [
            await seed_user(phone=f"139{i:08d}", role=UserRole.patient)
            for i in range(3)
        ]

        seeded_ids = []
        async with test_session_factory() as session:
            for u in users:
                order = await _seed_pending(session, u.id, hospital.id)
                seeded_ids.append(order.id)
            await session.commit()

        with patch(
            "app.services.payment_service.PaymentService.close_pending_payment",
            new_callable=AsyncMock,
            return_value=None,
        ) as mock_close:
            async with test_session_factory() as session:
                svc = OrderService(session)
                result = await svc.check_expired_orders()
                await session.commit()

        assert len(result) == len(users)
        assert mock_close.call_count == len(users), (
            f"TD-ORDER-01: expected {len(users)} close calls (one per "
            f"expired order), got {mock_close.call_count}"
        )

        called_order_ids = sorted(c.args[0] for c in mock_close.call_args_list)
        assert called_order_ids == sorted(seeded_ids), (
            "Each expired order must be closed exactly once and only its own id."
        )
