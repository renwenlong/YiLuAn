"""Shared fixtures for prep-package ABAC API tests."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import pytest

from app.core.admin_jwt import create_admin_access_token
from app.core.security import create_access_token
from app.models.admin_user import AdminRole, AdminUser
from app.models.hospital import Hospital
from app.models.order import Order, OrderStatus
from app.models.preparation_package import PreparationPackage, PrepStatus
from app.models.user import User, UserRole
from tests.conftest import test_session_factory


async def seed_admin_token(username: str = "prep_ops") -> str:
    async with test_session_factory() as session:
        admin = AdminUser(
            username=username,
            password_hash="test-not-used",
            role=AdminRole.super_,
            is_active=True,
        )
        session.add(admin)
        await session.commit()
        await session.refresh(admin)
        return create_admin_access_token(admin)


async def seed_prep_package(order_id: UUID) -> PreparationPackage:
    async with test_session_factory() as session:
        package = PreparationPackage(
            order_id=order_id,
            status=PrepStatus.active,
            carry_items=["身份证", "医保卡", "既往检查报告"],
            pre_visit_notes="患者有糖尿病史，空腹检查需提前沟通。",
            possible_questions=["是否需要调整用药？", "复查周期多久？"],
            companion_focus_points=["提醒取号", "协助排队", "留意低血糖风险"],
            trace_id="trace-prep-001",
            model="deepseek-chat",
            estimated_cost_yuan=Decimal("0.120000"),
            actual_cost_yuan=Decimal("0.100000"),
            generation_time_ms=1234,
            fallback_reason="budget_guard_soft_cap",
            user_checked_items=["身份证"],
        )
        session.add(package)
        await session.commit()
        await session.refresh(package)
        return package


@pytest.fixture
async def prep_abac_context(seed_user, seed_hospital, seed_order):
    patient: User = await seed_user(phone="13810000001", role=UserRole.patient)
    companion: User = await seed_user(phone="13810000002", role=UserRole.companion)
    hospital: Hospital = await seed_hospital(name="ABAC测试医院")
    order: Order = await seed_order(
        patient_id=patient.id,
        companion_id=companion.id,
        hospital_id=hospital.id,
        status=OrderStatus.accepted,
    )
    package = await seed_prep_package(order.id)
    return {
        "patient": patient,
        "companion": companion,
        "order": order,
        "package": package,
        "patient_token": create_access_token({"sub": str(patient.id), "role": "patient"}),
        "companion_token": create_access_token(
            {"sub": str(companion.id), "role": "companion"}
        ),
        "admin_token": await seed_admin_token(),
    }
