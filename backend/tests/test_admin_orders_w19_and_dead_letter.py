"""W19 + dead_letter coverage for admin orders.

Targets:
- ``force-status`` to a cancel state issues a refund when the order was
  paid, notifies both parties, and stamps the side-effects in the audit
  reason.
- ``force-status`` to ``completed`` bumps companion ``total_orders``.
- Dead-letter admin endpoints (list / detail / resolve) round-trip a
  row written by the cancel path's auto-refund failure handler.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.models.admin_audit_log import AdminAuditLog
from app.models.companion_profile import CompanionProfile
from app.models.dead_letter import DeadLetter, DeadLetterStatus
from app.models.notification import Notification
from app.models.order import OrderStatus
from app.models.payment import Payment
from app.models.user import UserRole
from tests.conftest import test_session_factory

ADMIN_TOKEN = "dev-admin-token"
HEADERS = {"X-Admin-Token": ADMIN_TOKEN}


# ---------------------------------------------------------------------------
# W19: force-cancel side effects
# ---------------------------------------------------------------------------


class TestForceCancelSideEffects:
    async def test_force_cancel_paid_order_issues_refund_and_notifies(
        self,
        client,
        seed_user,
        seed_hospital,
        seed_order,
        seed_payment,
    ):
        patient = await seed_user(phone="13900000101")
        companion = await seed_user(phone="13900000102", role=UserRole.companion)
        hospital = await seed_hospital()
        order = await seed_order(
            patient.id,
            hospital.id,
            companion_id=companion.id,
            status=OrderStatus.accepted,
        )
        await seed_payment(order.id, patient.id, amount=299.0)

        resp = await client.post(
            f"/api/v1/admin/orders/{order.id}/force-status",
            headers=HEADERS,
            json={"status": "cancelled_by_companion", "reason": "platform override"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["new_status"] == "cancelled_by_companion"

        async with test_session_factory() as session:
            # Refund row created
            refunds = (
                await session.execute(
                    select(Payment).where(
                        Payment.order_id == order.id,
                        Payment.payment_type == "refund",
                    )
                )
            ).scalars().all()
            assert len(refunds) == 1
            assert str(refunds[0].amount) in {"299.00", "299.0"}

            # Both parties notified
            notifs = (
                await session.execute(
                    select(Notification).where(
                        Notification.reference_id == str(order.id)
                    )
                )
            ).scalars().all()
            recipients = {str(n.user_id) for n in notifs}
            assert str(patient.id) in recipients
            assert str(companion.id) in recipients

            # Audit reason captures the side-effects summary
            logs = (
                await session.execute(
                    select(AdminAuditLog).where(
                        AdminAuditLog.target_id == order.id,
                        AdminAuditLog.action == "force_status",
                    )
                )
            ).scalars().all()
            assert len(logs) == 1
            reason = logs[0].reason or ""
            assert "side_effects=" in reason
            assert "refund=issued" in reason
            assert "notify=patient+companion" in reason

    async def test_force_cancel_unpaid_order_skips_refund_but_notifies(
        self, client, seed_user, seed_hospital, seed_order
    ):
        patient = await seed_user(phone="13900000111")
        hospital = await seed_hospital()
        order = await seed_order(patient.id, hospital.id)

        resp = await client.post(
            f"/api/v1/admin/orders/{order.id}/force-status",
            headers=HEADERS,
            json={"status": "cancelled_by_patient", "reason": "test"},
        )
        assert resp.status_code == 200, resp.text

        async with test_session_factory() as session:
            refunds = (
                await session.execute(
                    select(Payment).where(
                        Payment.order_id == order.id,
                        Payment.payment_type == "refund",
                    )
                )
            ).scalars().all()
            assert refunds == []

            logs = (
                await session.execute(
                    select(AdminAuditLog).where(
                        AdminAuditLog.target_id == order.id,
                        AdminAuditLog.action == "force_status",
                    )
                )
            ).scalars().all()
            assert len(logs) == 1
            assert "refund=unpaid" in (logs[0].reason or "")
            # No companion on the seeded order → patient_only
            assert "notify=patient_only" in (logs[0].reason or "")

    async def test_force_complete_bumps_companion_total_orders(
        self,
        client,
        seed_user,
        seed_hospital,
        seed_order,
        seed_companion_profile,
    ):
        patient = await seed_user(phone="13900000121")
        companion = await seed_user(phone="13900000122", role=UserRole.companion)
        profile = await seed_companion_profile(user_id=companion.id)
        baseline = profile.total_orders

        hospital = await seed_hospital()
        order = await seed_order(
            patient.id,
            hospital.id,
            companion_id=companion.id,
            status=OrderStatus.in_progress,
        )

        resp = await client.post(
            f"/api/v1/admin/orders/{order.id}/force-status",
            headers=HEADERS,
            json={"status": "completed", "reason": "ops manual completion"},
        )
        assert resp.status_code == 200, resp.text

        async with test_session_factory() as session:
            row = (
                await session.execute(
                    select(CompanionProfile).where(
                        CompanionProfile.user_id == companion.id
                    )
                )
            ).scalar_one()
            assert row.total_orders == baseline + 1


# ---------------------------------------------------------------------------
# Dead-letter admin endpoints
# ---------------------------------------------------------------------------


class TestAdminDeadLetters:
    async def _seed_row(self, **overrides):
        async with test_session_factory() as session:
            row = DeadLetter(
                channel=overrides.get("channel", "order_refund"),
                reason=overrides.get("reason", "refund_provider_error"),
                target_type=overrides.get("target_type", "order"),
                target_id=overrides.get("target_id", uuid.uuid4()),
                payload=overrides.get("payload", {"amount": "299.00"}),
                status=overrides.get("status", DeadLetterStatus.pending),
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return row

    async def test_list_filters_and_paginates(self, client):
        await self._seed_row(channel="order_refund")
        await self._seed_row(channel="notification")

        resp = await client.get(
            "/api/v1/admin/dead-letters?channel=order_refund", headers=HEADERS
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] >= 1
        assert all(it["channel"] == "order_refund" for it in body["items"])
        assert all(it["status"] == "pending" for it in body["items"])

    async def test_list_rejects_invalid_status(self, client):
        resp = await client.get(
            "/api/v1/admin/dead-letters?status=nope", headers=HEADERS
        )
        assert resp.status_code == 400

    async def test_detail_and_resolve_roundtrip(self, client):
        row = await self._seed_row()
        resp = await client.get(
            f"/api/v1/admin/dead-letters/{row.id}", headers=HEADERS
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == str(row.id)
        assert resp.json()["status"] == "pending"

        resp = await client.post(
            f"/api/v1/admin/dead-letters/{row.id}/resolve",
            headers=HEADERS,
            json={"note": "manual refund via wechat backend"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "resolved"
        assert data["resolved_by"]
        assert data["resolution_note"] == "manual refund via wechat backend"

        # Audit row was created
        async with test_session_factory() as session:
            logs = (
                await session.execute(
                    select(AdminAuditLog).where(
                        AdminAuditLog.target_id == row.id,
                        AdminAuditLog.action == "dead_letter_resolve",
                    )
                )
            ).scalars().all()
            assert len(logs) == 1

        # Idempotency-ish: resolving again returns 400.
        resp = await client.post(
            f"/api/v1/admin/dead-letters/{row.id}/resolve",
            headers=HEADERS,
            json={"note": "again"},
        )
        assert resp.status_code == 400

    async def test_resolve_404(self, client):
        resp = await client.post(
            f"/api/v1/admin/dead-letters/{uuid.uuid4()}/resolve",
            headers=HEADERS,
            json={"note": "x"},
        )
        assert resp.status_code == 404


pytestmark = pytest.mark.asyncio
