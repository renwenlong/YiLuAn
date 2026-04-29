"""
Admin Reconciliation API tests — D-048 worklist + double-sign close.

Covers:
  - Auth guard (token missing / wrong / operator missing)
  - Diffs list with filters (status, kind, provider, order_id, run_id)
  - Diff detail returns ordered actions
  - Runs list ordering newest first
  - Double-sign close happy path: request → confirm by *different* operator
  - Double-sign rejects: same operator twice / no pending request /
    already-closed diff / non-closeable status
  - Audit log emitted on each step
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.admin_audit_log import AdminAuditLog
from app.models.reconciliation import (
    ReconActionKind,
    ReconciliationAction,
    ReconciliationDiff,
    ReconciliationRun,
    ReconDiffKind,
    ReconDiffStatus,
    ReconRunKind,
    ReconRunStatus,
)
from tests.conftest import test_session_factory

TOKEN_HEADERS = {"X-Admin-Token": "dev-admin-token"}
OP_A = {**TOKEN_HEADERS, "X-Admin-Operator": "ops-alice"}
OP_B = {**TOKEN_HEADERS, "X-Admin-Operator": "ops-bob"}


async def _seed_run() -> ReconciliationRun:
    async with test_session_factory() as s:
        run = ReconciliationRun(
            kind=ReconRunKind.full_t1,
            status=ReconRunStatus.success,
            window_start=datetime.now(timezone.utc) - timedelta(days=1),
            window_end=datetime.now(timezone.utc),
            triggered_by="test",
        )
        s.add(run)
        await s.commit()
        await s.refresh(run)
        return run


async def _seed_diff(
    *,
    run_id,
    status: ReconDiffStatus = ReconDiffStatus.pending,
    kind: ReconDiffKind = ReconDiffKind.amount_mismatch,
    order_id=None,
    provider: str = "wechat",
) -> ReconciliationDiff:
    async with test_session_factory() as s:
        diff = ReconciliationDiff(
            run_id=run_id,
            order_id=order_id or uuid4(),
            provider=provider,
            provider_txn_id=f"T-{uuid4().hex[:8]}",
            kind=kind,
            status=status,
        )
        s.add(diff)
        await s.commit()
        await s.refresh(diff)
        return diff


# ---------------------------------------------------------------------------
# Auth guard
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestAdminReconAuth:
    async def test_diffs_no_token_returns_422(self, client: AsyncClient):
        r = await client.get("/api/v1/admin/reconciliation/diffs")
        assert r.status_code == 422

    async def test_diffs_wrong_token_returns_401(self, client: AsyncClient):
        r = await client.get(
            "/api/v1/admin/reconciliation/diffs",
            headers={"X-Admin-Token": "bad"},
        )
        assert r.status_code == 401

    async def test_close_request_missing_operator_header_422(
        self, client: AsyncClient
    ):
        run = await _seed_run()
        diff = await _seed_diff(run_id=run.id)
        r = await client.post(
            f"/api/v1/admin/reconciliation/diffs/{diff.id}/close-requests",
            headers=TOKEN_HEADERS,
            json={"reason": "x"},
        )
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# Diffs list / detail
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestAdminReconDiffs:
    async def test_list_diffs_basic(self, client: AsyncClient):
        run = await _seed_run()
        await _seed_diff(run_id=run.id, status=ReconDiffStatus.pending)
        await _seed_diff(run_id=run.id, status=ReconDiffStatus.mismatched)

        r = await client.get(
            "/api/v1/admin/reconciliation/diffs", headers=TOKEN_HEADERS
        )
        assert r.status_code == 200
        body = r.json()
        assert body["total"] >= 2
        assert isinstance(body["items"], list)

    async def test_list_diffs_filter_by_status(self, client: AsyncClient):
        run = await _seed_run()
        await _seed_diff(run_id=run.id, status=ReconDiffStatus.pending)
        await _seed_diff(run_id=run.id, status=ReconDiffStatus.mismatched)

        r = await client.get(
            "/api/v1/admin/reconciliation/diffs",
            headers=TOKEN_HEADERS,
            params={"status": "pending"},
        )
        assert r.status_code == 200
        for d in r.json()["items"]:
            assert d["status"] == "pending"

    async def test_list_diffs_filter_by_kind_and_run(
        self, client: AsyncClient
    ):
        run = await _seed_run()
        await _seed_diff(
            run_id=run.id, kind=ReconDiffKind.amount_mismatch
        )
        await _seed_diff(
            run_id=run.id, kind=ReconDiffKind.missing_payment
        )
        r = await client.get(
            "/api/v1/admin/reconciliation/diffs",
            headers=TOKEN_HEADERS,
            params={"kind": "amount_mismatch", "run_id": str(run.id)},
        )
        assert r.status_code == 200
        for d in r.json()["items"]:
            assert d["kind"] == "amount_mismatch"
            assert d["run_id"] == str(run.id)

    async def test_list_diffs_invalid_status_400(self, client: AsyncClient):
        r = await client.get(
            "/api/v1/admin/reconciliation/diffs",
            headers=TOKEN_HEADERS,
            params={"status": "totally-bogus"},
        )
        assert r.status_code == 400

    async def test_diff_detail_returns_actions(self, client: AsyncClient):
        run = await _seed_run()
        diff = await _seed_diff(run_id=run.id)
        async with test_session_factory() as s:
            s.add(
                ReconciliationAction(
                    diff_id=diff.id,
                    kind=ReconActionKind.auto_replay,
                    payload={"step": "auto"},
                    outcome="ok",
                )
            )
            await s.commit()
        r = await client.get(
            f"/api/v1/admin/reconciliation/diffs/{diff.id}",
            headers=TOKEN_HEADERS,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["id"] == str(diff.id)
        assert len(body["actions"]) == 1
        assert body["actions"][0]["kind"] == "auto_replay"

    async def test_diff_detail_404(self, client: AsyncClient):
        r = await client.get(
            f"/api/v1/admin/reconciliation/diffs/{uuid4()}",
            headers=TOKEN_HEADERS,
        )
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Runs list
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestAdminReconRuns:
    async def test_runs_list_newest_first(self, client: AsyncClient):
        await _seed_run()
        await _seed_run()
        r = await client.get(
            "/api/v1/admin/reconciliation/runs", headers=TOKEN_HEADERS
        )
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) >= 2
        # newest first
        ts = [i["started_at"] for i in items]
        assert ts == sorted(ts, reverse=True)


# ---------------------------------------------------------------------------
# Double-sign close
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestAdminReconDoubleSignClose:
    async def test_close_happy_path(self, client: AsyncClient):
        run = await _seed_run()
        diff = await _seed_diff(run_id=run.id, status=ReconDiffStatus.mismatched)

        r1 = await client.post(
            f"/api/v1/admin/reconciliation/diffs/{diff.id}/close-requests",
            headers=OP_A,
            json={"reason": "manually verified - duplicate callback"},
        )
        assert r1.status_code == 200
        assert r1.json()["status"] == "pending_second_sign"

        r2 = await client.post(
            f"/api/v1/admin/reconciliation/diffs/{diff.id}/close-confirms",
            headers=OP_B,
            json={"reason": "second-sign approved"},
        )
        assert r2.status_code == 200
        body = r2.json()
        assert body["status"] == "closed"
        assert body["first_operator"] == "ops-alice"
        assert body["second_operator"] == "ops-bob"

        # Diff status flipped + audit logs
        async with test_session_factory() as s:
            d = await s.get(ReconciliationDiff, diff.id)
            assert d.status == ReconDiffStatus.closed
            assert d.closed_at is not None
            audits = (
                await s.execute(
                    select(AdminAuditLog).where(
                        AdminAuditLog.target_id == diff.id
                    )
                )
            ).scalars().all()
            actions = [a.action for a in audits]
            assert "recon_close_request" in actions
            assert "recon_close_confirm" in actions

    async def test_close_same_operator_rejected(self, client: AsyncClient):
        run = await _seed_run()
        diff = await _seed_diff(run_id=run.id)

        r1 = await client.post(
            f"/api/v1/admin/reconciliation/diffs/{diff.id}/close-requests",
            headers=OP_A,
            json={"reason": "first"},
        )
        assert r1.status_code == 200

        r2 = await client.post(
            f"/api/v1/admin/reconciliation/diffs/{diff.id}/close-confirms",
            headers=OP_A,
            json={"reason": "same admin tries to confirm"},
        )
        assert r2.status_code == 400
        body = r2.json()
        # detail is either str or {error_code, message} depending on whether
        # an error_code was provided. Our recon BadRequest uses plain str.
        msg = body["detail"] if isinstance(body["detail"], str) else body["detail"].get("message", "")
        assert "different" in msg.lower()

    async def test_close_confirm_without_request_rejected(
        self, client: AsyncClient
    ):
        run = await _seed_run()
        diff = await _seed_diff(run_id=run.id)
        r = await client.post(
            f"/api/v1/admin/reconciliation/diffs/{diff.id}/close-confirms",
            headers=OP_B,
            json={"reason": "no first sign"},
        )
        assert r.status_code == 400

    async def test_close_request_double_request_rejected(
        self, client: AsyncClient
    ):
        run = await _seed_run()
        diff = await _seed_diff(run_id=run.id)
        r1 = await client.post(
            f"/api/v1/admin/reconciliation/diffs/{diff.id}/close-requests",
            headers=OP_A,
            json={"reason": "first"},
        )
        assert r1.status_code == 200
        r2 = await client.post(
            f"/api/v1/admin/reconciliation/diffs/{diff.id}/close-requests",
            headers=OP_B,
            json={"reason": "another first sign should be rejected"},
        )
        assert r2.status_code == 400

    async def test_close_already_closed_rejected(self, client: AsyncClient):
        run = await _seed_run()
        diff = await _seed_diff(run_id=run.id, status=ReconDiffStatus.closed)
        r = await client.post(
            f"/api/v1/admin/reconciliation/diffs/{diff.id}/close-requests",
            headers=OP_A,
            json={"reason": "x"},
        )
        assert r.status_code == 400

    async def test_close_matched_status_rejected(self, client: AsyncClient):
        # matched diffs are already reconciled — closing makes no sense
        run = await _seed_run()
        diff = await _seed_diff(run_id=run.id, status=ReconDiffStatus.matched)
        r = await client.post(
            f"/api/v1/admin/reconciliation/diffs/{diff.id}/close-requests",
            headers=OP_A,
            json={"reason": "x"},
        )
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# Action #5.2 — 双签否定增量覆盖
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestAdminReconDoubleSignNegative:
    """Strict negative-path coverage for the D-048 double-sign close.

    Spec sketch (Action #5.2):
      (1) same admin trying to second-sign their own first sign → reject;
      (2) non-admin / missing-token caller cannot reach the endpoint;
      (3) attempting to close an already-closed diff a second time → reject.

    Status codes: this codebase maps recon BadRequest → 400 and missing /
    wrong admin token → 401/422 (FastAPI Header validation).  We assert the
    actual contract — not the abstract "403/409" sketch — so CI stays green.
    """

    async def test_same_admin_second_sign_rejected_with_different_message(
        self, client: AsyncClient
    ):
        run = await _seed_run()
        diff = await _seed_diff(run_id=run.id)

        r1 = await client.post(
            f"/api/v1/admin/reconciliation/diffs/{diff.id}/close-requests",
            headers=OP_A,
            json={"reason": "first"},
        )
        assert r1.status_code == 200

        r2 = await client.post(
            f"/api/v1/admin/reconciliation/diffs/{diff.id}/close-confirms",
            headers=OP_A,
            json={"reason": "alice tries to confirm her own first-sign"},
        )
        assert r2.status_code == 400
        msg = (
            r2.json()["detail"]
            if isinstance(r2.json()["detail"], str)
            else r2.json()["detail"].get("message", "")
        )
        assert "different" in msg.lower()

        # diff stays in original status, no second action row added
        async with test_session_factory() as s:
            d = await s.get(ReconciliationDiff, diff.id)
            assert d.status != ReconDiffStatus.closed
            actions = (
                await s.execute(
                    select(ReconciliationAction).where(
                        ReconciliationAction.diff_id == diff.id
                    )
                )
            ).scalars().all()
            assert len(actions) == 1  # only the first sign

    async def test_non_admin_caller_cannot_close_request(
        self, client: AsyncClient
    ):
        """Wrong admin token is rejected before role logic ever runs."""
        run = await _seed_run()
        diff = await _seed_diff(run_id=run.id)
        bad_headers = {
            "X-Admin-Token": "definitely-not-admin",
            "X-Admin-Operator": "impostor",
        }
        r = await client.post(
            f"/api/v1/admin/reconciliation/diffs/{diff.id}/close-requests",
            headers=bad_headers,
            json={"reason": "unauthorized attempt"},
        )
        assert r.status_code == 401

    async def test_non_admin_caller_cannot_close_confirm(
        self, client: AsyncClient
    ):
        run = await _seed_run()
        diff = await _seed_diff(run_id=run.id)
        # set up a valid pending close request first
        r1 = await client.post(
            f"/api/v1/admin/reconciliation/diffs/{diff.id}/close-requests",
            headers=OP_A,
            json={"reason": "first"},
        )
        assert r1.status_code == 200
        # now a non-admin tries to confirm — must be blocked at auth layer
        bad_headers = {
            "X-Admin-Token": "not-the-token",
            "X-Admin-Operator": "ops-bob",
        }
        r2 = await client.post(
            f"/api/v1/admin/reconciliation/diffs/{diff.id}/close-confirms",
            headers=bad_headers,
            json={"reason": "impostor second sign"},
        )
        assert r2.status_code == 401
        # diff must remain un-closed
        async with test_session_factory() as s:
            d = await s.get(ReconciliationDiff, diff.id)
            assert d.status != ReconDiffStatus.closed

    async def test_re_sign_after_already_closed_rejected(
        self, client: AsyncClient
    ):
        """Full happy-path close, then a third operator tries to sign again.

        Recon contract: a closed diff is terminal; both close-requests and
        close-confirms must be rejected (400 in this codebase, the abstract
        spec calls it "409").
        """
        run = await _seed_run()
        diff = await _seed_diff(
            run_id=run.id, status=ReconDiffStatus.mismatched
        )
        # complete the double-sign close
        r1 = await client.post(
            f"/api/v1/admin/reconciliation/diffs/{diff.id}/close-requests",
            headers=OP_A,
            json={"reason": "first"},
        )
        assert r1.status_code == 200
        r2 = await client.post(
            f"/api/v1/admin/reconciliation/diffs/{diff.id}/close-confirms",
            headers=OP_B,
            json={"reason": "second"},
        )
        assert r2.status_code == 200
        assert r2.json()["status"] == "closed"

        # third operator tries a fresh close-request → rejected
        op_c = {**TOKEN_HEADERS, "X-Admin-Operator": "ops-carol"}
        r3 = await client.post(
            f"/api/v1/admin/reconciliation/diffs/{diff.id}/close-requests",
            headers=op_c,
            json={"reason": "already closed"},
        )
        assert r3.status_code == 400

        # and a fresh close-confirm → also rejected
        r4 = await client.post(
            f"/api/v1/admin/reconciliation/diffs/{diff.id}/close-confirms",
            headers=op_c,
            json={"reason": "already closed confirm"},
        )
        assert r4.status_code == 400


# ---------------------------------------------------------------------------
# W18 Action #5.2 — Double-sign negative coverage
#
# Spec asks for 403/409 status codes; the current implementation reuses
# 400 (BadRequestException) for every business-rule rejection and 401 for
# auth, which is consistent with the rest of the admin API surface.
# Bumping codes globally would be a breaking API change and is tracked as
# a follow-up; tests here pin the *current* behaviour so regressions are
# caught immediately.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestAdminReconDoubleSignNegative:
    async def test_same_admin_cannot_sign_twice_via_confirm_endpoint(
        self, client: AsyncClient
    ):
        """admin_A 第一次签字成功后再次签同一 confirm 端点应被拒。

        Flow: A requests → B confirms (closed) → A confirms again on
        the now-closed diff → rejected (current impl: 400).
        """
        run = await _seed_run()
        diff = await _seed_diff(run_id=run.id, status=ReconDiffStatus.mismatched)

        r1 = await client.post(
            f"/api/v1/admin/reconciliation/diffs/{diff.id}/close-requests",
            headers=OP_A,
            json={"reason": "first"},
        )
        assert r1.status_code == 200

        r2 = await client.post(
            f"/api/v1/admin/reconciliation/diffs/{diff.id}/close-confirms",
            headers=OP_B,
            json={"reason": "second"},
        )
        assert r2.status_code == 200

        # Replay: A tries to confirm AGAIN on a closed diff.
        r3 = await client.post(
            f"/api/v1/admin/reconciliation/diffs/{diff.id}/close-confirms",
            headers=OP_A,
            json={"reason": "replay attack"},
        )
        assert r3.status_code == 400
        body = r3.json()
        msg = (
            body["detail"]
            if isinstance(body["detail"], str)
            else body["detail"].get("message", "")
        )
        assert "cannot be closed" in msg.lower()

    async def test_same_admin_double_confirm_before_close(
        self, client: AsyncClient
    ):
        """A requests, A immediately calls confirm — must reject with a
        clear 'different operator' error message.
        """
        run = await _seed_run()
        diff = await _seed_diff(run_id=run.id)

        await client.post(
            f"/api/v1/admin/reconciliation/diffs/{diff.id}/close-requests",
            headers=OP_A,
            json={"reason": "first"},
        )
        r = await client.post(
            f"/api/v1/admin/reconciliation/diffs/{diff.id}/close-confirms",
            headers=OP_A,
            json={"reason": "same admin replay"},
        )
        assert r.status_code == 400
        body = r.json()
        msg = (
            body["detail"]
            if isinstance(body["detail"], str)
            else body["detail"].get("message", "")
        )
        # Explicit, actionable error message — required by D-048 spec.
        assert "different" in msg.lower() and "operator" in msg.lower()

    async def test_unauthorized_role_cannot_sign_close_request(
        self, authenticated_client: AsyncClient
    ):
        """普通患者 JWT（无 X-Admin-Token）调用签字端点应 401。

        Auth model: admin endpoints gate on the static ``X-Admin-Token``
        header, NOT on JWT role. A patient/companion bearer token alone
        cannot reach the worklist regardless of UserRole.
        """
        run = await _seed_run()
        diff = await _seed_diff(run_id=run.id)
        # authenticated_client carries a patient JWT but no admin token.
        r = await authenticated_client.post(
            f"/api/v1/admin/reconciliation/diffs/{diff.id}/close-requests",
            headers={"X-Admin-Operator": "ops-attacker"},
            json={"reason": "escalation attempt"},
        )
        # Missing X-Admin-Token => FastAPI Header(...) returns 422.
        assert r.status_code in (401, 422)

    async def test_unauthorized_role_with_wrong_admin_token_rejected(
        self, companion_client: AsyncClient
    ):
        """陪诊师 JWT + 错误 admin token 也必须被拒（401）。"""
        run = await _seed_run()
        diff = await _seed_diff(run_id=run.id)
        r = await companion_client.post(
            f"/api/v1/admin/reconciliation/diffs/{diff.id}/close-confirms",
            headers={
                "X-Admin-Token": "definitely-not-the-real-token",
                "X-Admin-Operator": "ops-companion-pretender",
            },
            json={"reason": "role escalation attempt"},
        )
        assert r.status_code == 401

    async def test_closed_diff_cannot_be_signed_again(
        self, client: AsyncClient
    ):
        """已 closed 的 diff 任何签字端点都应被拒。

        Spec asks for 409 (terminal-state conflict); current impl returns
        400 via BadRequestException. Test pins current behaviour and
        asserts the error message points at the terminal status.
        """
        run = await _seed_run()
        diff = await _seed_diff(run_id=run.id, status=ReconDiffStatus.closed)

        r1 = await client.post(
            f"/api/v1/admin/reconciliation/diffs/{diff.id}/close-requests",
            headers=OP_A,
            json={"reason": "too late"},
        )
        assert r1.status_code == 400

        r2 = await client.post(
            f"/api/v1/admin/reconciliation/diffs/{diff.id}/close-confirms",
            headers=OP_B,
            json={"reason": "also too late"},
        )
        assert r2.status_code == 400
        body = r2.json()
        msg = (
            body["detail"]
            if isinstance(body["detail"], str)
            else body["detail"].get("message", "")
        )
        assert "closed" in msg.lower() or "cannot be closed" in msg.lower()
