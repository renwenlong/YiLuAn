"""ADR-0029 / D-043 — delete_account 联动清理 emergency_contacts + events 测试。"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.pii import encrypt_phone, phone_hash
from app.models.admin_audit_log import AdminAuditLog
from app.models.emergency import EmergencyContact, EmergencyEvent
from app.models.user import User
from app.services.user import UserService

pytestmark = pytest.mark.asyncio


async def test_delete_account_purges_emergency_contacts_and_events(seed_user):
    user = await seed_user(phone="13900139888")

    from tests.conftest import test_session_factory

    # 种 2 个紧急联系人 + 1 个紧急事件
    async with test_session_factory() as session:
        session.add_all(
            [
                EmergencyContact(
                    user_id=user.id,
                    name="父亲",
                    phone_encrypted=encrypt_phone("13800138001"),
                    phone_hash=phone_hash("13800138001"),
                    relationship="父亲",
                ),
                EmergencyContact(
                    user_id=user.id,
                    name="母亲",
                    phone_encrypted=encrypt_phone("13800138002"),
                    phone_hash=phone_hash("13800138002"),
                    relationship="母亲",
                ),
                EmergencyEvent(
                    patient_id=user.id,
                    contact_called_encrypted=encrypt_phone("110"),
                    contact_called_hash=phone_hash("110"),
                    contact_type="hotline",
                ),
            ]
        )
        await session.commit()

    # 调 delete_account
    async with test_session_factory() as session:
        u = (
            await session.execute(select(User).where(User.id == user.id))
        ).scalar_one()
        svc = UserService(session)
        await svc.delete_account(u)
        await session.commit()

    # 验证三张表
    async with test_session_factory() as session:
        contacts = (
            await session.execute(
                select(EmergencyContact).where(EmergencyContact.user_id == user.id)
            )
        ).scalars().all()
        events = (
            await session.execute(
                select(EmergencyEvent).where(EmergencyEvent.patient_id == user.id)
            )
        ).scalars().all()
        u = (
            await session.execute(select(User).where(User.id == user.id))
        ).scalar_one()
        audits = (
            await session.execute(
                select(AdminAuditLog).where(
                    AdminAuditLog.action == "user_self_delete",
                    AdminAuditLog.target_id == user.id,
                )
            )
        ).scalars().all()

    assert contacts == []
    assert events == []
    assert u.is_deleted  # 用户自己也软删
    assert u.deleted_at is not None
    assert len(audits) == 1
    assert "emergency_contacts_purged" in audits[0].reason
    assert "2" in audits[0].reason  # 2 contacts
    assert "emergency_events_purged" in audits[0].reason
