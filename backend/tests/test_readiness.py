"""Readiness endpoint coverage — TD-OPS-01.

Covers all 5 dependency checks (db, redis, alembic, payment, sms) plus the
aggregator behaviour (any error → 503, skipped/degraded → still 200).
"""
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
from sqlalchemy import text

from app.api.v1 import health as health_module
from tests.conftest import test_session_factory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _ok_alembic():
    return {"status": "ok", "current": "f4a5b6c7d8e9", "head": "f4a5b6c7d8e9", "latency_ms": 1}


async def _drift_alembic():
    return {
        "status": "error",
        "current": "old_rev",
        "head": "f4a5b6c7d8e9",
        "latency_ms": 1,
        "error": "version drift",
    }


@pytest.fixture
def patch_alembic_ok(monkeypatch):
    monkeypatch.setattr(health_module, "_check_alembic", _ok_alembic)
    yield


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_readiness_all_healthy_mock_providers(client, patch_alembic_ok):
    """All 5 checks pass (payment + sms in mock mode) → 200, ready=true."""
    with patch("app.api.v1.health.async_session", test_session_factory):
        response = await client.get("/api/v1/readiness")
    assert response.status_code == 200
    data = response.json()
    assert data["ready"] is True
    assert data["status"] == "ready"
    checks = data["checks"]
    assert set(checks.keys()) == {"db", "redis", "alembic", "payment", "sms"}
    assert checks["db"]["status"] == "ok"
    assert "latency_ms" in checks["db"]
    assert checks["redis"]["status"] == "ok"
    assert checks["alembic"]["status"] == "ok"
    assert checks["alembic"]["current"] == checks["alembic"]["head"]
    assert checks["payment"]["status"] == "skipped"
    assert checks["payment"]["mode"] == "mock"
    assert checks["sms"]["status"] == "skipped"
    assert checks["sms"]["mode"] == "mock"


# ---------------------------------------------------------------------------
# DB failure → 503
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_readiness_db_failure(client, patch_alembic_ok):
    @asynccontextmanager
    async def broken_session():
        raise RuntimeError("DB down")
        yield  # noqa: unreachable

    with patch("app.api.v1.health.async_session", broken_session):
        response = await client.get("/api/v1/readiness")
    assert response.status_code == 503
    data = response.json()
    assert data["ready"] is False
    assert data["checks"]["db"]["status"] == "error"
    assert "DB down" in data["checks"]["db"]["error"]
    assert data["checks"]["redis"]["status"] == "ok"


# ---------------------------------------------------------------------------
# Redis failure → 503
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_readiness_redis_failure(client, fake_redis, patch_alembic_ok):
    original_ping = fake_redis.ping

    async def broken_ping(*args, **kwargs):
        raise ConnectionError("Redis down")

    fake_redis.ping = broken_ping
    try:
        with patch("app.api.v1.health.async_session", test_session_factory):
            response = await client.get("/api/v1/readiness")
        assert response.status_code == 503
        data = response.json()
        assert data["ready"] is False
        assert data["checks"]["redis"]["status"] == "error"
        assert "Redis down" in data["checks"]["redis"]["error"]
        assert data["checks"]["db"]["status"] == "ok"
    finally:
        fake_redis.ping = original_ping


# ---------------------------------------------------------------------------
# Alembic drift → 503
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_readiness_alembic_drift(client, monkeypatch):
    monkeypatch.setattr(health_module, "_check_alembic", _drift_alembic)
    with patch("app.api.v1.health.async_session", test_session_factory):
        response = await client.get("/api/v1/readiness")
    assert response.status_code == 503
    data = response.json()
    assert data["ready"] is False
    assert data["checks"]["alembic"]["status"] == "error"
    assert data["checks"]["alembic"]["current"] != data["checks"]["alembic"]["head"]
    assert "drift" in data["checks"]["alembic"]["error"]


# ---------------------------------------------------------------------------
# Alembic real check on test DB (no alembic_version table) → error
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_readiness_alembic_missing_version_row(client):
    """If alembic_version table is empty, readiness must return 503."""
    async with test_session_factory() as s:
        await s.execute(text("DELETE FROM alembic_version"))
        await s.commit()
    with patch("app.api.v1.health.async_session", test_session_factory):
        response = await client.get("/api/v1/readiness")
    assert response.status_code == 503
    data = response.json()
    assert data["checks"]["alembic"]["status"] == "error"
    assert "missing" in data["checks"]["alembic"]["error"].lower()


# ---------------------------------------------------------------------------
# Alembic OK when version row matches head
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_readiness_alembic_ok_when_version_matches(client):
    """Seed alembic_version with current script head → check passes."""
    head = health_module._alembic_script_head()
    assert head, "expected at least one alembic head in the bundled scripts"
    # conftest already seeded alembic_version with the current head; no setup needed.
    with patch("app.api.v1.health.async_session", test_session_factory):
        response = await client.get("/api/v1/readiness")
    assert response.status_code == 200
    data = response.json()
    assert data["checks"]["alembic"]["status"] == "ok"
    assert data["checks"]["alembic"]["current"] == head
    assert data["checks"]["alembic"]["head"] == head


# ---------------------------------------------------------------------------
# Payment / SMS providers
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_readiness_payment_real_mode_degraded_does_not_fail(
    client, monkeypatch, patch_alembic_ok
):
    """Real-mode payment ping failing → degraded (NOT error). Readiness still 200."""
    monkeypatch.setattr(health_module.settings, "payment_provider", "wechat")

    async def boom():
        # simulate the real path raising; replicate _check_payment fallback
        return {"status": "degraded", "mode": "wechat", "latency_ms": 1, "error": "boom"}

    monkeypatch.setattr(health_module, "_check_payment", boom)
    with patch("app.api.v1.health.async_session", test_session_factory):
        response = await client.get("/api/v1/readiness")
    assert response.status_code == 200
    data = response.json()
    assert data["ready"] is True
    assert data["checks"]["payment"]["status"] == "degraded"


@pytest.mark.asyncio
async def test_readiness_sms_real_mode_missing_config_fails(
    client, monkeypatch, patch_alembic_ok
):
    monkeypatch.setattr(health_module.settings, "sms_provider", "aliyun")
    monkeypatch.setattr(health_module.settings, "sms_access_key", "")
    monkeypatch.setattr(health_module.settings, "sms_access_secret", "")
    monkeypatch.setattr(health_module.settings, "sms_sign_name", "")
    monkeypatch.setattr(health_module.settings, "sms_template_code", "")
    with patch("app.api.v1.health.async_session", test_session_factory):
        response = await client.get("/api/v1/readiness")
    assert response.status_code == 503
    data = response.json()
    assert data["checks"]["sms"]["status"] == "error"
    assert "missing config" in data["checks"]["sms"]["error"]


@pytest.mark.asyncio
async def test_readiness_sms_real_mode_complete_config_ok(
    client, monkeypatch, patch_alembic_ok
):
    monkeypatch.setattr(health_module.settings, "sms_provider", "aliyun")
    monkeypatch.setattr(health_module.settings, "sms_access_key", "AK")
    monkeypatch.setattr(health_module.settings, "sms_access_secret", "SK")
    monkeypatch.setattr(health_module.settings, "sms_sign_name", "SIGN")
    monkeypatch.setattr(health_module.settings, "sms_template_code", "SMS_001")
    with patch("app.api.v1.health.async_session", test_session_factory):
        response = await client.get("/api/v1/readiness")
    assert response.status_code == 200
    data = response.json()
    assert data["checks"]["sms"]["status"] == "ok"
    assert data["checks"]["sms"]["mode"] == "aliyun"


# ---------------------------------------------------------------------------
# Both DB and Redis fail → 503 (compound error)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_readiness_db_and_redis_both_fail(client, fake_redis, patch_alembic_ok):
    @asynccontextmanager
    async def broken_session():
        raise RuntimeError("DB down")
        yield  # noqa: unreachable

    async def broken_ping(*args, **kwargs):
        raise ConnectionError("Redis down")

    original_ping = fake_redis.ping
    fake_redis.ping = broken_ping
    try:
        with patch("app.api.v1.health.async_session", broken_session):
            response = await client.get("/api/v1/readiness")
        assert response.status_code == 503
        data = response.json()
        assert data["checks"]["db"]["status"] == "error"
        assert data["checks"]["redis"]["status"] == "error"
    finally:
        fake_redis.ping = original_ping


# ---------------------------------------------------------------------------
# Root-level /readiness mirrors the api/v1 endpoint
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_readiness_root_endpoint_ok(client, patch_alembic_ok):
    with patch("app.api.v1.health.async_session", test_session_factory):
        response = await client.get("/readiness")
    assert response.status_code == 200
    data = response.json()
    assert data["ready"] is True
    assert "checks" in data


@pytest.mark.asyncio
async def test_readiness_root_endpoint_db_failure(client, patch_alembic_ok):
    @asynccontextmanager
    async def broken_session():
        raise RuntimeError("DB down")
        yield  # noqa: unreachable

    with patch("app.api.v1.health.async_session", broken_session):
        response = await client.get("/readiness")
    assert response.status_code == 503
    data = response.json()
    assert data["ready"] is False
    assert "DB down" in data["checks"]["db"]["error"]


# ---------------------------------------------------------------------------
# Latency budget — sanity check the whole endpoint stays well under 1.5s
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_readiness_latency_under_budget(client, patch_alembic_ok):
    import time as _time
    with patch("app.api.v1.health.async_session", test_session_factory):
        t0 = _time.perf_counter()
        response = await client.get("/api/v1/readiness")
        elapsed_ms = (_time.perf_counter() - t0) * 1000
    assert response.status_code == 200
    assert elapsed_ms < 1500, f"readiness took {elapsed_ms:.0f}ms (>1500ms budget)"
