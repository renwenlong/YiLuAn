"""S3-DEV-002-PREP-API AC#3: admin view writes AdminAuditLog.

ADR-0048 §7.0.2 + AC#3 lock-in.  When an admin reads
``GET /api/v1/admin/prep-packages/{order_id}`` we must write a row
into ``admin_audit_logs`` so the privileged view of sensitive medical
content is reconcilable in postmortems / regulator audits.

We test through the real ASGI client (not unit-mocked) so the wiring
in ``app/api/v1/admin/prep_packages.py`` is genuinely exercised:

  - successful read writes exactly one new audit row with the right shape
  - audit row carries the admin's ``username`` as ``operator``
  - audit row carries the requested ``order_id`` as ``target_id``
  - the action and target_type are the AC-mandated literals
  - multiple reads stack (one row per call) — supports forensic timeline
  - non-admin tokens are NOT audited as admins (negative control —
    the dependency stack should reject them with 401/403 before the
    handler runs, so no AdminAuditLog row appears)
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.database import get_db
from app.main import app
from app.models.admin_audit_log import AdminAuditLog
from app.services import prep_package_service as _prep_pkg_service
from tests.conftest import override_get_db
from tests.conftest import test_session_factory as _session_factory

pytest_plugins = ["tests.api.v1.prep_package_abac_fixtures"]

ADMIN_URL_TEMPLATE = "/api/v1/admin/prep-packages/{order_id}"


async def _list_prep_view_audits(order_id: str) -> list[AdminAuditLog]:
    """Fetch all audit rows for this prep_package target_id."""
    async with _session_factory() as session:
        result = await session.execute(
            select(AdminAuditLog)
            .where(
                AdminAuditLog.target_type == "prep_package",
                AdminAuditLog.action == "view",
            )
            .order_by(AdminAuditLog.created_at.asc())
        )
        rows = list(result.scalars().all())
    return [r for r in rows if str(r.target_id) == order_id]


async def test_admin_view_writes_audit_log_row(
    client: AsyncClient, prep_abac_context: Mapping[str, Any]
) -> None:
    """Happy path: admin GET → exactly 1 new AdminAuditLog row appears."""
    order_id = str(prep_abac_context["order"].id)
    before = await _list_prep_view_audits(order_id)

    response = await client.get(
        ADMIN_URL_TEMPLATE.format(order_id=order_id),
        headers={"Authorization": f"Bearer {prep_abac_context['admin_token']}"},
    )
    assert response.status_code == 200, response.text

    after = await _list_prep_view_audits(order_id)
    assert len(after) == len(before) + 1, (
        f"expected exactly one new audit row, got {len(after) - len(before)}"
    )

    new_row = after[-1]
    assert new_row.target_type == "prep_package"
    assert new_row.action == "view"
    assert str(new_row.target_id) == order_id


async def test_admin_view_audit_records_admin_username(
    client: AsyncClient, prep_abac_context: Mapping[str, Any]
) -> None:
    """The operator field carries the admin's username, not a stub literal.

    Important for postmortem questions like "who saw record X at time T".
    """
    order_id = str(prep_abac_context["order"].id)
    response = await client.get(
        ADMIN_URL_TEMPLATE.format(order_id=order_id),
        headers={"Authorization": f"Bearer {prep_abac_context['admin_token']}"},
    )
    assert response.status_code == 200

    audits = await _list_prep_view_audits(order_id)
    assert audits, "no audit row written"
    # The fixture seeds admin with username='prep_ops' (default in
    # seed_admin_token).  Don't hard-code the full literal here — couple to
    # the fixture invariant: the operator string starts with the fixture's
    # ``prep_`` prefix (so a fixture rename to 'prep_admin' / 'prep_qa' still
    # passes, but a regression to a stub literal like 'system' / 'admin' /
    # '<unknown>' fails loudly).
    assert audits[-1].operator
    assert audits[-1].operator.startswith("prep_"), (
        f"operator should start with fixture-seeded 'prep_' prefix, "
        f"got {audits[-1].operator!r} — stub literal regression?"
    )
    assert " " not in audits[-1].operator


async def test_admin_view_audit_stacks_per_call(
    client: AsyncClient, prep_abac_context: Mapping[str, Any]
) -> None:
    """Repeated reads each produce a row — required for forensic timeline."""
    order_id = str(prep_abac_context["order"].id)
    before = await _list_prep_view_audits(order_id)

    for _ in range(3):
        response = await client.get(
            ADMIN_URL_TEMPLATE.format(order_id=order_id),
            headers={"Authorization": f"Bearer {prep_abac_context['admin_token']}"},
        )
        assert response.status_code == 200

    after = await _list_prep_view_audits(order_id)
    assert len(after) == len(before) + 3


async def test_patient_token_does_not_create_admin_audit(
    client: AsyncClient, prep_abac_context: Mapping[str, Any]
) -> None:
    """Negative control: a patient JWT hitting the admin URL must NOT
    create an AdminAuditLog row (the dependency stack rejects before the
    handler runs).

    This guards against an accidental flip where the audit insert happens
    in a request-middleware that runs before ABAC dependency resolution.
    The PR #235 fix means admin-side endpoints return 403 for cross-role
    tokens at dependency-eval time; the audit insert lives in the handler
    body, which never executes on a 403.
    """
    order_id = str(prep_abac_context["order"].id)
    before = await _list_prep_view_audits(order_id)

    response = await client.get(
        ADMIN_URL_TEMPLATE.format(order_id=order_id),
        headers={"Authorization": f"Bearer {prep_abac_context['patient_token']}"},
    )
    # admin endpoint vs patient token: dependency rejects.  Whether the
    # rejection is 401 (legacy) or 403 (post-PR-235 strict role) we tolerate
    # — the invariant under test is "no audit row written".
    assert response.status_code in (401, 403), response.text

    after = await _list_prep_view_audits(order_id)
    assert len(after) == len(before), (
        "patient token on admin URL produced an admin-side audit row — "
        "that would mean the audit insert runs before dependency resolution"
    )


async def test_companion_token_does_not_create_admin_audit(
    client: AsyncClient, prep_abac_context: Mapping[str, Any]
) -> None:
    """Same as the patient case, for the companion role."""
    order_id = str(prep_abac_context["order"].id)
    before = await _list_prep_view_audits(order_id)

    response = await client.get(
        ADMIN_URL_TEMPLATE.format(order_id=order_id),
        headers={"Authorization": f"Bearer {prep_abac_context['companion_token']}"},
    )
    assert response.status_code in (401, 403)

    after = await _list_prep_view_audits(order_id)
    assert len(after) == len(before)


# ---------------------------------------------------------------------------
# S3-OPS-VIEW-PREP-AUDIT-ISOLATED-SESSION: 404 / 500 audit persistence
# ---------------------------------------------------------------------------
# These tests close the original AC#3 "known limitation" — they verify the
# audit row is durable even when the service layer raises (404 probe for
# non-existent order_id, 500 from an unexpected exception). The endpoint
# uses an isolated AuditSession dependency that commits before the fetch,
# following the pattern from PR #250 (cache_invalidate.py / S3-DEV-005).
#
# Why this matters: capturing reconnaissance (admin probes for ids that
# do not exist) is a stronger forensic property than logging only
# successful reads. Required by ABAC + compliance review.


async def test_view_prep_package_audit_persists_on_404(
    client: AsyncClient, prep_abac_context: Mapping[str, Any]
) -> None:
    """404 probe for non-existent order_id MUST still write an audit row.

    Closes original AC#3 "known limitation" — captures admin
    reconnaissance attempts. Implementation: isolated AuditSession
    (S3-OPS-VIEW-PREP-AUDIT-ISOLATED-SESSION + PR #250 pattern).
    """
    bogus_order_id = uuid4()
    bogus_str = str(bogus_order_id)
    before = await _list_prep_view_audits(bogus_str)

    response = await client.get(
        ADMIN_URL_TEMPLATE.format(order_id=bogus_str),
        headers={"Authorization": f"Bearer {prep_abac_context['admin_token']}"},
    )
    # Service layer raises NotFoundException → 404
    assert response.status_code == 404, response.text

    after = await _list_prep_view_audits(bogus_str)
    assert len(after) == len(before) + 1, (
        f"404 probe MUST persist audit row (forensic invariant): "
        f"got {len(after) - len(before)} new rows, expected exactly 1. "
        f"Regression: AuditSession not isolated from request-scoped DBSession."
    )

    new_row = after[-1]
    assert new_row.target_type == "prep_package"
    assert new_row.action == "view"
    assert str(new_row.target_id) == bogus_str
    # operator must still resolve to the admin's username (probe identity)
    assert new_row.operator
    assert new_row.operator.startswith("prep_"), (
        f"operator should carry admin identity even on probe; "
        f"got {new_row.operator!r}"
    )


async def test_view_prep_package_audit_persists_on_500(
    fake_redis: object,
    prep_abac_context: Mapping[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """500 from service layer MUST still write an audit row.

    Same forensic invariant as the 404 test: even unexpected
    exceptions must not erase the audit trail of an admin's view
    attempt. We monkeypatch ``get_prep_for_admin`` to raise an
    unexpected RuntimeError, simulating a DB outage or service bug.

    Uses a dedicated client with ``raise_app_exceptions=False`` so
    the unhandled RuntimeError becomes an HTTP 500 response (the
    default ``client`` fixture re-raises into the test).
    """
    order_id = str(prep_abac_context["order"].id)
    before = await _list_prep_view_audits(order_id)

    async def _raise(self: object, _order_id: object) -> None:
        raise RuntimeError("simulated 500 from prep_package_service")

    monkeypatch.setattr(
        _prep_pkg_service.PrepPackageService,
        "get_prep_for_admin",
        _raise,
    )

    # Dedicated client with raise_app_exceptions=False so RuntimeError
    # becomes a real HTTP 500 instead of bubbling into the test body.
    app.dependency_overrides[get_db] = override_get_db
    app.state.redis = fake_redis
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as raw_client:
        response = await raw_client.get(
            ADMIN_URL_TEMPLATE.format(order_id=order_id),
            headers={
                "Authorization": f"Bearer {prep_abac_context['admin_token']}"
            },
        )

    # FastAPI default exception handler → 500
    assert response.status_code == 500, response.text

    after = await _list_prep_view_audits(order_id)
    assert len(after) == len(before) + 1, (
        f"500 crash MUST persist audit row (forensic invariant): "
        f"got {len(after) - len(before)} new rows, expected exactly 1. "
        f"Regression: AuditSession not isolated from request-scoped DBSession."
    )

    new_row = after[-1]
    assert new_row.target_type == "prep_package"
    assert new_row.action == "view"
    assert str(new_row.target_id) == order_id
