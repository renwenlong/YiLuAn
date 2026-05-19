"""F-07 tests: 复诊提醒 CRUD + cron dispatch + provider abstraction."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.cron.followup_reminder_dispatch import _run as dispatch_run
from app.models.followup_reminder import (
    MAX_ATTEMPTS,
    FollowupReminder,
    FollowupReminderStatus,
)
from app.models.order import Order, OrderStatus, SERVICE_PRICES, ServiceType
from app.services.subscribe_message import (
    FollowupReminderPayload,
    ProviderResult,
    SubscribeMessageProvider,
)

from .conftest import test_session_factory


# ---------- helpers ----------------------------------------------------------


async def _seed_completed_order(
    session, *, patient_id: uuid.UUID, hospital_id: uuid.UUID, status: OrderStatus = OrderStatus.completed
) -> Order:
    order = Order(
        id=uuid.uuid4(),
        order_number=f"T{uuid.uuid4().hex[:12].upper()}",
        patient_id=patient_id,
        hospital_id=hospital_id,
        service_type=ServiceType.full_accompany,
        status=status,
        appointment_date="2026-04-30",
        appointment_time="09:00",
        price=SERVICE_PRICES[ServiceType.full_accompany],
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    session.add(order)
    await session.flush()
    return order


# ---------- API: create / list / cancel --------------------------------------


@pytest.mark.asyncio
class TestFollowupReminderAPI:
    async def test_create_for_completed_order(
        self, authenticated_client, seed_hospital
    ):
        hospital = await seed_hospital()
        user = authenticated_client._test_user  # type: ignore[attr-defined]
        async with test_session_factory() as session:
            order = await _seed_completed_order(
                session, patient_id=user.id, hospital_id=hospital.id
            )
            await session.commit()

        remind_at = (datetime.now(timezone.utc) + timedelta(days=14)).isoformat()
        resp = await authenticated_client.post(
            f"/api/v1/orders/{order.id}/followup-reminders",
            json={
                "order_id": str(order.id),
                "remind_at": remind_at,
                "note": "复查血糖",
            },
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["status"] == "pending"
        assert body["attempts"] == 0
        assert body["note"] == "复查血糖"

    async def test_create_rejected_when_order_not_completed(
        self, authenticated_client, seed_hospital
    ):
        hospital = await seed_hospital()
        user = authenticated_client._test_user  # type: ignore[attr-defined]
        async with test_session_factory() as session:
            order = await _seed_completed_order(
                session, patient_id=user.id, hospital_id=hospital.id,
                status=OrderStatus.in_progress,
            )
            await session.commit()
        resp = await authenticated_client.post(
            f"/api/v1/orders/{order.id}/followup-reminders",
            json={
                "order_id": str(order.id),
                "remind_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
            },
        )
        assert resp.status_code == 400

    async def test_create_rejects_other_users_order(
        self, authenticated_client, seed_user, seed_hospital
    ):
        from app.models.user import UserRole

        hospital = await seed_hospital()
        other = await seed_user(phone="13700007777", role=UserRole.patient)
        async with test_session_factory() as session:
            order = await _seed_completed_order(
                session, patient_id=other.id, hospital_id=hospital.id
            )
            await session.commit()
        resp = await authenticated_client.post(
            f"/api/v1/orders/{order.id}/followup-reminders",
            json={
                "order_id": str(order.id),
                "remind_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
            },
        )
        assert resp.status_code == 404

    async def test_create_rejects_path_body_id_mismatch(
        self, authenticated_client, seed_hospital
    ):
        hospital = await seed_hospital()
        user = authenticated_client._test_user  # type: ignore[attr-defined]
        async with test_session_factory() as session:
            order = await _seed_completed_order(
                session, patient_id=user.id, hospital_id=hospital.id
            )
            await session.commit()
        resp = await authenticated_client.post(
            f"/api/v1/orders/{order.id}/followup-reminders",
            json={
                "order_id": str(uuid.uuid4()),
                "remind_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
            },
        )
        assert resp.status_code == 400

    async def test_list_and_cancel(
        self, authenticated_client, seed_hospital
    ):
        hospital = await seed_hospital()
        user = authenticated_client._test_user  # type: ignore[attr-defined]
        async with test_session_factory() as session:
            order = await _seed_completed_order(
                session, patient_id=user.id, hospital_id=hospital.id
            )
            await session.commit()
        created = (
            await authenticated_client.post(
                f"/api/v1/orders/{order.id}/followup-reminders",
                json={
                    "order_id": str(order.id),
                    "remind_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
                },
            )
        ).json()

        listing = (
            await authenticated_client.get(
                "/api/v1/orders/me/followup-reminders"
            )
        ).json()
        assert listing["total"] >= 1
        assert any(item["id"] == created["id"] for item in listing["items"])

        rm = await authenticated_client.delete(
            f"/api/v1/orders/me/followup-reminders/{created['id']}"
        )
        assert rm.status_code == 204

        # cancel twice → 400 (no longer pending)
        rm2 = await authenticated_client.delete(
            f"/api/v1/orders/me/followup-reminders/{created['id']}"
        )
        assert rm2.status_code == 400


# ---------- cron dispatch ----------------------------------------------------


class _StubOK(SubscribeMessageProvider):
    name = "stub-ok"

    def __init__(self):
        self.calls: list[FollowupReminderPayload] = []

    async def send(self, payload):
        self.calls.append(payload)
        return ProviderResult(success=True, message_id="ok-1")


class _StubFail(SubscribeMessageProvider):
    name = "stub-fail"

    def __init__(self):
        self.calls = 0

    async def send(self, payload):
        self.calls += 1
        return ProviderResult(success=False, error="provider down")


async def _make_reminder(session, *, patient_id, hospital_id, remind_at):
    order = await _seed_completed_order(
        session, patient_id=patient_id, hospital_id=hospital_id
    )
    reminder = FollowupReminder(
        user_id=patient_id,
        order_id=order.id,
        remind_at=remind_at,
    )
    session.add(reminder)
    await session.flush()
    return reminder


@pytest.mark.asyncio
class TestFollowupReminderCron:
    async def test_dispatch_sends_due_pending(self, seed_hospital, seed_user):
        from app.models.user import UserRole

        hospital = await seed_hospital()
        user = await seed_user(phone="13700001111", role=UserRole.patient)
        past = datetime.now(timezone.utc) - timedelta(minutes=1)
        future = datetime.now(timezone.utc) + timedelta(days=1)
        async with test_session_factory() as session:
            due = await _make_reminder(
                session, patient_id=user.id, hospital_id=hospital.id, remind_at=past
            )
            not_due = await _make_reminder(
                session, patient_id=user.id, hospital_id=hospital.id, remind_at=future
            )
            await session.commit()
            due_id, not_due_id = due.id, not_due.id

        provider = _StubOK()
        async with test_session_factory() as session:
            result = await dispatch_run(session, provider=provider)
            await session.commit()
        assert result == {"due": 1, "sent": 1, "failed": 0, "retry": 0}

        async with test_session_factory() as session:
            due_after = await session.get(FollowupReminder, due_id)
            not_due_after = await session.get(FollowupReminder, not_due_id)
            assert due_after.status == FollowupReminderStatus.sent
            assert due_after.sent_at is not None
            assert due_after.provider_message_id == "ok-1"
            assert not_due_after.status == FollowupReminderStatus.pending

    async def test_dispatch_marks_failed_after_max_attempts(
        self, seed_hospital, seed_user
    ):
        from app.models.user import UserRole

        hospital = await seed_hospital()
        user = await seed_user(phone="13700002222", role=UserRole.patient)
        past = datetime.now(timezone.utc) - timedelta(minutes=1)
        async with test_session_factory() as session:
            reminder = await _make_reminder(
                session, patient_id=user.id, hospital_id=hospital.id, remind_at=past
            )
            await session.commit()
            reminder_id = reminder.id

        provider = _StubFail()
        for i in range(MAX_ATTEMPTS - 1):
            async with test_session_factory() as session:
                await dispatch_run(session, provider=provider)
                await session.commit()
            async with test_session_factory() as session:
                r = await session.get(FollowupReminder, reminder_id)
                assert r.status == FollowupReminderStatus.pending
                assert r.attempts == i + 1

        async with test_session_factory() as session:
            await dispatch_run(session, provider=provider)
            await session.commit()
        async with test_session_factory() as session:
            r = await session.get(FollowupReminder, reminder_id)
            assert r.status == FollowupReminderStatus.failed
            assert r.attempts == MAX_ATTEMPTS
            assert r.last_error == "provider down"

    async def test_dispatch_idempotent_after_sent(self, seed_hospital, seed_user):
        from app.models.user import UserRole

        hospital = await seed_hospital()
        user = await seed_user(phone="13700003333", role=UserRole.patient)
        past = datetime.now(timezone.utc) - timedelta(minutes=1)
        async with test_session_factory() as session:
            await _make_reminder(
                session, patient_id=user.id, hospital_id=hospital.id, remind_at=past
            )
            await session.commit()

        provider = _StubOK()
        async with test_session_factory() as session:
            first = await dispatch_run(session, provider=provider)
            await session.commit()
        async with test_session_factory() as session:
            second = await dispatch_run(session, provider=provider)
            await session.commit()
        assert first["sent"] == 1
        assert second == {"due": 0, "sent": 0, "failed": 0, "retry": 0}
        assert len(provider.calls) == 1
