"""S2-TEST-016-READ-ONLY-FLAG-E2E Phase A1 — admin endpoint full E2E flow.

Covers AC E#1-E#4 + E#6, dep on ``S2-OPS-A-READ-ONLY-FLAG-ADMIN-API`` (PR #300).

What this file adds beyond PR #300 unit tests
(``backend/tests/api/v1/admin/test_read_only_endpoints.py``):

- **E#1 set + mutating chain**: ``POST /admin/users/{id}/read-only`` → patient
  立即调真实 ``PATCH /users/me`` → 403 USER_READONLY (full pipeline).
- **E#2 unset + recovery chain**: set → unset → patient ``PATCH /users/me``
  恢复 200 (recovery assert PR #300 unit test 没做).
- **E#3 batch 100 边界**: 真实 100 user_ids + 100 audit row scan (PR #300 unit
  test 只测 3 user_ids).
- **E#4 batch 101 reject**: 字面边界 — 验 Pydantic 422 反 422 + 零 audit 副作用.
- **E#6 audit log 全字段 schema**: 3 actions × full schema grep
  (target_type / target_id / operator / created_at / reason).

References:
- ADR-0053 §7 (admin endpoint set + batch design)
- ADR-0053 §8 哨兵 #5 (E2E hard gate)
- PRD-001 §F8 D1 (reason_detail NEVER in response)
- PR #299 (Phase A0 — E#5 GET + E#8 token 瞬时 + E#9 lint)
- PR #300 (S2-OPS-A-READ-ONLY-FLAG-ADMIN-API — endpoint dep)
- 刻晴 plan v0 §11 Phase A1 detail
  (~/.openclaw/projects/yiluan-study-iter/tests/S2-TEST-016-plan.md)

NOTE: Uses ``X-Admin-Token`` (legacy header) via ``admin_headers`` fixture.
``require_admin`` dual-tracks JWT + X-Admin-Token so legacy header is
equivalent for endpoint behavior. PR #300 unit test uses admin JWT for
operator id verification; this E2E focuses on endpoint flow.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.admin_audit_log import AdminAuditLog

pytestmark = [pytest.mark.asyncio, pytest.mark.e2e]


# ---------------------------------------------------------------------------
# E#1 — set then mutating endpoint → 403 full chain
# ---------------------------------------------------------------------------


async def test_e1_admin_set_then_patient_mutating_403(
    e2e_client: AsyncClient,
    login_via_otp,
    patient_phone,
    admin_headers: dict,
):
    """E#1: admin POST set-read-only → patient PATCH /users/me 立即 403.

    Covers full E2E flow: admin set DB → patient JWT 已签发 → mutating
    endpoint 403 with USER_READONLY error_code (PRD-001 §F8 D1 字面冻结).
    """
    p_access, _, p_user = await login_via_otp(patient_phone, role="patient")
    p_headers = {"Authorization": f"Bearer {p_access}"}

    # Baseline: patient can write before flag is set.
    baseline = await e2e_client.put(
        "/api/v1/users/me",
        headers=p_headers,
        json={"display_name": "baseline-name"},
    )
    assert baseline.status_code == 200, f"baseline write must succeed: {baseline.text}"

    # Admin flips read-only via the endpoint (not a DB shortcut).
    set_resp = await e2e_client.post(
        f"/api/v1/admin/users/{p_user['id']}/read-only",
        headers=admin_headers,
        json={
            "is_read_only": True,
            "reason_category": "CREDENTIAL_LEAK",
            "reason_detail": "PHASE_A1_E1_LEAK_MARKER_DO_NOT_LEAK",
        },
    )
    assert set_resp.status_code == 200, f"admin set failed: {set_resp.text}"
    set_body = set_resp.json()

    # AC#6: reason_detail must not leak in admin response.
    assert "reason_detail" not in set_body
    assert "PHASE_A1_E1_LEAK_MARKER_DO_NOT_LEAK" not in str(set_body)

    # Patient's existing JWT must now 403 on mutating endpoint.
    mutating = await e2e_client.put(
        "/api/v1/users/me",
        headers=p_headers,
        json={"display_name": "should-fail-readonly"},
    )
    assert (
        mutating.status_code == 403
    ), f"expected 403 USER_READONLY, got {mutating.status_code}: {mutating.text}"

    # PRD-001 §F8 D1: error_code 字面 USER_READONLY.
    body = mutating.json()
    detail = body.get("detail", body)
    error_code = detail.get("error_code") if isinstance(detail, dict) else None
    assert error_code == "USER_READONLY", f"error_code must be USER_READONLY, got: {detail}"

    # Patient-facing response must also never carry reason_detail.
    assert "PHASE_A1_E1_LEAK_MARKER_DO_NOT_LEAK" not in mutating.text


# ---------------------------------------------------------------------------
# E#2 — unset then mutating endpoint recovers 200
# ---------------------------------------------------------------------------


async def test_e2_admin_unset_then_patient_mutating_recovers(
    e2e_client: AsyncClient,
    login_via_otp,
    patient_phone,
    admin_headers: dict,
):
    """E#2: admin set → unset → patient mutating 立即恢复 200.

    Verifies DELETE endpoint truly clears the flag at endpoint level (not
    just DB col — full request pipeline including ``WriteableUser``
    dependency re-evaluates per request).
    """
    p_access, _, p_user = await login_via_otp(patient_phone, role="patient")
    p_headers = {"Authorization": f"Bearer {p_access}"}

    # Set
    set_resp = await e2e_client.post(
        f"/api/v1/admin/users/{p_user['id']}/read-only",
        headers=admin_headers,
        json={"is_read_only": True, "reason_category": "GRAY_REVOKE"},
    )
    assert set_resp.status_code == 200

    # Confirm 403 in the middle.
    mid = await e2e_client.put(
        "/api/v1/users/me",
        headers=p_headers,
        json={"display_name": "blocked"},
    )
    assert mid.status_code == 403

    # Unset
    unset_resp = await e2e_client.delete(
        f"/api/v1/admin/users/{p_user['id']}/read-only",
        headers=admin_headers,
    )
    assert unset_resp.status_code == 200
    unset_body = unset_resp.json()
    assert unset_body["is_read_only"] is False
    assert unset_body["reason_category"] is None
    assert unset_body["read_only_set_at"] is None
    assert unset_body["read_only_set_by"] is None

    # Mutating endpoint recovers (flag is checked per request via
    # WriteableUser dep; no JWT claim cached).
    recovered = await e2e_client.put(
        "/api/v1/users/me",
        headers=p_headers,
        json={"display_name": "recovered"},
    )
    assert (
        recovered.status_code == 200
    ), f"expected recovery 200, got {recovered.status_code}: {recovered.text}"


# ---------------------------------------------------------------------------
# E#3 — batch 100 (boundary, max allowed)
# ---------------------------------------------------------------------------


async def test_e3_batch_100_all_set_with_audit(
    e2e_client: AsyncClient,
    login_via_otp,
    admin_headers: dict,
):
    """E#3: 真实 100 user_ids batch set → 100 succeeded + 100 audit rows.

    PR #300 unit test 只测 3 user_ids; 这里覆盖边界 100 (max ≤100 allowed).
    """
    from tests.conftest import test_session_factory as _factory

    # Seed 100 patient users via OTP login.
    user_ids = []
    for i in range(100):
        phone = f"139{i:08d}"
        _access, _, u = await login_via_otp(phone, role="patient")
        user_ids.append(u["id"])

    assert len(user_ids) == 100

    # Batch-set all 100 as read-only.
    resp = await e2e_client.post(
        "/api/v1/admin/users/batch-read-only",
        headers=admin_headers,
        json={
            "user_ids": user_ids,
            "is_read_only": True,
            "reason_category": "GRAY_ANOMALY",
            "reason_detail": "phase-a1-batch-100-marker",
        },
    )
    assert resp.status_code == 200, f"batch 100 failed: {resp.text}"
    body = resp.json()
    assert body["requested"] == 100
    assert body["succeeded"] == 100
    assert body["failed"] == 0
    assert len(body["results"]) == 100

    # AC#6: detail leak guard at batch level.
    assert "phase-a1-batch-100-marker" not in resp.text

    # Audit row count = 100 for action=set_read_only, target_id in user_ids.
    async with _factory() as s:
        rows = (
            (await s.execute(select(AdminAuditLog).where(AdminAuditLog.action == "set_read_only")))
            .scalars()
            .all()
        )

    batch_target_set = {str(uid) for uid in user_ids}
    batch_rows = [r for r in rows if str(r.target_id) in batch_target_set]
    assert len(batch_rows) == 100, f"expected 100 audit rows for this batch, got {len(batch_rows)}"
    for row in batch_rows:
        assert (
            "category=GRAY_ANOMALY" in row.reason
        ), f"audit row {row.id} missing category in reason: {row.reason}"


# ---------------------------------------------------------------------------
# E#4 — batch >100 (101 boundary, reject before any DB write)
# ---------------------------------------------------------------------------


async def test_e4_batch_101_rejected_no_changes(
    e2e_client: AsyncClient,
    admin_headers: dict,
):
    """E#4: 101 user_ids batch → 422 BATCH_TOO_LARGE, zero DB side-effects.

    PR #300 unit test covers the 422 itself; here we ALSO assert no audit
    row written (transactional reject before any DB touch).
    """
    from tests.conftest import test_session_factory as _factory

    async with _factory() as s:
        before_rows = (
            (await s.execute(select(AdminAuditLog).where(AdminAuditLog.action == "set_read_only")))
            .scalars()
            .all()
        )
    before = len(before_rows)

    fake_ids = [str(uuid4()) for _ in range(101)]
    resp = await e2e_client.post(
        "/api/v1/admin/users/batch-read-only",
        headers=admin_headers,
        json={
            "user_ids": fake_ids,
            "is_read_only": True,
            "reason_category": "GRAY_REVOKE",
        },
    )
    assert resp.status_code == 422, f"expected 422, got {resp.status_code}: {resp.text}"

    detail = resp.json()["detail"]
    assert detail["error_code"] == "BATCH_TOO_LARGE"
    assert "101" in detail["message"]
    assert "100" in detail["message"]

    async with _factory() as s:
        after_rows = (
            (await s.execute(select(AdminAuditLog).where(AdminAuditLog.action == "set_read_only")))
            .scalars()
            .all()
        )
    after = len(after_rows)

    assert after == before, f"batch 101 reject must not leave audit row: {before} -> {after}"


# ---------------------------------------------------------------------------
# E#6 — audit log full-field schema (set / unset / batch)
# ---------------------------------------------------------------------------


async def test_e6_audit_log_full_field_schema(
    e2e_client: AsyncClient,
    login_via_otp,
    patient_phone,
    admin_headers: dict,
):
    """E#6: 验 audit row 全字段 schema 完整性 (3 actions x full field grep).

    Schema fields required (AdminAuditLog model):
    - action in {set_read_only, unset_read_only}
    - target_type == "user"
    - target_id == user.id
    - operator (str, non-empty)
    - reason (str, contains 'category=' for set, may be empty for unset)
    - created_at (UTC datetime, non-null)
    """
    from uuid import UUID as _UUID

    from tests.conftest import test_session_factory as _factory

    p_access, _, p_user = await login_via_otp(patient_phone, role="patient")

    # Action 1: set
    r1 = await e2e_client.post(
        f"/api/v1/admin/users/{p_user['id']}/read-only",
        headers=admin_headers,
        json={
            "is_read_only": True,
            "reason_category": "COMPLIANCE_REPORT",
            "reason_detail": "phase-a1-e6-set",
        },
    )
    assert r1.status_code == 200

    # Action 2: unset
    r2 = await e2e_client.delete(
        f"/api/v1/admin/users/{p_user['id']}/read-only",
        headers=admin_headers,
    )
    assert r2.status_code == 200

    # Action 3: batch set (this single user)
    r3 = await e2e_client.post(
        "/api/v1/admin/users/batch-read-only",
        headers=admin_headers,
        json={
            "user_ids": [p_user["id"]],
            "is_read_only": True,
            "reason_category": "GRAY_ANOMALY",
            "reason_detail": "phase-a1-e6-batch",
        },
    )
    assert r3.status_code == 200

    # Scan audit rows for this target_id.
    # NB: target_id is a SQLAlchemy UUID column; pass uuid.UUID, not str.
    async with _factory() as s:
        rows = (
            (
                await s.execute(
                    select(AdminAuditLog)
                    .where(AdminAuditLog.target_id == _UUID(p_user["id"]))
                    .order_by(AdminAuditLog.created_at.asc())
                )
            )
            .scalars()
            .all()
        )

    actions = [r.action for r in rows]
    assert "set_read_only" in actions, f"missing set_read_only: actions={actions}"
    assert "unset_read_only" in actions, f"missing unset_read_only: actions={actions}"
    set_rows = [r for r in rows if r.action == "set_read_only"]
    assert len(set_rows) >= 2, f"expected >=2 set_read_only rows, got {len(set_rows)}"

    for row in rows:
        assert row.target_type == "user", f"target_type wrong: {row.target_type}"
        assert str(row.target_id) == str(p_user["id"])
        assert row.operator, f"operator must be non-empty: {row.operator!r}"
        assert row.created_at is not None, "created_at must not be null"
        if row.action == "set_read_only":
            assert (
                "category=" in row.reason
            ), f"set_read_only reason must contain 'category=': {row.reason!r}"
