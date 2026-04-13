from unittest.mock import AsyncMock, patch

import pytest

from tests.conftest import test_session_factory


@pytest.mark.asyncio
async def test_health_check(client):
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


@pytest.mark.asyncio
async def test_readiness_all_healthy(client):
    """Both DB and Redis healthy → 200 + status=ready."""
    with patch("app.api.v1.health.async_session", test_session_factory):
        response = await client.get("/api/v1/readiness")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["db"] == "ok"
    assert data["redis"] == "ok"


@pytest.mark.asyncio
async def test_readiness_db_failure(client):
    """DB check fails → 503 + db=error."""
    mock_factory = AsyncMock()
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(side_effect=Exception("DB down"))
    mock_factory.return_value = mock_ctx

    with patch("app.api.v1.health.async_session", mock_factory):
        response = await client.get("/api/v1/readiness")
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "not_ready"
    assert data["db"] == "error"
    assert data["redis"] == "ok"


@pytest.mark.asyncio
async def test_readiness_redis_failure(client, fake_redis):
    """Redis check fails → 503 + redis=error."""
    original_set = fake_redis.set

    async def broken_set(*args, **kwargs):
        raise ConnectionError("Redis down")

    fake_redis.set = broken_set
    try:
        with patch("app.api.v1.health.async_session", test_session_factory):
            response = await client.get("/api/v1/readiness")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "not_ready"
        assert data["db"] == "ok"
        assert data["redis"] == "error"
    finally:
        fake_redis.set = original_set


@pytest.mark.asyncio
async def test_readiness_both_fail(client, fake_redis):
    """Both DB and Redis fail → 503 + both=error."""
    mock_factory = AsyncMock()
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(side_effect=Exception("DB down"))
    mock_factory.return_value = mock_ctx

    async def broken_set(*args, **kwargs):
        raise ConnectionError("Redis down")

    original_set = fake_redis.set
    fake_redis.set = broken_set
    try:
        with patch("app.api.v1.health.async_session", mock_factory):
            response = await client.get("/api/v1/readiness")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "not_ready"
        assert data["db"] == "error"
        assert data["redis"] == "error"
    finally:
        fake_redis.set = original_set
