"""W1 P0 · PG smoke — concurrent prepay race regression.

Why this exists
---------------
The unit suite runs against SQLite in-memory.  ``with_for_update()`` is a
**no-op** on SQLite, which means the order-row lock in
``OrderService._get_order_for_update_or_404`` has never been exercised by
the test suite.  See the TODO at
``backend/tests/test_payment_concurrent.py:30``:

    # TODO: Fix the race condition before production deployment.

This file pins the contract under a real Postgres where ``SELECT ... FOR
UPDATE`` actually serialises the five concurrent ``POST /orders/{id}/pay``
requests.

Contract
--------
Given a freshly created (unpaid) order and 5 concurrent ``POST
/orders/{id}/pay`` requests:

  * **Exactly 1** response is 2xx (200/201) — that's the winner.
  * The remaining 4 are **400** (friendly "订单已支付，请勿重复操作" /
    similar BadRequest).
  * Zero 5xx, zero raw ``IntegrityError`` / ``UNIQUE`` leaks to the
    client.

If the contract is violated, this test should FAIL (not xfail) — it means
the race exists in production-shape DB.

Implementation notes
--------------------
* We override ``app.dependency_overrides[get_db]`` so the FastAPI app
  routes its session through a PG-backed ``async_sessionmaker`` instead
  of the global SQLite test factory.
* Each concurrent request gets its own ``AsyncSession`` (FastAPI
  dependency-per-request), so ``FOR UPDATE`` actually serialises across
  sessions — which is the whole point.
* Seed data is created via the same PG engine, then a JWT for the
  seeded user is minted so we don't need to mock auth.
* All seeded rows live in unique-UUID space; we do not clean up
  (consistent with the existing ``test_pg_alembic_smoke.py`` pattern of
  letting the smoke DB accumulate harmless rows).
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

pytestmark = pytest.mark.smoke


# ---------------------------------------------------------------------------
# PG URL resolution — mirrors test_pg_alembic_smoke.py
# ---------------------------------------------------------------------------

def _resolve_pg_url() -> str:
    url = (
        os.environ.get("SMOKE_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
        or "postgresql+asyncpg://postgres:postgres@localhost:5432/yiluan"
    )
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


PG_URL = _resolve_pg_url()


# ---------------------------------------------------------------------------
# PG engine + override fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
async def pg_engine():
    """Module-scoped PG engine. Smaller pool than prod since we only
    fire ≤10 concurrent requests in this file."""
    eng = create_async_engine(
        PG_URL,
        echo=False,
        pool_size=10,
        max_overflow=5,
    )
    yield eng
    await eng.dispose()


@pytest.fixture(scope="module")
def pg_sessionmaker(pg_engine):
    return async_sessionmaker(
        pg_engine, class_=AsyncSession, expire_on_commit=False
    )


@pytest.fixture
async def pg_app_client(pg_sessionmaker):
    """FastAPI client whose ``get_db`` dependency is wired to PG.

    Critically: each request gets its OWN session (FastAPI dependency-
    per-request), which is what makes ``SELECT ... FOR UPDATE`` actually
    serialise — the smoke we cannot get from SQLite.
    """
    from app.database import get_db as _get_db
    from app.main import app

    async def _pg_get_db():
        async with pg_sessionmaker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    app.dependency_overrides[_get_db] = _pg_get_db
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
        app.dependency_overrides.pop(_get_db, None)


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------

async def _seed_user_hospital_order(pg_sessionmaker):
    """Create a unique (user, hospital, order) triple in PG and return
    ``(user_id, order_id, jwt_token)``.

    Status starts as ``created`` so it is payable.
    """
    from app.core.security import create_access_token
    from app.models.hospital import Hospital
    from app.models.order import Order, OrderStatus, ServiceType
    from app.models.user import User, UserRole

    async with pg_sessionmaker() as s:
        user = User(
            phone=f"139{uuid.uuid4().int % 100_000_000:08d}",
            role=UserRole.patient,
            roles="patient",
            display_name="w1-prepay-race",
        )
        s.add(user)
        await s.flush()

        hospital = Hospital(name=f"w1-race-hosp-{uuid.uuid4().hex[:8]}")
        s.add(hospital)
        await s.flush()

        order = Order(
            order_number=f"YLA{uuid.uuid4().hex[:12].upper()}",
            patient_id=user.id,
            hospital_id=hospital.id,
            service_type=ServiceType.full_accompany,
            status=OrderStatus.created,
            appointment_date="2026-12-31",
            appointment_time="09:00",
            price=299.0,
            hospital_name=hospital.name,
            patient_name=user.display_name,
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        s.add(order)
        await s.commit()
        await s.refresh(user)
        await s.refresh(order)

        token = create_access_token({"sub": str(user.id), "role": "patient"})
        return user.id, order.id, token


# ---------------------------------------------------------------------------
# The test
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_concurrent_prepay_on_pg_serialises_to_one_winner(
    pg_app_client: AsyncClient,
    pg_sessionmaker,
):
    """5 concurrent ``POST /orders/{id}/pay`` against the same order.

    Contract under real PG (``SELECT ... FOR UPDATE`` is enforced):
      * exactly 1 response in {200, 201}
      * remaining 4 are 400 (friendly BadRequest)
      * zero 5xx, zero IntegrityError leaks
    """
    user_id, order_id, token = await _seed_user_hospital_order(pg_sessionmaker)

    pg_app_client.headers["Authorization"] = f"Bearer {token}"

    tasks = [
        pg_app_client.post(f"/api/v1/orders/{order_id}/pay")
        for _ in range(5)
    ]
    responses = await asyncio.gather(*tasks, return_exceptions=True)

    # Hard fail on any raised exception (e.g. IntegrityError bubbling).
    for i, r in enumerate(responses):
        assert not isinstance(r, BaseException), (
            f"prepay #{i} raised {type(r).__name__}: {r!r} — "
            "IntegrityError / UNIQUE leak across the API boundary is "
            "exactly the W1 P0 bug we're guarding against."
        )

    statuses = [r.status_code for r in responses]
    bodies = [r.text for r in responses]

    server_errors = [s for s in statuses if s >= 500]
    assert not server_errors, (
        f"prepay race produced server error(s) {server_errors} — "
        f"statuses={statuses} bodies={bodies}"
    )

    winners = [s for s in statuses if s in (200, 201)]
    rejects = [s for s in statuses if s == 400]

    assert len(winners) == 1, (
        f"Expected exactly 1 winner, got {len(winners)}. "
        f"statuses={statuses} — under FOR UPDATE serialisation only one "
        f"caller may create the prepay row."
    )
    assert len(rejects) == 4, (
        f"Expected 4 friendly 400 rejections, got {len(rejects)}. "
        f"statuses={statuses}"
    )

    # And no body should leak SQLAlchemy internals (defense in depth).
    for b in bodies:
        assert "IntegrityError" not in b, f"IntegrityError leaked: {b}"
        assert "UNIQUE constraint" not in b, f"UNIQUE leaked: {b}"
