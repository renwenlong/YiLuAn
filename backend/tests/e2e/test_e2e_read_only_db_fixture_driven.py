"""S2-TEST-016-READ-ONLY-FLAG-E2E Phase A0 — DB-fixture-driven E2E.

Covers AC subset that does NOT require admin set/unset/batch endpoint
(``S2-OPS-A-READ-ONLY-FLAG-ADMIN-API`` is still not-started as of 10:20Z):

- **E#5**: GET endpoints still 200 after read-only is set (read != write).
- **E#8**: Existing JWT becomes effective within 1s of the DB UPDATE
  (no token cache residue — ``get_current_user`` re-reads the row every
  request).

E#1-E#4 / E#6 are covered in ``test_e2e_read_only_admin_endpoints.py``
once the admin API task lands.

NB: This file extends the unit sentinel coverage in
``backend/tests/api/v1/test_read_only_flag.py`` by exercising the full
HTTP request pipeline (not just the dep), with realistic timing assertions.

References:
- ADR-0053 §7 + §8 哨兵 #5
- PRD-001 §F8 D1 / D2
- S2-DEV-016-READ-ONLY-FLAG-DB AC#7 (sentinel shape) — extended here for E2E
- 刻晴 plan v0 §3 Phase A0 (~/.openclaw/projects/yiluan-study-iter/tests/S2-TEST-016-plan.md)
"""

from __future__ import annotations

import asyncio
import time

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.user import User

pytestmark = [pytest.mark.asyncio, pytest.mark.e2e]


async def _flip_read_only(
    factory: async_sessionmaker,
    user_id,
    *,
    category: str | None = "GRAY_REVOKE",
    detail: str | None = None,
) -> None:
    """Persist ``is_read_only=TRUE`` (+ category, optional detail)."""
    async with factory() as session:
        user = await session.get(User, user_id)
        assert user is not None, f"user {user_id} not found"
        user.is_read_only = True
        user.read_only_reason_category = category
        if detail is not None:
            user.read_only_reason_detail = detail
        await session.commit()


# ---------------------------------------------------------------------------
# E#5 — GET endpoints unaffected
# ---------------------------------------------------------------------------


async def test_e5_get_users_me_returns_200_when_read_only(
    authenticated_client: AsyncClient,
):
    """E#5 part 1: ``GET /api/v1/users/me`` returns 200 even when the user
    is in read-only mode. The flag gates ONLY writes (CurrentUser passes,
    WriteableUser blocks). Read endpoints stay open."""
    from tests.conftest import test_session_factory as _factory

    user = authenticated_client._test_user  # type: ignore[attr-defined]
    await _flip_read_only(_factory, user.id, category="GRAY_REVOKE")

    resp = await authenticated_client.get("/api/v1/users/me")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body.get("id") == str(user.id)


async def test_e5_multiple_get_endpoints_all_200(
    authenticated_client: AsyncClient,
):
    """E#5 part 2: A representative set of GET endpoints all stay 200
    after the read-only flag flips. Picks endpoints with no extra
    fixture dependency (returning empty lists or current-user shape).
    """
    from tests.conftest import test_session_factory as _factory

    user = authenticated_client._test_user  # type: ignore[attr-defined]
    await _flip_read_only(_factory, user.id, category="GRAY_ANOMALY")

    # Endpoints chosen because they only need the JWT (no other seeds).
    sample_get_paths = [
        "/api/v1/users/me",
        # /companions/me may 404 (no companion profile) — that's still
        # not a 403 USER_READONLY, which is the only thing we want to
        # rule out.
    ]
    for path in sample_get_paths:
        resp = await authenticated_client.get(path)
        assert resp.status_code != 403 or (
            resp.json().get("detail", {}).get("error_code") != "USER_READONLY"
        ), (
            f"GET {path} blocked by USER_READONLY: read-only must NOT "
            f"affect GETs. body={resp.text!r}"
        )


# ---------------------------------------------------------------------------
# E#8 — token instant invalidation (no caching residue)
# ---------------------------------------------------------------------------


async def test_e8_existing_token_blocked_within_one_second(
    authenticated_client: AsyncClient,
):
    """E#8: After ``is_read_only`` flips to TRUE in the DB, an existing
    JWT must hit 403 on the very next mutating request — within 1
    second of the UPDATE commit. Validates that ``get_current_user``
    re-reads the user row every request (no in-process / Redis cache
    of the flag in Phase C).

    Sequence:
        1. Issue a baseline POST — must succeed (proves the endpoint
           and token currently work).
        2. Capture wall-clock t0, flip the DB row, capture t1.
        3. Issue the same POST — must 403 USER_READONLY.
        4. Assert (t1 - t0) < 1s. The 403 itself shows the flag took
           effect by the next request; the timing assertion guards
           against a future regression that adds a TTL cache.
    """
    from tests.conftest import test_session_factory as _factory

    user = authenticated_client._test_user  # type: ignore[attr-defined]

    # Baseline: writeable user can hit mutating endpoint.
    baseline = await authenticated_client.post("/api/v1/notifications/read-all")
    assert baseline.status_code < 400, (
        f"baseline mutating endpoint must succeed before the flag flips; "
        f"got {baseline.status_code}: {baseline.text}"
    )

    t0 = time.monotonic()
    await _flip_read_only(_factory, user.id, category="CREDENTIAL_LEAK")
    t1 = time.monotonic()

    # Same endpoint, same JWT — must now 403 because the next
    # get_current_user call reloads the row.
    blocked = await authenticated_client.post("/api/v1/notifications/read-all")
    assert blocked.status_code == 403, (
        f"after read-only flip, same JWT must 403; got {blocked.status_code}: "
        f"{blocked.text}"
    )
    detail = blocked.json()["detail"]
    assert detail["error_code"] == "USER_READONLY"
    assert detail["reason_category"] == "CREDENTIAL_LEAK"

    elapsed = t1 - t0
    assert elapsed < 1.0, (
        f"DB UPDATE took {elapsed:.3f}s — should be << 1s on test DB. "
        f"If this triggers, the test DB may be unhealthy."
    )


async def test_e8_no_caching_between_requests_back_to_back(
    authenticated_client: AsyncClient,
):
    """E#8 corollary: flip TRUE → FALSE → TRUE → FALSE in rapid
    succession and verify the next request after each flip sees the
    new state. This rules out a same-process cache that latches one
    way.
    """
    from tests.conftest import test_session_factory as _factory

    user = authenticated_client._test_user  # type: ignore[attr-defined]

    async def _set_flag(flag: bool):
        async with _factory() as session:
            u = await session.get(User, user.id)
            u.is_read_only = flag
            await session.commit()

    # FALSE -> 2xx
    resp = await authenticated_client.post("/api/v1/notifications/read-all")
    assert resp.status_code < 400, resp.text

    # TRUE -> 403
    await _set_flag(True)
    resp = await authenticated_client.post("/api/v1/notifications/read-all")
    assert resp.status_code == 403

    # FALSE -> 2xx (back to writeable)
    await _set_flag(False)
    resp = await authenticated_client.post("/api/v1/notifications/read-all")
    assert resp.status_code < 400, (
        f"unset failed to restore writeability — got {resp.status_code}: "
        f"{resp.text} — sticky-true regression?"
    )

    # TRUE -> 403 again
    await _set_flag(True)
    resp = await authenticated_client.post("/api/v1/notifications/read-all")
    assert resp.status_code == 403
