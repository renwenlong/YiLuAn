"""Model smoke tests for S3 preparation_packages (ADR-0048 §7.1)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.preparation_package import PreparationPackage, PrepStatus
from app.models.prompt_version import PromptVersion
from tests.conftest import test_session_factory
from tests.models.test_share_and_digest import _seed_order_and_user


@pytest.mark.asyncio
async def test_preparation_package_insert_and_query() -> None:
    async with test_session_factory() as session:
        order_id, _ = await _seed_order_and_user(session)
        prompt = PromptVersion(
            id=uuid.uuid4(),
            version=f"test-{uuid.uuid4().hex[:8]}",
            git_commit_hash="a" * 40,
            prompt_text="生成陪诊准备包",
            model="deepseek-chat",
            temperature=Decimal("0.20"),
            created_at=datetime.now(timezone.utc),
        )
        package = PreparationPackage(
            id=uuid.uuid4(),
            order_id=order_id,
            status=PrepStatus.active,
            carry_items=["身份证", "医保卡"],
            pre_visit_notes={"text": "就诊前避免空腹"},
            possible_questions=["用药是否需要调整?"],
            companion_focus_points=["协助排队取号"],
            prompt_version_id=prompt.id,
            trace_id="trace-smoke",
            model="deepseek-chat",
            estimated_cost_yuan=Decimal("0.100000"),
            actual_cost_yuan=Decimal("0.088000"),
            generation_time_ms=1234,
            fallback_reason=None,
            user_checked_items=["身份证"],
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(prompt)
        session.add(package)
        await session.commit()

        row = (
            await session.execute(
                select(PreparationPackage).where(PreparationPackage.order_id == order_id)
            )
        ).scalar_one()
        assert row.status == PrepStatus.active
        assert row.carry_items == ["身份证", "医保卡"]
        assert row.prompt_version_id == prompt.id
        assert row.actual_cost_yuan == Decimal("0.088000")


@pytest.mark.asyncio
async def test_preparation_package_order_id_unique() -> None:
    async with test_session_factory() as session:
        order_id, _ = await _seed_order_and_user(session)
        now = datetime.now(timezone.utc)
        session.add_all(
            [
                PreparationPackage(
                    id=uuid.uuid4(),
                    order_id=order_id,
                    status=PrepStatus.pending,
                    created_at=now,
                    updated_at=now,
                ),
                PreparationPackage(
                    id=uuid.uuid4(),
                    order_id=order_id,
                    status=PrepStatus.pending,
                    created_at=now,
                    updated_at=now,
                ),
            ]
        )
        with pytest.raises(IntegrityError):
            await session.flush()
        await session.rollback()
