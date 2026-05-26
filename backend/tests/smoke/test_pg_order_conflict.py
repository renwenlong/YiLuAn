"""W1 P0 · PG smoke — companion double-booking race regression.

Why this exists
---------------
Same backdrop as ``test_pg_prepay_race.py``: the unit suite runs on
SQLite where ``with_for_update()`` is a no-op, so any time-slot
conflict logic on the order-creation path is never properly exercised
against a real lock manager.

Scenario
--------
3 different patients concurrently ``POST /orders`` against the **same
verified companion** with the **same appointment_date + appointment_time**.

Expected contract
-----------------
Business intent (per spec):  a verified companion can only physically
serve one patient in a given time slot.  Under that contract the test
asserts:

  * exactly 1 response in {200, 201}
  * the other 2 are 4xx (conflict / business-rule rejection)
  * zero 5xx

xfail branch
------------
If the backend currently has **no** time-slot conflict check (i.e. all 3
orders are accepted), this test will fail the "exactly 1" assertion.
The xfail marker below documents that case as **REVEALS REAL BUG** —
the actual fix is owned by Programmer / Architect, not this PR.

See: PR body §1, /home/wenlongren/workspace/yiluan-analysis/keqing-qa.md T2.
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
# PG URL resolution (copy of helper in test_pg_alembic_smoke.py)
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
# Engine + app override fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
async def pg_engine():
    eng = create_async_engine(PG_URL, echo=False, pool_size=10, max_overflow=5)
    yield eng
    await eng.dispose()


@pytest.fixture(scope="module")
def pg_sessionmaker(pg_engine):
    return async_sessionmaker(
        pg_engine, class_=AsyncSession, expire_on_commit=False
    )


@pytest.fixture
async def pg_app():
    """Yield the FastAPI app with ``get_db`` overridable; cleanup on
    teardown so we don't leak override state into sibling tests."""
    from app.database import get_db as _get_db
    from app.main import app
    yield app, _get_db
    app.dependency_overrides.pop(_get_db, None)


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------

async def _seed_companion(pg_sessionmaker):
    """Create a verified companion. Returns ``(user_id,)``."""
    from app.models.companion_profile import CompanionProfile, VerificationStatus
    from app.models.user import User, UserRole

    async with pg_sessionmaker() as s:
        comp_user = User(
            phone=f"137{uuid.uuid4().int % 100_000_000:08d}",
            role=UserRole.companion,
            roles="companion",
            display_name="w1-race-companion",
        )
        s.add(comp_user)
        await s.flush()
        profile = CompanionProfile(
            user_id=comp_user.id,
            real_name="刻晴-companion",
            verification_status=VerificationStatus.verified,
        )
        s.add(profile)
        await s.commit()
        return comp_user.id


async def _seed_patient_with_hospital(pg_sessionmaker):
    """Create a patient + hospital. Returns ``(user_id, hospital_id, jwt)``."""
    from app.core.security import create_access_token
    from app.models.hospital import Hospital
    from app.models.user import User, UserRole

    async with pg_sessionmaker() as s:
        u = User(
            phone=f"138{uuid.uuid4().int % 100_000_000:08d}",
            role=UserRole.patient,
            roles="patient",
            display_name="w1-race-patient",
        )
        s.add(u)
        await s.flush()
        h = Hospital(name=f"w1-race-hosp-{uuid.uuid4().hex[:8]}")
        s.add(h)
        await s.commit()
        token = create_access_token({"sub": str(u.id), "role": "patient"})
        return u.id, h.id, token


# ---------------------------------------------------------------------------
# The test
# ---------------------------------------------------------------------------

# NOTE: marked xfail because a static code scan of backend/app/services/order/
# lifecycle.py::create_order shows no companion+time conflict guard at the
# time of writing this regression. We pin the *desired* contract here so that
# when Programmer/Architect ship the fix the xfail flips to "xpassed" and we
# can drop the marker.
@pytest.mark.xfail(
    strict=False,
    reason=(
        "REVEALS REAL BUG (W1 P0): create_order has no companion+time-slot "
        "conflict guard. 3 patients can currently double-book the same "
        "companion in the same slot. See PR body §1 / keqing-qa.md T2. "
        "Drop this xfail once the conflict check ships."
    ),
)
@pytest.mark.asyncio
async def test_concurrent_orders_against_same_companion_same_slot(
    pg_app,
    pg_sessionmaker,
):
    """3 concurrent ``POST /orders`` targeting the same companion at the
    same appointment_date / appointment_time. Only one should win.
    """
    app, _get_db = pg_app

    # Wire get_db -> PG for the lifetime of the test.
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

    # Seed: 1 companion + 3 patients (each with their own hospital is fine).
    companion_id = await _seed_companion(pg_sessionmaker)

    patient_a = await _seed_patient_with_hospital(pg_sessionmaker)
    patient_b = await _seed_patient_with_hospital(pg_sessionmaker)
    patient_c = await _seed_patient_with_hospital(pg_sessionmaker)
    patients = [patient_a, patient_b, patient_c]

    # Same slot for all three.
    appointment_date = "2027-01-15"
    appointment_time = "09:00"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        async def _post_for(patient):
            user_id, hospital_id, token = patient
            payload = {
                "service_type": "full_accompany",
                "hospital_id": str(hospital_id),
                "appointment_date": appointment_date,
                "appointment_time": appointment_time,
                "companion_id": str(companion_id),
                "description": "W1 P0 concurrent-booking regression",
            }
            return await ac.post(
                "/api/v1/orders",
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
            )

        tasks = [_post_for(p) for p in patients]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

    # No raised exceptions, no 5xx.
    for i, r in enumerate(responses):
        assert not isinstance(r, BaseException), (
            f"order #{i} raised {type(r).__name__}: {r!r}"
        )
    statuses = [r.status_code for r in responses]
    bodies = [r.text for r in responses]
    assert not [s for s in statuses if s >= 500], (
        f"order-creation race produced 5xx: statuses={statuses} bodies={bodies}"
    )

    # Desired contract: exactly one winner.
    winners = [s for s in statuses if s in (200, 201)]
    assert len(winners) == 1, (
        f"Expected exactly 1 winner for the same companion+slot, got "
        f"{len(winners)}. statuses={statuses}. "
        f"If this fails with len(winners)==3 the W1 P0 conflict gap is "
        f"confirmed in production-shape DB — see xfail reason."
    )
