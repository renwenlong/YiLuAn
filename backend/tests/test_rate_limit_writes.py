"""W1-S3: route-level rate limit assertions for write/auth endpoints.

The default ``conftest._disable_rate_limiter`` autouse fixture disables the
slowapi limiter for the rest of the suite (most tests would otherwise blow
through the 30/min cap). Here we explicitly re-enable it and verify the
decorators actually fire 429s.

We do **not** exercise the underlying business logic (creating a real order
needs payment fixtures etc.) — once the request reaches the rate-limit
decorator we either get the limiter's 429 or the route's own error/200,
both of which are sufficient to prove the decorator is wired up. The
assertion is: *somewhere in the burst, a 429 appears*.
"""
from __future__ import annotations

import pytest

from app.core.rate_limit import limiter


@pytest.fixture
def _enable_limiter():
    """Re-enable the global limiter and reset its in-memory storage before
    each rate-limit test so previous tests' counters don't bleed in."""
    limiter.enabled = True
    # slowapi >= 0.1.9: in-memory storage exposes .reset()
    try:
        limiter._storage.reset()  # type: ignore[attr-defined]
    except Exception:
        pass
    yield
    limiter.enabled = False


@pytest.mark.asyncio
async def test_orders_create_is_rate_limited(_enable_limiter, authenticated_client):
    """POST /api/v1/orders capped at 30/minute.

    We use a schema-valid (but business-invalid) payload so requests get past
    FastAPI's Pydantic body validation and actually reach the limiter.
    Business-layer 404/400 is fine — we only care that the 31st+ request
    is short-circuited to 429.
    """
    payload = {
        "service_type": "full_accompany",
        "hospital_id": "00000000-0000-0000-0000-000000000000",
        "appointment_date": "2099-01-01",
        "appointment_time": "09:30",
    }
    statuses = []
    for _ in range(35):
        resp = await authenticated_client.post("/api/v1/orders", json=payload)
        statuses.append(resp.status_code)
    assert 429 in statuses, f"expected a 429 in {statuses!r}"


@pytest.mark.asyncio
async def test_orders_pay_is_rate_limited(_enable_limiter, authenticated_client):
    fake_id = "00000000-0000-0000-0000-000000000000"
    statuses = []
    for _ in range(35):
        resp = await authenticated_client.post(f"/api/v1/orders/{fake_id}/pay")
        statuses.append(resp.status_code)
    assert 429 in statuses


@pytest.mark.asyncio
async def test_orders_refund_is_rate_limited(_enable_limiter, authenticated_client):
    fake_id = "00000000-0000-0000-0000-000000000000"
    statuses = []
    for _ in range(35):
        resp = await authenticated_client.post(f"/api/v1/orders/{fake_id}/refund")
        statuses.append(resp.status_code)
    assert 429 in statuses


@pytest.mark.asyncio
async def test_orders_cancel_is_rate_limited(_enable_limiter, authenticated_client):
    fake_id = "00000000-0000-0000-0000-000000000000"
    statuses = []
    for _ in range(35):
        resp = await authenticated_client.post(f"/api/v1/orders/{fake_id}/cancel")
        statuses.append(resp.status_code)
    assert 429 in statuses


@pytest.mark.asyncio
async def test_orders_accept_is_rate_limited(_enable_limiter, companion_client):
    fake_id = "00000000-0000-0000-0000-000000000000"
    statuses = []
    for _ in range(35):
        resp = await companion_client.post(f"/api/v1/orders/{fake_id}/accept")
        statuses.append(resp.status_code)
    assert 429 in statuses


@pytest.mark.asyncio
async def test_auth_refresh_is_rate_limited(_enable_limiter, client):
    statuses = []
    for _ in range(15):
        resp = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": "garbage"}
        )
        statuses.append(resp.status_code)
    assert 429 in statuses, f"expected a 429 in {statuses!r}"


@pytest.mark.asyncio
async def test_auth_verify_otp_is_rate_limited(_enable_limiter, client):
    statuses = []
    for _ in range(15):
        resp = await client.post(
            "/api/v1/auth/verify-otp",
            json={"phone": "13800138999", "code": "000000"},
        )
        statuses.append(resp.status_code)
    assert 429 in statuses
