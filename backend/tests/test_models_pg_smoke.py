"""PG-only model smoke tests — TD-CI-01 closure.

These tests run **only** when PG_SMOKE=1 (set by the alembic-smoke workflow).
They are skipped during the regular SQLite test run because the goal is to
verify behaviours that are **invisible to SQLite + create_all()**:

  * Native PG enum types (orderstatus, servicetype, verificationstatus)
    — including the two recently-added orderstatus values
    (``rejected_by_companion`` + ``expired``) that 4-17 migration audit
    flagged as missing in some early dev DBs.
  * The Payment model's 4 columns added in
    ``b7c8d9e0f1a2_align_payments_columns_and_verify_enums`` —
    trade_no / prepay_id / refund_id / callback_raw — round-trip insert/query.
  * Payment uniqueness constraint (order_id + payment_type) actually enforced
    by the DB, not just declared in the ORM.

Pre-condition: alembic upgrade head has been run against the target PG
(handled by the workflow). Tests do NOT call create_all() — they rely on
the migrated schema.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Skip the whole module unless explicitly opted-in (CI workflow sets PG_SMOKE=1).
pytestmark = [
    pytest.mark.skipif(
        os.environ.get("PG_SMOKE") != "1",
        reason="PG smoke tests only run in alembic-smoke workflow (set PG_SMOKE=1)",
    ),
    pytest.mark.asyncio,
]


PG_URL = os.environ.get(
    "DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/yiluan_smoke"
)


@pytest.fixture(scope="module")
def pg_engine():
    eng = create_async_engine(PG_URL, echo=False, pool_pre_ping=True)
    yield eng
    asyncio.get_event_loop().run_until_complete(eng.dispose())


@pytest.fixture
async def session(pg_engine) -> AsyncSession:
    Session = async_sessionmaker(pg_engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as s:
        yield s
        # Best-effort cleanup of anything we inserted (FK-safe order)
        for tbl in (
            "reviews",
            "chat_messages",
            "payments",
            "order_status_history",
            "orders",
            "patient_profiles",
            "companion_profiles",
            "device_tokens",
            "notifications",
            "users",
            "hospitals",
        ):
            try:
                await s.execute(text(f"DELETE FROM {tbl}"))
            except Exception:
                await s.rollback()
        await s.commit()


# ---------------------------------------------------------------------------
# Test 1: Alembic landed at head
# ---------------------------------------------------------------------------
async def test_alembic_version_table_populated(session):
    res = await session.execute(text("SELECT version_num FROM alembic_version"))
    row = res.first()
    assert row is not None, "alembic_version table missing or empty"
    assert row[0], f"alembic_version row has empty version_num: {row}"


# ---------------------------------------------------------------------------
# Test 2: orderstatus enum has BOTH recently-added values (4-17 lesson)
# ---------------------------------------------------------------------------
async def test_orderstatus_enum_has_rejected_and_expired(session):
    res = await session.execute(
        text(
            "SELECT enumlabel FROM pg_enum e "
            "JOIN pg_type t ON t.oid = e.enumtypid "
            "WHERE t.typname = 'orderstatus' ORDER BY enumlabel"
        )
    )
    labels = {r[0] for r in res.fetchall()}
    assert "rejected_by_companion" in labels, (
        f"orderstatus enum missing 'rejected_by_companion' (4-17 regression). "
        f"Got: {sorted(labels)}"
    )
    assert "expired" in labels, (
        f"orderstatus enum missing 'expired' (4-17 regression). Got: {sorted(labels)}"
    )


# ---------------------------------------------------------------------------
# Test 3: Payment model has all 4 align-payments columns; insert/query
# ---------------------------------------------------------------------------
async def test_payment_columns_round_trip(session):
    from app.models.payment import Payment
    from app.models.user import User

    user = User(phone=f"139{uuid.uuid4().int % 10**8:08d}", roles="patient")
    session.add(user)
    await session.commit()
    await session.refresh(user)

    order_id = uuid.uuid4()
    payment = Payment(
        order_id=order_id,
        user_id=user.id,
        amount=299.0,
        payment_type="pay",
        status="success",
        trade_no=f"WX{uuid.uuid4().hex[:16]}",
        prepay_id=f"prepay_{uuid.uuid4().hex[:24]}",
        refund_id=None,
        callback_raw='{"raw": "wechat callback body"}',
    )
    session.add(payment)
    await session.commit()
    await session.refresh(payment)

    # Read back and verify all 4 align-payments columns round-trip
    res = await session.execute(select(Payment).where(Payment.id == payment.id))
    got = res.scalar_one()
    assert got.trade_no == payment.trade_no
    assert got.prepay_id == payment.prepay_id
    assert got.refund_id is None
    assert "wechat callback body" in got.callback_raw


# ---------------------------------------------------------------------------
# Test 4: Payment unique (order_id, payment_type) constraint enforced by PG
# ---------------------------------------------------------------------------
async def test_payment_unique_constraint_enforced(session):
    from app.models.payment import Payment
    from app.models.user import User

    user = User(phone=f"138{uuid.uuid4().int % 10**8:08d}", roles="patient")
    session.add(user)
    await session.commit()
    await session.refresh(user)

    order_id = uuid.uuid4()
    p1 = Payment(order_id=order_id, user_id=user.id, amount=100.0, payment_type="pay", status="success")
    session.add(p1)
    await session.commit()

    # A refund on the same order should be allowed (different payment_type)
    p2 = Payment(order_id=order_id, user_id=user.id, amount=50.0, payment_type="refund", status="success")
    session.add(p2)
    await session.commit()

    # A second 'pay' for the same order must fail (uq_payment_order_type)
    dup = Payment(order_id=order_id, user_id=user.id, amount=100.0, payment_type="pay", status="success")
    session.add(dup)
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


# ---------------------------------------------------------------------------
# Test 5: Order with both new enum values can be inserted (4-17 regression)
# ---------------------------------------------------------------------------
async def test_order_insert_rejected_and_expired(session):
    from app.models.hospital import Hospital
    from app.models.order import Order, OrderStatus, ServiceType
    from app.models.user import User

    patient = User(phone=f"137{uuid.uuid4().int % 10**8:08d}", roles="patient")
    hosp = Hospital(name="北京协和医院 (smoke)", address="东城区", level="三甲")
    session.add_all([patient, hosp])
    await session.commit()
    await session.refresh(patient)
    await session.refresh(hosp)

    for status in (OrderStatus.rejected_by_companion, OrderStatus.expired):
        order = Order(
            order_number=f"YLA{uuid.uuid4().hex[:12].upper()}",
            patient_id=patient.id,
            hospital_id=hosp.id,
            service_type=ServiceType.full_accompany,
            status=status,
            appointment_date="2026-05-01",
            appointment_time="09:00",
            price=299.0,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(order)
        await session.commit()
        await session.refresh(order)
        assert order.status == status, f"failed to round-trip {status}"


# ---------------------------------------------------------------------------
# Test 6: ServiceType enum complete
# ---------------------------------------------------------------------------
async def test_servicetype_enum_complete(session):
    res = await session.execute(
        text(
            "SELECT enumlabel FROM pg_enum e "
            "JOIN pg_type t ON t.oid = e.enumtypid "
            "WHERE t.typname = 'servicetype'"
        )
    )
    labels = {r[0] for r in res.fetchall()}
    assert {"full_accompany", "half_accompany", "errand"}.issubset(labels), (
        f"servicetype enum incomplete: {sorted(labels)}"
    )


# ---------------------------------------------------------------------------
# Test 7: VerificationStatus enum
# ---------------------------------------------------------------------------
async def test_verificationstatus_enum_complete(session):
    res = await session.execute(
        text(
            "SELECT enumlabel FROM pg_enum e "
            "JOIN pg_type t ON t.oid = e.enumtypid "
            "WHERE t.typname = 'verificationstatus'"
        )
    )
    labels = {r[0] for r in res.fetchall()}
    assert "verified" in labels, f"verificationstatus missing 'verified': {sorted(labels)}"


# ---------------------------------------------------------------------------
# Test 8: Notification + DeviceToken insert (touches NotificationType enum)
# ---------------------------------------------------------------------------
async def test_notification_and_device_token_insert(session):
    from app.models.device_token import DeviceToken
    from app.models.notification import Notification, NotificationType
    from app.models.user import User

    user = User(phone=f"136{uuid.uuid4().int % 10**8:08d}", roles="patient")
    session.add(user)
    await session.commit()
    await session.refresh(user)

    notif = Notification(
        user_id=user.id,
        type=NotificationType.system,
        title="smoke",
        body="pg-smoke notification",
    )
    device = DeviceToken(
        user_id=user.id,
        token=f"dev_{uuid.uuid4().hex}",
        device_type="ios",
    )
    session.add_all([notif, device])
    await session.commit()
    await session.refresh(notif)
    await session.refresh(device)
    assert notif.id is not None
    assert device.id is not None
