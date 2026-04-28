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
