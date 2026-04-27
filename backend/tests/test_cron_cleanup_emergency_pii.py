"""ADR-0029 — cleanup_emergency_pii cron 单元测试。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.cron.cleanup_emergency_pii import cleanup_emergency_pii
from app.core.pii import encrypt_phone, phone_hash
from app.models.admin_audit_log import AdminAuditLog
from app.models.emergency import EmergencyContact, EmergencyEvent

pytestmark = pytest.mark.asyncio


async def test_cron_purges_expired_contacts_and_old_events(seed_user):
    user = await seed_user(phone="13900139001")
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)

    from tests.conftest import test_session_factory

    async with test_session_factory() as session:
        # 已过期联系人（expires_at < now）
        expired = EmergencyContact(
            user_id=user.id,
            name="A",
            phone_encrypted=encrypt_phone("13800138001"),
            phone_hash=phone_hash("13800138001"),
            relationship="父",
            expires_at=now - timedelta(days=1),
        )
        # 未过期联系人
        active = EmergencyContact(
            user_id=user.id,
            name="B",
            phone_encrypted=encrypt_phone("13800138002"),
            phone_hash=phone_hash("13800138002"),
            relationship="母",
            expires_at=now + timedelta(days=30),
        )
        # 未设过期（永久）
        permanent = EmergencyContact(
            user_id=user.id,
            name="C",
            phone_encrypted=encrypt_phone("13800138003"),
            phone_hash=phone_hash("13800138003"),
            relationship="子",
            expires_at=None,
        )
        # 老事件 ( > 180d ) → 删
        old_event = EmergencyEvent(
            patient_id=user.id,
            contact_called_encrypted=encrypt_phone("110"),
            contact_called_hash=phone_hash("110"),
            contact_type="hotline",
            triggered_at=now - timedelta(days=181),
        )
        # 近期事件 → 保留
        recent_event = EmergencyEvent(
            patient_id=user.id,
            contact_called_encrypted=encrypt_phone("120"),
            contact_called_hash=phone_hash("120"),
            contact_type="hotline",
            triggered_at=now - timedelta(days=30),
        )
        session.add_all([expired, active, permanent, old_event, recent_event])
        await session.commit()

    async with test_session_factory() as session:
        result = await cleanup_emergency_pii(
            session=session,
            now_fn=lambda: now,
        )

    assert result == {"status": "ok", "contacts_deleted": 1, "events_deleted": 1}

    async with test_session_factory() as session:
        contacts = (await session.execute(select(EmergencyContact))).scalars().all()
        events = (await session.execute(select(EmergencyEvent))).scalars().all()
        audits = (
            await session.execute(
                select(AdminAuditLog).where(
                    AdminAuditLog.action == "cron_cleanup_emergency_pii"
                )
            )
        ).scalars().all()

    assert {c.name for c in contacts} == {"B", "C"}
    assert len(events) == 1
    assert len(audits) == 1
    assert "contacts_deleted" in audits[0].reason


async def test_cron_no_op_when_nothing_to_delete(seed_user):
    user = await seed_user(phone="13900139002")
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)

    from tests.conftest import test_session_factory

    async with test_session_factory() as session:
        c = EmergencyContact(
            user_id=user.id,
            name="A",
            phone_encrypted=encrypt_phone("13800138001"),
            phone_hash=phone_hash("13800138001"),
            relationship="父",
            expires_at=now + timedelta(days=10),
        )
        session.add(c)
        await session.commit()

    async with test_session_factory() as session:
        result = await cleanup_emergency_pii(
            session=session,
            now_fn=lambda: now,
        )

    assert result == {"status": "ok", "contacts_deleted": 0, "events_deleted": 0}

    # 无清理 → 不写 audit
    async with test_session_factory() as session:
        audits = (
            await session.execute(
                select(AdminAuditLog).where(
                    AdminAuditLog.action == "cron_cleanup_emergency_pii"
                )
            )
        ).scalars().all()
    assert audits == []
