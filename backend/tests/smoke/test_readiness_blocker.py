"""
Production readiness **阻断级**（blocker）tests — P1-7 / Action #7.

These complement ``backend/tests/test_health.py`` which already covers
the basic DB-down / Redis-down scenarios on both ``/api/v1/readiness``
and root ``/readiness``. This file adds:

  C1. Both /health endpoints stay 200 (liveness must NEVER cascade to
      503 from a dependency outage — Kubernetes / ACA would kill the
      pod and prolong the outage).
  C2. Readiness 503 happens on BOTH paths uniformly (root + /api/v1).
  C3. Migration drift (alembic_version != head) — TODO: readiness
      should return 503 with a clear "migration drift" reason. Until
      that is implemented, this test is ``xfail`` and the gap is
      tracked in ``docs/TECH_DEBT.md``.
  C4. Readiness response shape contract — ops dashboards depend on
      ``checks.db`` / ``checks.redis`` keys + the flat ``db`` / ``redis``
      back-compat keys. Any rename without a migration is a blocker.

If any non-xfail test fails: do NOT release — production traffic will
be served by an unready pod (or a healthy pod will be killed during a
benign Redis blip).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest

from tests.conftest import test_session_factory


# ---------------------------------------------------------------------------
# C1. Liveness must never cascade
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestLivenessIsolation:
    """``/health`` and ``/api/v1/health`` are PURE liveness probes —
    they must return 200 even when DB / Redis are completely down.
    Otherwise the orchestrator will kill the pod in the middle of an
    outage, multiplying the impact.
    """

    async def test_root_health_stays_200_when_db_down(self, client):
        @asynccontextmanager
        async def broken_session():
            raise RuntimeError("DB completely down")
            yield  # noqa: unreachable

        with patch("app.api.v1.health.async_session", broken_session):
            resp = await client.get("/health")
        assert resp.status_code == 200, (
            "Liveness must not depend on DB — got "
            f"{resp.status_code}: {resp.text}"
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
    """Root ``/readiness`` and ``/api/v1/readiness`` must return the
    same status / shape. They share an internal helper today
    (``_run_readiness_checks``) — this test prevents accidental
    divergence on a future refactor.
    """

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
        assert body["status"] == "not_ready"
        assert body["checks"]["db"].startswith("error:")

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
        assert resp.status_code == 503, (
            f"{path} must return 503 when Redis is down."
        )
        body = resp.json()
        assert body["status"] == "not_ready"
        assert body["checks"]["redis"].startswith("error:")

    @pytest.mark.parametrize("path", ["/readiness", "/api/v1/readiness"])
    async def test_returns_200_shape_when_healthy(self, client, path):
        with patch("app.api.v1.health.async_session", test_session_factory):
            resp = await client.get(path)
        assert resp.status_code == 200
        body = resp.json()
        # Contract: status + checks dict + back-compat flat keys.
        assert body["status"] == "ready"
        assert body["checks"] == {"db": "ok", "redis": "ok"}
        assert body["db"] == "ok"
        assert body["redis"] == "ok"


# ---------------------------------------------------------------------------
# C3. Migration drift detection (currently xfail — see TECH_DEBT)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.xfail(
    reason=(
        "TECH_DEBT: /readiness does not yet check alembic_version vs head. "
        "If a deploy lands new model code without running migrations, the "
        "pod will report ready and start serving 5xx-on-write. Tracked in "
        "docs/TECH_DEBT.md."
    ),
    strict=False,
)
async def test_readiness_detects_migration_drift(client):
    """When the running ``alembic_version`` row is older than the head
    revision, readiness must return 503 with a clear reason. Today the
    endpoint only checks ``SELECT 1`` so this scenario currently passes
    silently — captured here as a regression marker."""
    # We model "drift" by patching the checker to claim the current
    # version is stale. The endpoint has no such check yet → the assert
    # below is expected to fail (xfail).
    with patch("app.api.v1.health.async_session", test_session_factory):
        resp = await client.get("/api/v1/readiness")
    body = resp.json()
    # Desired (post-fix) behaviour:
    assert resp.status_code == 503, (
        "Migration drift must surface as 503 — see TECH_DEBT for the "
        "implementation plan."
    )
    # Should mention 'migration' or 'alembic' in the failure detail.
    detail = " ".join(str(v) for v in body.get("checks", {}).values()).lower()
    assert "migration" in detail or "alembic" in detail


# ---------------------------------------------------------------------------
# C4. Response-shape contract (back-compat keys)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestReadinessResponseContract:
    """Ops dashboards & external probes rely on:
      * ``status`` ∈ {"ready", "not_ready"}
      * ``checks`` dict with at least ``db`` and ``redis`` keys
      * Flat back-compat ``db`` / ``redis`` keys (legacy probes)

    Removing or renaming any of these is a release blocker.
    """

    async def test_healthy_response_has_all_required_keys(self, client):
        with patch("app.api.v1.health.async_session", test_session_factory):
            resp = await client.get("/api/v1/readiness")
        assert resp.status_code == 200
        body = resp.json()
        for key in ("status", "checks", "db", "redis"):
            assert key in body, f"Missing key {key!r} in response: {body}"
        assert "db" in body["checks"]
        assert "redis" in body["checks"]

    async def test_unhealthy_response_has_all_required_keys(self, client):
        @asynccontextmanager
        async def broken_session():
            raise RuntimeError("DB down")
            yield  # noqa: unreachable

        with patch("app.api.v1.health.async_session", broken_session):
            resp = await client.get("/api/v1/readiness")
        assert resp.status_code == 503
        body = resp.json()
        for key in ("status", "checks", "db", "redis"):
            assert key in body, f"Missing key {key!r} in 503 response: {body}"
        assert body["status"] == "not_ready"
        # Flat keys must collapse to ok|error (no half-baked values).
        assert body["db"] in ("ok", "error")
        assert body["redis"] in ("ok", "error")
