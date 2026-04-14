"""Tests for active order handling during account deletion (D-009).

Covers:
1. No active orders → normal deletion
2. Pending (created) orders → cancel, no refund
3. Accepted orders with payment → cancel + 100% refund
4. In-progress orders with payment → cancel + 50% refund
5. Mixed-status orders → each handled correctly
"""

import pytest
from httpx import AsyncClient

from app.models.order import OrderStatus, ServiceType
from app.models.payment import Payment
from app.models.user import UserRole
from tests.conftest import test_session_factory


@pytest.mark.asyncio
async def test_delete_no_active_orders(authenticated_client, seed_hospital, seed_order):
    """Deletion with only completed orders — no cancellations, no refunds."""
    user = authenticated_client._test_user
    hospital = await seed_hospital()

    order_completed = await seed_order(
        user.id, hospital.id, status=OrderStatus.completed
    )

    resp = await authenticated_client.delete("/api/v1/users/me")
    assert resp.status_code == 200

    async with test_session_factory() as session:
        from app.models.order import Order

        order = await session.get(Order, order_completed.id)
        assert order.status == OrderStatus.completed  # untouched


@pytest.mark.asyncio
async def test_delete_pending_order_cancelled_no_refund(
    authenticated_client, seed_hospital, seed_order
):
    """Pending (created) order → cancelled, no refund created."""
    user = authenticated_client._test_user
    hospital = await seed_hospital()

    order = await seed_order(user.id, hospital.id, status=OrderStatus.created)

    resp = await authenticated_client.delete("/api/v1/users/me")
    assert resp.status_code == 200

    async with test_session_factory() as session:
        from app.models.order import Order

        cancelled = await session.get(Order, order.id)
        assert cancelled.status == OrderStatus.cancelled_by_patient

        # No refund record should exist
        from sqlalchemy import select

        stmt = select(Payment).where(
            Payment.order_id == order.id, Payment.payment_type == "refund"
        )
        result = await session.execute(stmt)
        assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_delete_accepted_order_refund_full(
    authenticated_client, seed_hospital, seed_order, seed_payment
):
    """Accepted order with payment → cancelled + 100% refund."""
    user = authenticated_client._test_user
    hospital = await seed_hospital()

    order = await seed_order(
        user.id, hospital.id, status=OrderStatus.accepted, price=299.0
    )
    await seed_payment(order.id, user.id, amount=299.0)

    resp = await authenticated_client.delete("/api/v1/users/me")
    assert resp.status_code == 200

    async with test_session_factory() as session:
        from app.models.order import Order
        from sqlalchemy import select

        cancelled = await session.get(Order, order.id)
        assert cancelled.status == OrderStatus.cancelled_by_patient

        # Full refund record
        stmt = select(Payment).where(
            Payment.order_id == order.id, Payment.payment_type == "refund"
        )
        result = await session.execute(stmt)
        refund = result.scalar_one_or_none()
        assert refund is not None
        assert refund.amount == 299.0
        assert refund.status == "success"


@pytest.mark.asyncio
async def test_delete_in_progress_order_refund_half(
    authenticated_client, seed_hospital, seed_order, seed_payment
):
    """In-progress order with payment → cancelled + 50% refund."""
    user = authenticated_client._test_user
    hospital = await seed_hospital()

    order = await seed_order(
        user.id, hospital.id, status=OrderStatus.in_progress, price=200.0
    )
    await seed_payment(order.id, user.id, amount=200.0)

    resp = await authenticated_client.delete("/api/v1/users/me")
    assert resp.status_code == 200

    async with test_session_factory() as session:
        from app.models.order import Order
        from sqlalchemy import select

        cancelled = await session.get(Order, order.id)
        assert cancelled.status == OrderStatus.cancelled_by_patient

        # 50% refund
        stmt = select(Payment).where(
            Payment.order_id == order.id, Payment.payment_type == "refund"
        )
        result = await session.execute(stmt)
        refund = result.scalar_one_or_none()
        assert refund is not None
        assert refund.amount == 100.0
        assert refund.status == "success"


@pytest.mark.asyncio
async def test_delete_mixed_status_orders(
    authenticated_client, seed_hospital, seed_order, seed_payment
):
    """Mixed orders: created (no refund), accepted (100% refund),
    in_progress (50% refund), completed (untouched)."""
    user = authenticated_client._test_user
    hospital = await seed_hospital()

    order_created = await seed_order(
        user.id, hospital.id, status=OrderStatus.created, price=149.0
    )
    order_accepted = await seed_order(
        user.id, hospital.id, status=OrderStatus.accepted, price=199.0
    )
    await seed_payment(order_accepted.id, user.id, amount=199.0)

    order_in_progress = await seed_order(
        user.id, hospital.id, status=OrderStatus.in_progress, price=299.0
    )
    await seed_payment(order_in_progress.id, user.id, amount=299.0)

    order_completed = await seed_order(
        user.id, hospital.id, status=OrderStatus.completed, price=299.0
    )

    resp = await authenticated_client.delete("/api/v1/users/me")
    assert resp.status_code == 200

    async with test_session_factory() as session:
        from app.models.order import Order
        from sqlalchemy import select

        # created → cancelled, no refund
        o1 = await session.get(Order, order_created.id)
        assert o1.status == OrderStatus.cancelled_by_patient
        stmt = select(Payment).where(
            Payment.order_id == order_created.id, Payment.payment_type == "refund"
        )
        assert (await session.execute(stmt)).scalar_one_or_none() is None

        # accepted → cancelled, 100% refund
        o2 = await session.get(Order, order_accepted.id)
        assert o2.status == OrderStatus.cancelled_by_patient
        stmt = select(Payment).where(
            Payment.order_id == order_accepted.id, Payment.payment_type == "refund"
        )
        refund_accepted = (await session.execute(stmt)).scalar_one_or_none()
        assert refund_accepted is not None
        assert refund_accepted.amount == 199.0

        # in_progress → cancelled, 50% refund
        o3 = await session.get(Order, order_in_progress.id)
        assert o3.status == OrderStatus.cancelled_by_patient
        stmt = select(Payment).where(
            Payment.order_id == order_in_progress.id, Payment.payment_type == "refund"
        )
        refund_ip = (await session.execute(stmt)).scalar_one_or_none()
        assert refund_ip is not None
        assert refund_ip.amount == 149.5  # 299.0 * 0.5

        # completed → untouched
        o4 = await session.get(Order, order_completed.id)
        assert o4.status == OrderStatus.completed


@pytest.mark.asyncio
async def test_delete_accepted_order_no_payment_no_refund(
    authenticated_client, seed_hospital, seed_order
):
    """Accepted order with NO payment → cancelled, no refund record."""
    user = authenticated_client._test_user
    hospital = await seed_hospital()

    order = await seed_order(user.id, hospital.id, status=OrderStatus.accepted)

    resp = await authenticated_client.delete("/api/v1/users/me")
    assert resp.status_code == 200

    async with test_session_factory() as session:
        from app.models.order import Order
        from sqlalchemy import select

        cancelled = await session.get(Order, order.id)
        assert cancelled.status == OrderStatus.cancelled_by_patient

        stmt = select(Payment).where(
            Payment.order_id == order.id, Payment.payment_type == "refund"
        )
        assert (await session.execute(stmt)).scalar_one_or_none() is None
