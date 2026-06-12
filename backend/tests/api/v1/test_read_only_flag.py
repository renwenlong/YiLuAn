"""S2-DEV-016-READ-ONLY-FLAG-DB AC#7 — sentinel tests for the read-only flag.

Covers:

* AC#2: ``get_current_user`` propagates ``user.is_read_only`` (already
  loaded as part of the user row, no extra query).
* AC#3 / AC#7: ``WriteableUser`` dependency returns 403 with the canonical
  PRD-001 §F8 D2 shape:

      {
        "error_code": "USER_READONLY",
        "message": "Account is in read-only mode",
        "reason_category": "GRAY_REVOKE" | ... | null
      }

* AC#4: GET endpoints stay accessible to read-only users; only POST/PUT/
  PATCH/DELETE are blocked. We hit one of each shape (POST /users/me/...
  is the cheapest mutating endpoint with no extra fixtures required).

All tests rebuild the user row with ``is_read_only=TRUE`` before issuing
the request. We assert the 403 SHAPE (not just the status) so any
backend regression that drops ``reason_category`` or renames
``error_code`` will trip the sentinel.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.user import User

pytestmark = pytest.mark.asyncio


async def _flip_read_only(
    test_session_factory: async_sessionmaker,
    user_id,
    *,
    category: str | None = "GRAY_REVOKE",
) -> None:
    """Persist ``is_read_only=TRUE`` (+ category) on the given user row."""
    async with test_session_factory() as session:
        user = await session.get(User, user_id)
        assert user is not None
        user.is_read_only = True
        user.read_only_reason_category = category
        await session.commit()


async def test_mutating_endpoint_blocked_with_canonical_403_shape(
    authenticated_client: AsyncClient,
):
    """POST /users/me/feedback — mutating endpoint must 403 USER_READONLY."""
    from tests.conftest import test_session_factory as _factory

    user = authenticated_client._test_user  # type: ignore[attr-defined]
    await _flip_read_only(_factory, user.id, category="CREDENTIAL_LEAK")

    resp = await authenticated_client.post("/api/v1/notifications/read-all")
    assert resp.status_code == 403, resp.text
    body = resp.json()
    assert "detail" in body, body
    detail = body["detail"]
    # PRD-001 §F8 D2 canonical shape — sentinel asserts exact keys.
    assert isinstance(detail, dict), detail
    assert detail.get("error_code") == "USER_READONLY", detail
    assert "message" in detail, detail
    assert detail.get("reason_category") == "CREDENTIAL_LEAK", detail


async def test_get_endpoint_still_accessible_when_read_only(
    authenticated_client: AsyncClient,
):
    """GET endpoints unaffected — read-only ≠ no-read.

    Hits ``GET /users/me`` which only depends on CurrentUser.
    """
    from tests.conftest import test_session_factory as _factory

    user = authenticated_client._test_user  # type: ignore[attr-defined]
    await _flip_read_only(_factory, user.id)

    resp = await authenticated_client.get("/api/v1/users/me")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body.get("id") == str(user.id), body


async def test_writeable_user_passes_when_flag_false(
    authenticated_client: AsyncClient,
):
    """Sanity: when ``is_read_only=FALSE`` the same mutating endpoint
    works normally (proves the 403 is gated only on the flag, not on the
    dep itself)."""
    resp = await authenticated_client.post("/api/v1/notifications/read-all")
    # 200/204 acceptable — we only assert it's not the 403.
    assert resp.status_code < 400, resp.text


async def test_reason_category_null_when_admin_did_not_set_one(
    authenticated_client: AsyncClient,
):
    """If admin flipped the flag without supplying a category, 403 body
    must still include ``reason_category`` (null) so frontend can default
    to a generic copy instead of crashing on a missing key."""
    from tests.conftest import test_session_factory as _factory

    user = authenticated_client._test_user  # type: ignore[attr-defined]
    await _flip_read_only(_factory, user.id, category=None)

    resp = await authenticated_client.post("/api/v1/notifications/read-all")
    assert resp.status_code == 403, resp.text
    detail = resp.json()["detail"]
    assert detail.get("error_code") == "USER_READONLY"
    # Key must be present even when null — frontend mapper depends on it.
    assert "reason_category" in detail
    assert detail["reason_category"] is None


async def test_reason_detail_never_leaks_to_frontend(
    authenticated_client: AsyncClient,
):
    """PRD-001 §F8 D1 security guarantee: admin free-text ``reason_detail``
    (loaded from ``users.read_only_reason_detail`` column) MUST NEVER appear
    in any 403 response body to the user.

    Frontend only renders ``reason_category`` enum, never the detail prose
    (which could contain admin notes about grayscale strategy / credential
    leak source / report origin etc.).

    Sentinel: persist a distinctive marker into ``reason_detail`` and assert
    it never appears in the 403 body (any field, any nesting).
    """
    from tests.conftest import test_session_factory as _factory

    user = authenticated_client._test_user  # type: ignore[attr-defined]
    marker = "SECRET_ADMIN_NOTE_42_DO_NOT_LEAK"
    # Persist both category + detail.
    async with _factory() as session:
        u = await session.get(User, user.id)
        assert u is not None
        u.is_read_only = True
        u.read_only_reason_category = "COMPLIANCE_REPORT"
        u.read_only_reason_detail = marker
        await session.commit()

    resp = await authenticated_client.post("/api/v1/notifications/read-all")
    assert resp.status_code == 403, resp.text
    # Marker MUST NOT appear anywhere in body.
    assert marker not in resp.text, (
        f"SECURITY REGRESSION: reason_detail leaked into 403 body: {resp.text!r}"
    )
    # Sanity: category still present (positive control).
    detail = resp.json()["detail"]
    assert detail.get("reason_category") == "COMPLIANCE_REPORT"
