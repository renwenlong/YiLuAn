"""Tests for new admin surfaces: Dashboard (A), Audit Logs (C), Notes + Order Timeline (B)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from app.models.admin_audit_log import AdminAuditLog
from app.models.order_status_history import OrderStatusHistory
from tests.conftest import test_session_factory


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# A — Dashboard
# ---------------------------------------------------------------------------


async def test_dashboard_summary_returns_card_and_trend(admin_client):
    resp = await admin_client.get("/api/v1/admin/dashboard/summary")
    assert resp.status_code == 200
    body = resp.json()

    cards = body["cards"]
    for k in (
        "today_order_count",
        "today_gmv",
        "pending_companion_verifications",
        "open_reconciliation_diffs",
        "refund_pending_orders",
        "active_users_7d",
    ):
        assert k in cards, f"missing card key {k}"

    assert isinstance(body["trend_7d"], list)
    assert len(body["trend_7d"]) == 7, "trend must be exactly 7 days"
    for p in body["trend_7d"]:
        assert set(p.keys()) == {"date", "orders", "gmv"}


async def test_dashboard_requires_admin_auth(client):
    # Plain client (no admin headers) must be rejected.
    resp = await client.get("/api/v1/admin/dashboard/summary")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# C — Audit logs
# ---------------------------------------------------------------------------


async def _seed_audit_row(operator: str = "admin-token", **overrides) -> AdminAuditLog:
    async with test_session_factory() as session:
        row = AdminAuditLog(
            target_type=overrides.get("target_type", "order"),
            target_id=overrides.get("target_id", uuid.uuid4()),
            action=overrides.get("action", "force_status"),
            operator=operator,
            reason=overrides.get("reason", "test reason"),
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row


async def test_audit_logs_list_paginates_and_filters(admin_client):
    target_a = uuid.uuid4()
    await _seed_audit_row(target_type="order", target_id=target_a, action="force_status")
    await _seed_audit_row(target_type="order", target_id=target_a, action="refund")
    await _seed_audit_row(target_type="user", action="disable")

    resp = await admin_client.get("/api/v1/admin/audit-logs")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 3
    assert body["page"] == 1
    assert body["page_size"] == 50

    # Filter by target_type
    resp = await admin_client.get(
        "/api/v1/admin/audit-logs", params={"target_type": "user"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert all(it["target_type"] == "user" for it in body["items"])
    assert body["total"] >= 1

    # Filter by action
    resp = await admin_client.get(
        "/api/v1/admin/audit-logs", params={"action": "force_status"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert all(it["action"] == "force_status" for it in body["items"])

    # Filter by target_id
    resp = await admin_client.get(
        "/api/v1/admin/audit-logs", params={"target_id": str(target_a)}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 2
    assert all(it["target_id"] == str(target_a) for it in body["items"])


async def test_audit_logs_requires_admin(client):
    resp = await client.get("/api/v1/admin/audit-logs")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# B — Order timeline
# ---------------------------------------------------------------------------


async def test_order_timeline_returns_history_chronologically(admin_client):
    order_id = uuid.uuid4()
    changer = uuid.uuid4()
    async with test_session_factory() as session:
        session.add_all(
            [
                OrderStatusHistory(
                    order_id=order_id,
                    from_status=None,
                    to_status="created",
                    changed_by=changer,
                    note="initial",
                ),
                OrderStatusHistory(
                    order_id=order_id,
                    from_status="created",
                    to_status="accepted",
                    changed_by=changer,
                    note="companion picked up",
                ),
            ]
        )
        await session.commit()

    resp = await admin_client.get(f"/api/v1/admin/orders/{order_id}/timeline")
    assert resp.status_code == 200
    body = resp.json()
    assert body["order_id"] == str(order_id)
    assert len(body["entries"]) == 2
    # chronological ascending
    assert body["entries"][0]["to_status"] == "created"
    assert body["entries"][1]["to_status"] == "accepted"
    assert body["entries"][1]["from_status"] == "created"


async def test_order_timeline_empty_for_unknown_order(admin_client):
    resp = await admin_client.get(f"/api/v1/admin/orders/{uuid.uuid4()}/timeline")
    assert resp.status_code == 200
    assert resp.json()["entries"] == []


# ---------------------------------------------------------------------------
# B — Admin notes CRUD
# ---------------------------------------------------------------------------


async def test_note_create_list_edit_delete_flow(admin_client):
    target_id = uuid.uuid4()
    # create
    resp = await admin_client.post(
        "/api/v1/admin/notes",
        json={
            "target_type": "order",
            "target_id": str(target_id),
            "body": "customer claims payment failed; checked WeChat trace, all good",
        },
    )
    assert resp.status_code == 200, resp.text
    note = resp.json()
    assert note["body"].startswith("customer claims")
    assert note["target_id"] == str(target_id)

    # list
    resp = await admin_client.get(
        "/api/v1/admin/notes",
        params={"target_type": "order", "target_id": str(target_id)},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == note["id"]

    # edit
    resp = await admin_client.patch(
        f"/api/v1/admin/notes/{note['id']}",
        json={"body": "updated: confirmed refund via runbook 7.2"},
    )
    assert resp.status_code == 200
    assert resp.json()["body"].startswith("updated:")

    # delete
    resp = await admin_client.delete(f"/api/v1/admin/notes/{note['id']}")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True

    # list now empty
    resp = await admin_client.get(
        "/api/v1/admin/notes",
        params={"target_type": "order", "target_id": str(target_id)},
    )
    assert resp.json()["total"] == 0


async def test_note_rejects_disallowed_target_type(admin_client):
    resp = await admin_client.post(
        "/api/v1/admin/notes",
        json={
            "target_type": "hospital",  # not in allowlist
            "target_id": str(uuid.uuid4()),
            "body": "should reject",
        },
    )
    assert resp.status_code == 403


async def test_note_writes_audit_log_on_create(admin_client):
    target_id = uuid.uuid4()
    resp = await admin_client.post(
        "/api/v1/admin/notes",
        json={
            "target_type": "user",
            "target_id": str(target_id),
            "body": "VIP flag — handle with care",
        },
    )
    assert resp.status_code == 200

    # Audit row should now exist for this target
    resp = await admin_client.get(
        "/api/v1/admin/audit-logs",
        params={"target_id": str(target_id), "action": "add_note"},
    )
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1
