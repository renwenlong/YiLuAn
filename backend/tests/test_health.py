from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest

from tests.conftest import test_session_factory


@pytest.mark.asyncio
async def test_health_check(client):
    """Root /health is a pure liveness probe — no DB/Redis check."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data


@pytest.mark.asyncio
async def test_api_v1_ping(client):
    response = await client.get("/api/v1/ping")
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "pong"
    assert data["version"] == "v1"


@pytest.mark.asyncio
async def test_api_v1_health_liveness(client):
    """GET /api/v1/health returns 200 always (liveness probe)."""
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "timestamp" in data


# ---------- /api/v1/readiness ----------


@pytest.mark.asyncio
async def test_readiness_all_healthy(client):
    """Both DB and Redis healthy → 200 + status=ready + checks all ok."""
    with patch("app.api.v1.health.async_session", test_session_factory):
        response = await client.get("/api/v1/readiness")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["checks"] == {"db": "ok", "redis": "ok"}
    # 向后兼容扁平键
    assert data["db"] == "ok"
    assert data["redis"] == "ok"


@pytest.mark.asyncio
async def test_readiness_db_failure(client):
    """DB check fails → 503 + checks.db contains error message."""

    @asynccontextmanager
    async def broken_session():
        raise RuntimeError("DB down")
        yield  # noqa: unreachable

    with patch("app.api.v1.health.async_session", broken_session):
        response = await client.get("/api/v1/readiness")
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "not_ready"
    assert data["checks"]["db"].startswith("error:")
    assert "DB down" in data["checks"]["db"]
    assert data["checks"]["redis"] == "ok"


@pytest.mark.asyncio
async def test_readiness_redis_failure(client, fake_redis):
    """Redis check fails → 503 + checks.redis contains error message."""
    original_ping = fake_redis.ping

    async def broken_ping(*args, **kwargs):
        raise ConnectionError("Redis down")

    fake_redis.ping = broken_ping
    try:
        with patch("app.api.v1.health.async_session", test_session_factory):
            response = await client.get("/api/v1/readiness")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "not_ready"
        assert data["checks"]["db"] == "ok"
        assert data["checks"]["redis"].startswith("error:")
        assert "Redis down" in data["checks"]["redis"]
    finally:
        fake_redis.ping = original_ping


@pytest.mark.asyncio
async def test_readiness_both_fail(client, fake_redis):
    """Both fail → 503 + both checks contain error."""

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
        assert data["status"] == "not_ready"
        assert data["checks"]["db"].startswith("error:")
        assert data["checks"]["redis"].startswith("error:")
    finally:
        fake_redis.ping = original_ping


# ---------- Root-level /readiness (ACA/K8s default probe path) ----------


@pytest.mark.asyncio
async def test_readiness_root_all_healthy(client):
    """Root /readiness also returns 200 when healthy."""
    with patch("app.api.v1.health.async_session", test_session_factory):
        response = await client.get("/readiness")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["checks"] == {"db": "ok", "redis": "ok"}


@pytest.mark.asyncio
async def test_readiness_root_db_failure(client):
    """Root /readiness returns 503 on DB failure."""

    @asynccontextmanager
    async def broken_session():
        raise RuntimeError("DB down")
        yield  # noqa: unreachable

    with patch("app.api.v1.health.async_session", broken_session):
        response = await client.get("/readiness")
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "not_ready"
    assert "DB down" in data["checks"]["db"]
