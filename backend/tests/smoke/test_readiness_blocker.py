"""
Production readiness **阻断级**（blocker）tests — P1-7 / Action #7.

Updated 2026-04-24 to reflect TD-OPS-01 / TD-OPS-02 closure:
  * /readiness now returns a richer contract (`ready: bool`, `checks.<name>.{status, latency_ms, ...}`)
    串了 5 项依赖（db / redis / alembic / payment / sms）.
  * Alembic drift detection is no longer xfail — it's enforced.
  * Flat back-compat keys (`db`, `redis` at top-level) were retired in this
    breaking change because no production probe consumed them; ops dashboards
    moved to `checks.<name>.status`.

What we still guarantee here:
  C1. /health and /api/v1/health are pure liveness — never cascade to 503.
  C2. /readiness and /api/v1/readiness behave identically.
  C3. Migration drift returns 503 with a clear reason.
  C4. Response shape contract: `ready` + `status` + `checks.{db,redis,alembic,payment,sms}`.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest

from app.api.v1 import health as health_module
from tests.conftest import test_session_factory


# ---------------------------------------------------------------------------
# C1. Liveness must never cascade
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestLivenessIsolation:
    async def test_root_health_stays_200_when_db_down(self, client):
        @asynccontextmanager
        async def broken_session():
            raise RuntimeError("DB completely down")
            yield  # noqa: unreachable

        with patch("app.api.v1.health.async_session", broken_session):
            resp = await client.get("/health")
        assert resp.status_code == 200, (
            f"Liveness must not depend on DB — got {resp.status_code}: {resp.text}"
        )

    async def test_root_health_stays_200_when_redis_down(self, client, fake_redis):
        async def boom(*a, **kw):
            raise ConnectionError("Redis exploded")

        original = fake_redis.ping
        fake_redis.ping = boom
        try:
            resp = await client.get("/health")
        finally:
            fake_redis.ping = original
        assert resp.status_code == 200

    async def test_api_v1_health_stays_200_when_db_down(self, client):
        @asynccontextmanager
        async def broken_session():
            raise RuntimeError("DB down")
            yield  # noqa: unreachable

        with patch("app.api.v1.health.async_session", broken_session):
            resp = await client.get("/api/v1/health")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# C2. Both readiness paths behave identically
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestReadinessParity:

    @pytest.mark.parametrize("path", ["/readiness", "/api/v1/readiness"])
    async def test_returns_503_when_db_down(self, client, path):
        @asynccontextmanager
        async def broken_session():
            raise RuntimeError("DB down")
            yield  # noqa: unreachable

        with patch("app.api.v1.health.async_session", broken_session):
            resp = await client.get(path)
        assert resp.status_code == 503, (
            f"{path} must return 503 when DB is down — releasing without "
            "this guarantee means failed pods continue to receive traffic."
        )
        body = resp.json()
        assert body["ready"] is False
        assert body["checks"]["db"]["status"] == "error"
        assert "DB down" in body["checks"]["db"]["error"]

    @pytest.mark.parametrize("path", ["/readiness", "/api/v1/readiness"])
    async def test_returns_503_when_redis_down(self, client, fake_redis, path):
        async def boom(*a, **kw):
            raise ConnectionError("Redis down")

        original = fake_redis.ping
        fake_redis.ping = boom
        try:
            with patch("app.api.v1.health.async_session", test_session_factory):
                resp = await client.get(path)
        finally:
            fake_redis.ping = original
        assert resp.status_code == 503
        body = resp.json()
        assert body["ready"] is False
        assert body["checks"]["redis"]["status"] == "error"
        assert "Redis down" in body["checks"]["redis"]["error"]

    @pytest.mark.parametrize("path", ["/readiness", "/api/v1/readiness"])
    async def test_returns_200_shape_when_healthy(self, client, path):
        with patch("app.api.v1.health.async_session", test_session_factory):
            resp = await client.get(path)
        assert resp.status_code == 200
        body = resp.json()
        assert body["ready"] is True
        assert body["status"] == "ready"
        for k in ("db", "redis", "alembic", "payment", "sms"):
            assert k in body["checks"], f"missing check {k}"
            assert body["checks"][k]["status"] in ("ok", "skipped", "degraded")


# ---------------------------------------------------------------------------
# C3. Migration drift detection — TD-OPS-02 closed 2026-04-24, no longer xfail.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_readiness_detects_migration_drift(client, monkeypatch):
    async def drift():
        return {
            "status": "error",
            "current": "stale_rev",
            "head": "f4a5b6c7d8e9",
            "latency_ms": 1,
            "error": "version drift",
        }

    monkeypatch.setattr(health_module, "_check_alembic", drift)
    with patch("app.api.v1.health.async_session", test_session_factory):
        resp = await client.get("/api/v1/readiness")
    assert resp.status_code == 503, (
        "Migration drift must surface as 503 — TD-OPS-02 closure."
    )
    body = resp.json()
    assert body["checks"]["alembic"]["status"] == "error"
    assert body["checks"]["alembic"]["current"] != body["checks"]["alembic"]["head"]
    assert "drift" in body["checks"]["alembic"]["error"].lower()


# ---------------------------------------------------------------------------
# C4. Response-shape contract
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestReadinessResponseContract:

    async def test_healthy_response_has_all_required_keys(self, client):
        with patch("app.api.v1.health.async_session", test_session_factory):
            resp = await client.get("/api/v1/readiness")
        assert resp.status_code == 200
        body = resp.json()
        for key in ("ready", "status", "checks"):
            assert key in body, f"Missing key {key!r} in response: {body}"
        for k in ("db", "redis", "alembic", "payment", "sms"):
            assert k in body["checks"]
            assert "status" in body["checks"][k]

    async def test_unhealthy_response_has_all_required_keys(self, client):
        @asynccontextmanager
        async def broken_session():
            raise RuntimeError("DB down")
            yield  # noqa: unreachable

        with patch("app.api.v1.health.async_session", broken_session):
            resp = await client.get("/api/v1/readiness")
        assert resp.status_code == 503
        body = resp.json()
        for key in ("ready", "status", "checks"):
            assert key in body, f"Missing key {key!r} in 503 response: {body}"
        assert body["ready"] is False
        assert body["status"] == "not_ready"
        for k in ("db", "redis", "alembic", "payment", "sms"):
            assert k in body["checks"]
