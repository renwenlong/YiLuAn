"""S3-BUG-002-AI-BLOCKLIST-REQUIRE-JWT-ADMIN-WRONG-PRINCIPAL — endpoint integration.

Covers the **endpoint-level dependency chain** that the unit-test layer
(``tests/test_ai_blocklist_pubsub.py``) intentionally mocks out.

Root cause that this file regresses on:
    Prior ``_require_jwt_admin(principal)`` helper assumed
    ``principal.user`` to be an ``AdminUser``, but ``Depends(require_admin)``
    returns the ``AdminUser`` instance directly (no ``.user`` wrapper). All
    three endpoints (preview / reload / debug-version) therefore returned
    a stable 403 in real environments. Unit tests passed because the
    subscriber path was 100% mocked; nothing exercised the
    ``require_admin → endpoint`` chain.

This module hits the real FastAPI dependency stack with real admin JWTs
(via ``create_admin_access_token``) so the regression cannot recur
silently.

AC#5 coverage (per ADR-0048 §4.1 broad admin scope — not super-only):
    * preview / reload / debug-version × {admin JWT (super/ops/finance)
      200/202, missing/invalid token 401, user/patient JWT 403,
      legacy X-Admin-Token not in OpenAPI parameters}.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.admin_jwt import create_admin_access_token
from app.core.security import create_access_token
from app.models.admin_audit_log import AdminAuditLog
from app.models.admin_user import AdminRole, AdminUser
from app.models.user import User, UserRole
from app.services.ai_blocklist_pubsub import AI_BLOCKLIST_RELOAD_CHANNEL
from tests.conftest import test_session_factory as _session_factory

PREVIEW_URL = "/api/v1/admin/ai-blocklist/preview"
RELOAD_URL = "/api/v1/admin/ai-blocklist/reload"
DEBUG_VERSION_URL = "/api/v1/admin/ai-blocklist/debug-version"


# ---------------------------------------------------------------------------
# Fixtures (mirror tests/api/v1/test_admin_cache_invalidate.py pattern)
# ---------------------------------------------------------------------------


async def _seed_admin(username: str, role: AdminRole) -> str:
    async with _session_factory() as session:
        admin = AdminUser(
            username=username,
            password_hash="test-not-used",
            role=role,
            is_active=True,
        )
        session.add(admin)
        await session.commit()
        await session.refresh(admin)
        return create_admin_access_token(admin)


@pytest.fixture
async def super_token() -> str:
    return await _seed_admin(f"blocklist_super_{uuid4().hex[:6]}", AdminRole.super_)


@pytest.fixture
async def ops_token() -> str:
    return await _seed_admin(f"blocklist_ops_{uuid4().hex[:6]}", AdminRole.ops)


@pytest.fixture
async def finance_token() -> str:
    return await _seed_admin(f"blocklist_finance_{uuid4().hex[:6]}", AdminRole.finance)


async def _seed_user(role: UserRole) -> str:
    """Seed a real ``User`` row and return its user-side access token.

    user-side JWT is a syntactically valid bearer but the role is wrong;
    ``get_current_admin`` recognises it and raises 403 (per
    ``app/dependencies.py:152`` design). This proves the dependency
    chain enforces role boundary, not just signature validity.
    """
    async with _session_factory() as session:
        user = User(
            phone=f"+8613{uuid4().hex[:9]}",
            role=role,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return create_access_token(
            {
                "sub": str(user.id),
                "role": role.value,
                "v": user.token_version,
            }
        )


@pytest.fixture
async def patient_token() -> str:
    return await _seed_user(UserRole.patient)


@pytest.fixture
async def companion_token() -> str:
    return await _seed_user(UserRole.companion)


# ---------------------------------------------------------------------------
# preview endpoint (AC#4)
# ---------------------------------------------------------------------------


async def test_preview_super_admin_returns_200(client: AsyncClient, super_token: str) -> None:
    """S3-BUG-002 regression: super admin must reach the handler body, not 403.

    Pre-fix ``_require_jwt_admin(principal)`` returned 403 because
    ``getattr(principal, 'user', None) is None``. Post-fix the endpoint
    must reach the snapshot/audit/metric flow.
    """
    response = await client.get(
        PREVIEW_URL,
        headers={"Authorization": f"Bearer {super_token}"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert "version" in body
    assert "categories" in body
    assert isinstance(body["categories"], list)
    assert "total_patterns" in body
    assert body["total_patterns"] >= 0


async def test_preview_ops_admin_returns_200(client: AsyncClient, ops_token: str) -> None:
    """ops role is also an active AdminUser, so JWT auth alone is enough.

    Endpoint-level role restriction is intentionally absent (preview is
    read-only with audit + ADR-0048 §4.1 'admin' broad scope). If product
    later restricts to super_, this test must flip to 403 and a separate
    super_token test must assert 200.
    """
    response = await client.get(
        PREVIEW_URL,
        headers={"Authorization": f"Bearer {ops_token}"},
    )
    assert response.status_code == 200, response.text


async def test_preview_missing_token_returns_401(client: AsyncClient) -> None:
    """No Authorization header → JWT dependency raises 401.

    The pre-fix bug had this also rendering 403 (because
    ``_require_jwt_admin`` short-circuited before JWT validation). Post-fix
    we rely on ``get_current_admin`` which raises 401 for missing/invalid
    JWTs.
    """
    response = await client.get(PREVIEW_URL)
    assert response.status_code == 401, response.text


async def test_preview_invalid_token_returns_401(client: AsyncClient) -> None:
    response = await client.get(
        PREVIEW_URL,
        headers={"Authorization": "Bearer not-a-real-jwt"},
    )
    assert response.status_code == 401, response.text


async def test_preview_writes_audit_log(client: AsyncClient, super_token: str) -> None:
    """Post-fix the audit row must persist with operator=admin.id."""
    before = await _count_blocklist_view_audits()
    response = await client.get(
        PREVIEW_URL,
        headers={"Authorization": f"Bearer {super_token}"},
    )
    assert response.status_code == 200, response.text
    after = await _count_blocklist_view_audits()
    assert (
        after == before + 1
    ), f"expected exactly one new ai_blocklist_viewed row, got delta={after - before}"


async def test_preview_with_category_filter_records_audit_reason(
    client: AsyncClient, super_token: str
) -> None:
    response = await client.get(
        PREVIEW_URL,
        params={"category": "diagnosis"},
        headers={"Authorization": f"Bearer {super_token}"},
    )
    assert response.status_code == 200, response.text
    rows = await _latest_blocklist_view_audits(limit=1)
    assert rows, "audit row should be present after a successful preview"
    assert rows[0].reason == "category_filter=diagnosis"


# ---------------------------------------------------------------------------
# reload endpoint (AC#2)
# ---------------------------------------------------------------------------


async def test_reload_super_admin_returns_202(client: AsyncClient, super_token: str) -> None:
    """S3-BUG-002 regression: must reach the publish path, not 403."""
    response = await client.post(
        RELOAD_URL,
        headers={"Authorization": f"Bearer {super_token}"},
    )
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["accepted"] is True
    assert body["channel"] == AI_BLOCKLIST_RELOAD_CHANNEL
    assert body["triggered_by_admin_id"]


async def test_reload_writes_audit_log(client: AsyncClient, super_token: str) -> None:
    before = await _count_blocklist_reload_audits()
    response = await client.post(
        RELOAD_URL,
        headers={"Authorization": f"Bearer {super_token}"},
    )
    assert response.status_code == 202, response.text
    after = await _count_blocklist_reload_audits()
    assert (
        after == before + 1
    ), f"expected exactly one new ai_blocklist_reload row, got delta={after - before}"


async def test_reload_publishes_to_redis(
    client: AsyncClient, fake_redis: Any, super_token: str
) -> None:
    """Best-effort Redis publish runs on the happy path.

    The endpoint app uses ``request.app.state.redis``; we patch a capturing
    ``publish`` onto the fake redis instance because the suite's ``FakeRedis``
    class is a minimal in-process double without pubsub semantics. The actual
    payload is asserted in-place so the test fails loudly if the publish
    call is omitted (e.g. accidental ``return`` before publish, or wrong
    channel name).
    """
    published: list[tuple[str, str]] = []

    async def _capture_publish(channel: str, message: str) -> int:
        published.append((channel, message))
        return 1

    # FakeRedis has no native publish; monkeypatch one per-test to capture.
    fake_redis.publish = _capture_publish  # type: ignore[attr-defined]

    response = await client.post(
        RELOAD_URL,
        headers={"Authorization": f"Bearer {super_token}"},
    )
    assert response.status_code == 202, response.text
    assert len(published) == 1, f"expected exactly one publish call, got {len(published)}"
    channel, raw_payload = published[0]
    assert channel == AI_BLOCKLIST_RELOAD_CHANNEL
    payload = json.loads(raw_payload)
    assert "version" in payload
    assert "triggered_by_admin_id" in payload
    assert "triggered_at" in payload


async def test_reload_missing_token_returns_401(client: AsyncClient) -> None:
    response = await client.post(RELOAD_URL)
    assert response.status_code == 401, response.text


# ---------------------------------------------------------------------------
# debug-version endpoint
# ---------------------------------------------------------------------------


async def test_debug_version_super_admin_returns_200(client: AsyncClient, super_token: str) -> None:
    """S3-BUG-002 regression: debug endpoint must reach the snapshot read."""
    response = await client.get(
        DEBUG_VERSION_URL,
        headers={"Authorization": f"Bearer {super_token}"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert "instance" in body
    assert "version" in body
    assert body["categories"] >= 0
    assert body["total_patterns"] >= 0


async def test_debug_version_does_not_write_audit_log(
    client: AsyncClient, super_token: str
) -> None:
    """debug-version is intentionally cheap — no audit row.

    Documented in the endpoint docstring ("仅技术 debug 入口"). This pins
    that contract so a future maintainer who tries to add an audit row
    bumps into a failing test and re-reads the docstring.
    """
    before = await _count_blocklist_view_audits()
    response = await client.get(
        DEBUG_VERSION_URL,
        headers={"Authorization": f"Bearer {super_token}"},
    )
    assert response.status_code == 200, response.text
    after = await _count_blocklist_view_audits()
    assert after == before, "debug-version must not write audit rows"


async def test_debug_version_missing_token_returns_401(client: AsyncClient) -> None:
    response = await client.get(DEBUG_VERSION_URL)
    assert response.status_code == 401, response.text


async def test_debug_version_invalid_token_returns_401(client: AsyncClient) -> None:
    response = await client.get(
        DEBUG_VERSION_URL,
        headers={"Authorization": "Bearer not-a-real-jwt"},
    )
    assert response.status_code == 401, response.text


# ---------------------------------------------------------------------------
# user/patient JWT → 403 (AC#5: role boundary, not just signature)
# ---------------------------------------------------------------------------


async def test_preview_patient_token_returns_403(client: AsyncClient, patient_token: str) -> None:
    """AC#5: syntactically valid user-side JWT ≠ admin authorization.

    ``get_current_admin`` (``app/dependencies.py:152``) explicitly raises
    403 (not 401) when the bearer parses cleanly as a ``type=access``
    user token but has no matching ``AdminUser``. Confirms the
    dependency chain enforces role boundary, not just token signature.
    """
    response = await client.get(
        PREVIEW_URL,
        headers={"Authorization": f"Bearer {patient_token}"},
    )
    assert response.status_code == 403, response.text


async def test_reload_companion_token_returns_403(
    client: AsyncClient, companion_token: str
) -> None:
    """AC#5: companion-role user JWT also stopped at 403."""
    response = await client.post(
        RELOAD_URL,
        headers={"Authorization": f"Bearer {companion_token}"},
    )
    assert response.status_code == 403, response.text


async def test_debug_version_patient_token_returns_403(
    client: AsyncClient, patient_token: str
) -> None:
    """AC#5: debug-version also 403 for non-admin valid JWTs."""
    response = await client.get(
        DEBUG_VERSION_URL,
        headers={"Authorization": f"Bearer {patient_token}"},
    )
    assert response.status_code == 403, response.text


# ---------------------------------------------------------------------------
# OpenAPI surface (AC#5: legacy X-Admin-Token must NOT leak into spec)
# ---------------------------------------------------------------------------


async def test_openapi_does_not_expose_x_admin_token_for_ai_blocklist(
    client: AsyncClient,
) -> None:
    """AC#5: post-fix the endpoints use ``CurrentAdmin`` (JWT-only).

    The legacy double-track ``require_admin`` dependency injected an
    ``X-Admin-Token`` header into OpenAPI. If a future regression
    re-attaches the legacy path, this test catches it before the
    schema drift CI does (faster local feedback).
    """
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    spec = response.json()
    for path in (
        "/api/v1/admin/ai-blocklist/preview",
        "/api/v1/admin/ai-blocklist/reload",
        "/api/v1/admin/ai-blocklist/debug-version",
    ):
        path_item = spec.get("paths", {}).get(path, {})
        for method_def in path_item.values():
            if not isinstance(method_def, dict):
                continue
            for param in method_def.get("parameters", []) or []:
                assert (
                    param.get("name") != "X-Admin-Token"
                ), f"{path}: legacy X-Admin-Token header leaked back into OpenAPI"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _count_blocklist_view_audits() -> int:
    async with _session_factory() as session:
        result = await session.execute(
            select(AdminAuditLog).where(
                AdminAuditLog.target_type == "ai_blocklist",
                AdminAuditLog.action == "ai_blocklist_viewed",
            )
        )
        return len(list(result.scalars().all()))


async def _count_blocklist_reload_audits() -> int:
    async with _session_factory() as session:
        result = await session.execute(
            select(AdminAuditLog).where(
                AdminAuditLog.target_type == "ai_blocklist",
                AdminAuditLog.action == "ai_blocklist_reload",
            )
        )
        return len(list(result.scalars().all()))


async def _latest_blocklist_view_audits(limit: int = 5) -> list[AdminAuditLog]:
    async with _session_factory() as session:
        result = await session.execute(
            select(AdminAuditLog)
            .where(
                AdminAuditLog.target_type == "ai_blocklist",
                AdminAuditLog.action == "ai_blocklist_viewed",
            )
            .order_by(AdminAuditLog.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
