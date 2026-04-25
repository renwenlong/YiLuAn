"""End-to-end test fixtures (SQLite + FakeRedis, no docker).

Reuses the parent ``client`` / ``fake_redis`` / ``seed_*`` fixtures from
``tests/conftest.py``. CI doesn't need Postgres or Redis -- e2e runs in
the same harness as unit tests.

Real-credential modules (``test_payment_real.py``, ``test_sms_real.py``)
gate themselves on env vars and don't depend on these fixtures.

All tests under ``tests/e2e/`` are auto-marked ``@pytest.mark.e2e``.
"""
from __future__ import annotations

import random
import string
import time
import uuid
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.config import settings
from app.models.user import User, UserRole
from tests.conftest import test_session_factory


@pytest.fixture(autouse=True)
def _disable_slowapi_limiter():
    """Disable slowapi per-IP rate limiter for each e2e test.

    Every e2e test hits ``/api/v1/auth/send-otp`` from 127.0.0.1 and
    quickly trips the 5-per-minute cap. Rate limiting is exercised in
    the unit-test suite; e2e is about end-to-end correctness.

    Function scope (not session) so when a single ``pytest`` invocation
    runs both e2e and unit tests, the limiter is restored before unit
    tests like ``test_rate_limit.py`` execute.
    """
    try:
        from app.core.rate_limit import limiter
        original = limiter.enabled
        limiter.enabled = False
        yield
        limiter.enabled = original
    except Exception:
        yield


@pytest.fixture(autouse=True)
def _redirect_app_async_session(monkeypatch):
    """Force ``app.database.async_session`` to the in-memory test factory.

    Several services (``logging_wrapper`` for SMS, the order/expiry
    scheduler, etc.) open their own short-lived session via
    ``app.database.async_session()``. Without this redirection they
    would try to talk to the real configured Postgres -- which under
    e2e is either unavailable or shared with another harness, producing
    ``InterfaceError: another operation is in progress``.
    """
    from app import database as app_database
    monkeypatch.setattr(app_database, "async_session", test_session_factory)
    yield


def pytest_collection_modifyitems(config, items):
    for item in items:
        node = item.nodeid.replace("\\", "/")
        if "tests/e2e/" in node:
            item.add_marker(pytest.mark.e2e)


# ---------------------------------------------------------------------------
# Aliases / helpers shared across e2e tests.
# ---------------------------------------------------------------------------
@pytest.fixture
async def e2e_client(client) -> AsyncClient:
    """Alias for the parent ``client`` fixture (SQLite-backed AsyncClient)."""
    return client


@pytest.fixture
def unique_suffix() -> str:
    return "".join(random.choices(string.digits, k=5))


@pytest.fixture
def patient_phone(unique_suffix) -> str:
    return f"138{int(time.time()) % 1000:03d}{unique_suffix}"


@pytest.fixture
def companion_phone(unique_suffix) -> str:
    return f"139{int(time.time()) % 1000:03d}{unique_suffix}"


@pytest.fixture
async def login_via_otp(client, fake_redis):
    """Send-OTP -> verify-OTP via dev bypass code 000000.

    Returns ``(access_token, refresh_token, user_dict)``.
    Optional ``role`` ("patient"/"companion") triggers /me/switch-role and
    re-issues a fresh JWT carrying that role claim.
    """
    async def _do(phone: str, role: str | None = None):
        for key in (
            f"otp:rate:{phone}",
            f"otp:fail:{phone}",
            f"otp:{phone}",
            f"sms:rate:minute:{phone}",
            f"sms:rate:hour:{phone}",
        ):
            try:
                await fake_redis.delete(key)
            except Exception:
                pass
        try:
            from app.services.providers.sms.rate_limit import reset_inproc_store
            reset_inproc_store()
        except Exception:
            pass

        r = await client.post("/api/v1/auth/send-otp", json={"phone": phone})
        assert r.status_code == 200, f"send-otp failed: {r.status_code} {r.text}"

        r = await client.post(
            "/api/v1/auth/verify-otp",
            json={"phone": phone, "code": "000000"},
        )
        assert r.status_code == 200, f"verify-otp failed: {r.status_code} {r.text}"
        data = r.json()
        access, refresh, user = data["access_token"], data["refresh_token"], data["user"]

        if role is not None and user.get("role") != role:
            # Bootstrap role at the DB layer (OTP-registered users start with role=None)
            # and re-issue tokens by re-running verify-otp so the JWT carries the new
            # ``role`` / ``roles`` claims.
            uid = UUID(str(user["id"]))
            async with test_session_factory() as session:
                u = (
                    await session.execute(select(User).where(User.id == uid))
                ).scalar_one()
                u.role = UserRole(role)
                current = set((u.roles or "").split(",")) - {""}
                current.add(role)
                u.roles = ",".join(sorted(current))
                await session.commit()
            r2 = await client.post(
                "/api/v1/auth/verify-otp",
                json={"phone": phone, "code": "000000"},
            )
            assert r2.status_code == 200, r2.text
            data = r2.json()
            access, refresh, user = data["access_token"], data["refresh_token"], data["user"]

        return access, refresh, user

    return _do


@pytest.fixture
async def assign_role_e2e():
    """Promote a user to a role + add to roles list (SQLite)."""
    async def _do(user_id, role):
        uid = UUID(str(user_id))
        async with test_session_factory() as session:
            user = (
                await session.execute(select(User).where(User.id == uid))
            ).scalar_one()
            role_val = role.value if isinstance(role, UserRole) else role
            user.role = UserRole(role_val)
            current = set((user.roles or "").split(",")) - {""}
            current.add(role_val)
            user.roles = ",".join(sorted(current))
            await session.commit()
            return user

    return _do


@pytest.fixture
def admin_headers() -> dict:
    return {"X-Admin-Token": settings.admin_api_token}


# Convenience alias matching the historical e2e fixture name.
@pytest.fixture
def seed_hospital_e2e(seed_hospital):
    return seed_hospital
