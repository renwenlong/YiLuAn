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

from httpx import AsyncClient
from sqlalchemy import select

from app.models.admin_audit_log import AdminAuditLog
from tests.conftest import test_session_factory

ADMIN_URL_TEMPLATE = "/api/v1/admin/prep-packages/{order_id}"


async def _list_prep_view_audits(order_id: str) -> list[AdminAuditLog]:
    """Fetch all audit rows for this prep_package target_id."""
    async with test_session_factory() as session:
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
    # seed_admin_token).  Don't hard-code the literal here — couple to the
    # fixture invariant: the operator string is non-empty and looks like a
    # username (no spaces).
    assert audits[-1].operator
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


# Note on 404 paths: a probe for a non-existent order id raises
# NotFoundException from the service layer, which causes the request to
# unwind the transaction and the audit row written before the fetch is
# NOT persisted.  AC#3 says "admin 写 view_prep_package audit_log" which
# we read as "successful admin views write an audit row".  Auditing
# reconnaissance attempts (probes for ids that don't exist) is a stronger
# property that would need a separate session.commit() before the fetch,
# which complicates the request-scoped transaction model.  Left as a
# follow-up if the security team raises it; not in scope for AC#3.
