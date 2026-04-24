"""Liveness probes only — readiness coverage lives in test_readiness.py."""
import pytest


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
