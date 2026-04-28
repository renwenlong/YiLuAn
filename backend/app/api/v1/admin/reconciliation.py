"""
Admin Reconciliation — money reconciliation worklist & double-sign close.

Routes: /api/v1/admin/reconciliation
Auth:
  X-Admin-Token         — token-based admin auth (existing)
  X-Admin-Operator      — operator identity, required on close endpoints
                          so D-048 double-sign can enforce *different admin*.

Endpoints
---------
GET  /diffs                  list diffs, filters: status / kind / provider /
                             order_id / run_id / date_from / date_to / page
GET  /diffs/{id}             diff detail + ordered actions
POST /diffs/{id}/close-requests  body {reason} — first signature
POST /diffs/{id}/close-confirms  body {reason} — second signature (must be a
                             *different* operator; flips status to ``closed``)
GET  /runs                   list reconciliation runs

Reference: ADR-0032 (TD-MONEY-01) / D-048.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select

from app.core.admin_auth import require_admin_operator, require_admin_token
from app.dependencies import DBSession
from app.exceptions import BadRequestException, NotFoundException
from app.models.admin_audit_log import AdminAuditLog
from app.models.reconciliation import (
    ReconActionKind,
    ReconciliationAction,
    ReconciliationDiff,
    ReconciliationRun,
    ReconDiffKind,
    ReconDiffStatus,
)


router = APIRouter(
    prefix="/reconciliation",
    tags=["admin-reconciliation"],
    dependencies=[Depends(require_admin_token)],
)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class CloseRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


def _diff_to_dict(d: ReconciliationDiff) -> dict[str, Any]:
    return {
        "id": str(d.id),
        "run_id": str(d.run_id),
        "order_id": str(d.order_id) if d.order_id else None,
        "provider": d.provider,
        "provider_txn_id": d.provider_txn_id,
        "kind": d.kind.value if hasattr(d.kind, "value") else str(d.kind),
        "status": d.status.value if hasattr(d.status, "value") else str(d.status),
        "business_amount": str(d.business_amount) if d.business_amount is not None else None,
        "payment_amount": str(d.payment_amount) if d.payment_amount is not None else None,
        "ledger_amount": str(d.ledger_amount) if d.ledger_amount is not None else None,
        "business_status": d.business_status,
        "payment_status": d.payment_status,
        "ledger_status": d.ledger_status,
        "auto_retry_count": d.auto_retry_count,
        "last_error": d.last_error,
        "created_at": d.created_at.isoformat() if d.created_at else None,
        "updated_at": d.updated_at.isoformat() if d.updated_at else None,
        "closed_at": d.closed_at.isoformat() if d.closed_at else None,
    }


def _action_to_dict(a: ReconciliationAction) -> dict[str, Any]:
    return {
        "id": str(a.id),
        "diff_id": str(a.diff_id),
        "kind": a.kind.value if hasattr(a.kind, "value") else str(a.kind),
        "actor_id": str(a.actor_id) if a.actor_id else None,
        "payload": a.payload,
        "outcome": a.outcome,
        "error": a.error,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


# ---------------------------------------------------------------------------
# Diff list / detail
# ---------------------------------------------------------------------------
@router.get("/diffs")
async def list_diffs(
    session: DBSession,
    status: str | None = Query(default=None),
    kind: str | None = Query(default=None),
    provider: str | None = Query(default=None),
    order_id: UUID | None = Query(default=None),
    run_id: UUID | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    """List reconciliation diffs with filters; newest first."""
    stmt = select(ReconciliationDiff)
    if status:
        try:
            stmt = stmt.where(ReconciliationDiff.status == ReconDiffStatus(status))
        except ValueError as e:
            raise BadRequestException(f"invalid status: {status}") from e
    if kind:
        try:
            stmt = stmt.where(ReconciliationDiff.kind == ReconDiffKind(kind))
        except ValueError as e:
            raise BadRequestException(f"invalid kind: {kind}") from e
    if provider:
        stmt = stmt.where(ReconciliationDiff.provider == provider)
    if order_id is not None:
        stmt = stmt.where(ReconciliationDiff.order_id == order_id)
    if run_id is not None:
        stmt = stmt.where(ReconciliationDiff.run_id == run_id)
    if date_from is not None:
        stmt = stmt.where(ReconciliationDiff.created_at >= date_from)
    if date_to is not None:
        stmt = stmt.where(ReconciliationDiff.created_at <= date_to)

    # SQLAlchemy 2.0 doesn't have .count() on Select; use scalar subquery len
    rows = (await session.execute(stmt)).scalars().all()
    total = len(rows)
    rows.sort(key=lambda d: d.created_at or datetime.min, reverse=True)
    start = (page - 1) * page_size
    items = rows[start : start + page_size]

    return {
        "items": [_diff_to_dict(d) for d in items],
        "page": page,
        "page_size": page_size,
        "total": total,
    }


@router.get("/diffs/{diff_id}")
async def get_diff(
    diff_id: UUID,
    session: DBSession,
) -> dict[str, Any]:
    diff = await session.get(ReconciliationDiff, diff_id)
    if diff is None:
        raise NotFoundException(f"diff {diff_id} not found")
    actions_stmt = (
        select(ReconciliationAction)
        .where(ReconciliationAction.diff_id == diff_id)
        .order_by(ReconciliationAction.created_at.asc())
    )
    actions = (await session.execute(actions_stmt)).scalars().all()
    return {
        **_diff_to_dict(diff),
        "actions": [_action_to_dict(a) for a in actions],
    }


# ---------------------------------------------------------------------------
# Double-sign close (D-048)
# ---------------------------------------------------------------------------
_CLOSEABLE_STATUSES = {
    ReconDiffStatus.pending,
    ReconDiffStatus.mismatched,
    ReconDiffStatus.compensated,
}


async def _list_close_actions(
    session, diff_id: UUID
) -> list[ReconciliationAction]:
    stmt = (
        select(ReconciliationAction)
        .where(ReconciliationAction.diff_id == diff_id)
        .where(ReconciliationAction.kind == ReconActionKind.manual_close)
        .order_by(ReconciliationAction.created_at.asc())
    )
    return list((await session.execute(stmt)).scalars().all())


@router.post("/diffs/{diff_id}/close-requests")
async def request_close(
    diff_id: UUID,
    body: CloseRequest,
    session: DBSession,
    operator: str = Depends(require_admin_operator),
) -> dict[str, Any]:
    """First signature. Records a ``manual_close`` action with outcome
    ``pending_second_sign``. Diff stays in its current status.
    """
    diff = await session.get(ReconciliationDiff, diff_id)
    if diff is None:
        raise NotFoundException(f"diff {diff_id} not found")
    if diff.status not in _CLOSEABLE_STATUSES:
        raise BadRequestException(
            f"diff in status {diff.status} cannot be closed"
        )

    existing = await _list_close_actions(session, diff_id)
    pending = [a for a in existing if a.outcome == "pending_second_sign"]
    if pending:
        raise BadRequestException(
            "diff already has a pending close request; need a second signature"
        )

    action = ReconciliationAction(
        diff_id=diff_id,
        kind=ReconActionKind.manual_close,
        actor_id=None,
        payload={"operator": operator, "reason": body.reason, "step": "first"},
        outcome="pending_second_sign",
        error=None,
    )
    session.add(action)
    session.add(
        AdminAuditLog(
            target_type="reconciliation_diff",
            target_id=diff_id,
            action="recon_close_request",
            operator=operator,
            reason=body.reason,
        )
    )
    await session.commit()
    return {"status": "pending_second_sign", "action_id": str(action.id)}


@router.post("/diffs/{diff_id}/close-confirms")
async def confirm_close(
    diff_id: UUID,
    body: CloseRequest,
    session: DBSession,
    operator: str = Depends(require_admin_operator),
) -> dict[str, Any]:
    """Second signature. Must be performed by a *different* operator than
    the one who filed the pending request. Flips the diff to ``closed``.
    """
    diff = await session.get(ReconciliationDiff, diff_id)
    if diff is None:
        raise NotFoundException(f"diff {diff_id} not found")
    if diff.status not in _CLOSEABLE_STATUSES:
        raise BadRequestException(
            f"diff in status {diff.status} cannot be closed"
        )

    existing = await _list_close_actions(session, diff_id)
    pending = [a for a in existing if a.outcome == "pending_second_sign"]
    if not pending:
        raise BadRequestException(
            "no pending close request; call close-requests first"
        )
    first = pending[-1]
    first_operator = (first.payload or {}).get("operator")
    if first_operator == operator:
        raise BadRequestException(
            "second sign must be a different operator"
        )

    now = datetime.now(diff.created_at.tzinfo if diff.created_at else None)
    diff.status = ReconDiffStatus.closed
    diff.closed_at = now
    diff.updated_at = now

    second_action = ReconciliationAction(
        diff_id=diff_id,
        kind=ReconActionKind.manual_close,
        actor_id=None,
        payload={
            "operator": operator,
            "reason": body.reason,
            "step": "second",
            "first_operator": first_operator,
            "first_action_id": str(first.id),
        },
        outcome="closed",
        error=None,
    )
    session.add(second_action)
    session.add(
        AdminAuditLog(
            target_type="reconciliation_diff",
            target_id=diff_id,
            action="recon_close_confirm",
            operator=operator,
            reason=body.reason,
        )
    )
    await session.commit()
    return {
        "status": "closed",
        "action_id": str(second_action.id),
        "first_operator": first_operator,
        "second_operator": operator,
    }


# ---------------------------------------------------------------------------
# Runs (list)
# ---------------------------------------------------------------------------
@router.get("/runs")
async def list_runs(
    session: DBSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    stmt = select(ReconciliationRun).order_by(desc(ReconciliationRun.started_at))
    rows = (await session.execute(stmt)).scalars().all()
    total = len(rows)
    start = (page - 1) * page_size
    items = rows[start : start + page_size]

    def _row(r: ReconciliationRun) -> dict[str, Any]:
        return {
            "id": str(r.id),
            "kind": r.kind.value if hasattr(r.kind, "value") else str(r.kind),
            "status": r.status.value if hasattr(r.status, "value") else str(r.status),
            "window_start": r.window_start.isoformat() if r.window_start else None,
            "window_end": r.window_end.isoformat() if r.window_end else None,
            "orders_scanned": r.orders_scanned,
            "diffs_found": r.diffs_found,
            "diffs_auto_fixed": r.diffs_auto_fixed,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            "triggered_by": r.triggered_by,
            "notes": r.notes,
        }

    return {
        "items": [_row(r) for r in items],
        "page": page,
        "page_size": page_size,
        "total": total,
    }
