"""Tests for AI summary generator pipeline (S2-DEV-005).

Acceptance #9 (8+ cases):
1. 成功路径 → AIDigest.ok + 入库 + 成本 metric +
2. 单订单超限截断 (per_order_truncated)
3. 日预算超限降级 (daily_budget)
4. blocklist 命中降级 (post_check_blocked)
5. 边界『建议休息』不误降
6. blocklist 热更新生效
7. DeepSeek RetryableError → degraded provider_timeout + budget release
8. DeepSeek NonRetryableError → FAILED + dead_letter
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.models.ai_digest import AIDigest, AIDigestStatus
from app.models.dead_letter import DeadLetter
from app.models.hospital import Hospital
from app.models.order import Order, OrderStatus, ServiceType
from app.models.user import User, UserRole
from app.services.ai_summary import budget as ai_budget
from app.services.ai_summary import deepseek_client as ds
from app.services.ai_summary.digester import (
    DEGRADED_TEMPLATE,
    generate_digest,
)
from app.services.ai_summary.post_check import (
    BlocklistChecker,
    reset_default_checker_for_test,
)
from tests.conftest import FakeRedis, test_session_factory


# ---------------------------------------------------------------------------
# helpers / fixtures
# ---------------------------------------------------------------------------


class _BudgetRedis(FakeRedis):
    """FakeRedis extended with the float-counter ops budget.py expects."""

    async def incrbyfloat(self, key: str, amount: float) -> float:
        cur = float(self._store.get(key, "0"))
        new = cur + float(amount)
        self._store[key] = str(new)
        return new

    async def expire(self, key: str, ttl: int) -> bool:  # no-op for tests
        return True


@pytest.fixture
def redis():
    return _BudgetRedis()


async def _seed_order() -> uuid.UUID:
    async with test_session_factory() as session:
        user = User(
            phone=f"139{uuid.uuid4().int % 100000000:08d}",
            role=UserRole.patient,
            roles="patient",
            is_active=True,
        )
        session.add(user)
        await session.flush()
        hospital = Hospital(id=uuid.uuid4(), name="H1")
        session.add(hospital)
        await session.flush()
        order = Order(
            id=uuid.uuid4(),
            order_number=f"YLA-{uuid.uuid4().hex[:10].upper()}",
            patient_id=user.id,
            hospital_id=hospital.id,
            service_type=ServiceType.full_accompany,
            status=OrderStatus.completed,
            appointment_date="2026-06-01",
            appointment_time="09:00",
            price=Decimal("299.00"),
        )
        session.add(order)
        await session.commit()
        return order.id


def _mock_ok(content: str, *, prompt_tokens: int = 80, completion_tokens: int = 60, truncated: bool = False):
    async def _call(*, prompt, max_tokens, system=None):
        return ds.DeepSeekChatResult(
            content=content,
            model="deepseek-chat",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_yuan=ds.estimate_cost_yuan(prompt_tokens, completion_tokens),
            truncated=truncated,
        )

    return _call


@pytest.fixture(autouse=True)
def _reset_checker_singleton():
    reset_default_checker_for_test()
    yield
    reset_default_checker_for_test()


# ===========================================================================
# 1. happy path
# ===========================================================================


@pytest.mark.asyncio
async def test_success_persists_ok_digest_and_charges_budget(redis):
    order_id = await _seed_order()
    with patch(
        "app.services.ai_summary.digester.ds.chat_completion",
        new=_mock_ok("小明上午 9 点到院，做了血常规，医生交代回家多休息。"),
    ):
        async with test_session_factory() as session:
            outcome = await generate_digest(
                session=session, redis=redis, order_id=order_id, prompt="时间线..."
            )

    assert outcome.status == AIDigestStatus.OK
    assert outcome.cost_yuan > 0
    assert outcome.model == "deepseek-chat"
    # row persisted
    async with test_session_factory() as session:
        row = (
            await session.execute(select(AIDigest).where(AIDigest.order_id == order_id))
        ).scalar_one()
        assert row.status == AIDigestStatus.OK
        assert "血常规" in (row.summary or "")
    # budget charged
    today_spent = await ai_budget.get_today_spent(redis)
    assert today_spent > 0


# ===========================================================================
# 2. per-order cap → degraded (over-long prompt)
# ===========================================================================


@pytest.mark.asyncio
async def test_per_order_cap_degrades_when_prompt_blows_budget(redis):
    order_id = await _seed_order()
    # Massive prompt → estimated_max_completion_tokens == 0 → early degrade,
    # no LLM call at all.
    with patch(
        "app.services.ai_summary.digester.ds.chat_completion",
        new=AsyncMock(side_effect=AssertionError("LLM should not be called")),
    ):
        async with test_session_factory() as session:
            outcome = await generate_digest(
                session=session,
                redis=redis,
                order_id=order_id,
                prompt="x" * 500_000,
            )

    assert outcome.status == AIDigestStatus.DEGRADED
    assert outcome.degraded_reason == "per_order_truncated"
    assert outcome.summary == DEGRADED_TEMPLATE
    assert outcome.cost_yuan == Decimal("0")


# ===========================================================================
# 3. daily budget exhausted
# ===========================================================================


@pytest.mark.asyncio
async def test_daily_budget_exhausted_degrades_without_calling_llm(redis, monkeypatch):
    # Slam the day counter past the cap before the call.
    from app.config import settings as cfg

    today_key_value = str(float(cfg.ai_daily_budget_yuan) + 1.0)
    # seed today's counter manually
    from app.services.ai_summary.budget import _daily_key

    redis._store[_daily_key()] = today_key_value

    order_id = await _seed_order()
    with patch(
        "app.services.ai_summary.digester.ds.chat_completion",
        new=AsyncMock(side_effect=AssertionError("LLM must not be called")),
    ):
        async with test_session_factory() as session:
            outcome = await generate_digest(
                session=session, redis=redis, order_id=order_id, prompt="ok"
            )

    assert outcome.status == AIDigestStatus.DEGRADED
    assert outcome.degraded_reason == "daily_budget"
    assert outcome.summary == DEGRADED_TEMPLATE


# ===========================================================================
# 4. blocklist hit → degraded
# ===========================================================================


@pytest.mark.asyncio
async def test_post_check_blocklist_hit_degrades(redis):
    order_id = await _seed_order()
    with patch(
        "app.services.ai_summary.digester.ds.chat_completion",
        new=_mock_ok("根据症状确诊为重症肺炎，建议立即住院治疗。"),
    ):
        async with test_session_factory() as session:
            outcome = await generate_digest(
                session=session, redis=redis, order_id=order_id, prompt="t"
            )

    assert outcome.status == AIDigestStatus.DEGRADED
    assert outcome.degraded_reason == "post_check_blocked"
    assert outcome.summary == DEGRADED_TEMPLATE
    # cost still charged: the model already ran
    assert outcome.cost_yuan > 0


# ===========================================================================
# 5. boundary: '建议休息' must NOT trigger blocklist
# ===========================================================================


@pytest.mark.asyncio
async def test_post_check_does_not_false_positive_on_gentle_advice(redis):
    order_id = await _seed_order()
    with patch(
        "app.services.ai_summary.digester.ds.chat_completion",
        new=_mock_ok("就诊已结束，医生建议休息几天，注意保暖。"),
    ):
        async with test_session_factory() as session:
            outcome = await generate_digest(
                session=session, redis=redis, order_id=order_id, prompt="t"
            )

    assert outcome.status == AIDigestStatus.OK
    assert outcome.degraded_reason is None


# ===========================================================================
# 6. blocklist hot reload
# ===========================================================================


def test_blocklist_hot_reload_picks_up_new_phrase(tmp_path: Path):
    yaml_path = tmp_path / "blocklist.yaml"
    yaml_path.write_text("phrases:\n  - 旧词\n", encoding="utf-8")
    checker = BlocklistChecker(path=yaml_path)
    assert checker.check("出现旧词").blocked is True
    assert checker.check("一个新词").blocked is False

    # Rewrite with mtime bumped
    import time as _t

    _t.sleep(0.01)
    yaml_path.write_text("phrases:\n  - 新词\n", encoding="utf-8")
    # Force mtime to differ (file systems with 1s granularity)
    import os as _os

    st = _os.stat(yaml_path)
    _os.utime(yaml_path, ns=(st.st_atime_ns, st.st_mtime_ns + 10_000_000))

    assert checker.check("一个新词").blocked is True
    assert checker.check("出现旧词").blocked is False


# ===========================================================================
# 7. RetryableError (network / 5xx) → degraded provider_timeout + release
# ===========================================================================


@pytest.mark.asyncio
async def test_retryable_error_releases_budget_and_degrades(redis):
    from app.utils.outbound import RetryableError

    order_id = await _seed_order()

    async def _boom(*, prompt, max_tokens, system=None):
        raise RetryableError("DeepSeek 503: upstream timeout")

    with patch(
        "app.services.ai_summary.digester.ds.chat_completion", new=_boom
    ):
        async with test_session_factory() as session:
            outcome = await generate_digest(
                session=session, redis=redis, order_id=order_id, prompt="t"
            )

    assert outcome.status == AIDigestStatus.DEGRADED
    assert outcome.degraded_reason == "provider_timeout"
    # Budget should be ~0 — reservation released on failure.
    today = await ai_budget.get_today_spent(redis)
    assert today <= Decimal("0.0001"), f"budget not released, today={today}"


# ===========================================================================
# 8. NonRetryableError → FAILED + dead_letter row
# ===========================================================================


@pytest.mark.asyncio
async def test_nonretryable_error_records_dead_letter_and_failed_status(redis):
    from app.utils.outbound import NonRetryableError

    order_id = await _seed_order()

    async def _boom(*, prompt, max_tokens, system=None):
        raise NonRetryableError("DEEPSEEK_API_KEY missing")

    with patch(
        "app.services.ai_summary.digester.ds.chat_completion", new=_boom
    ):
        async with test_session_factory() as session:
            outcome = await generate_digest(
                session=session, redis=redis, order_id=order_id, prompt="t"
            )

    assert outcome.status == AIDigestStatus.FAILED
    assert outcome.degraded_reason == "provider_failed"

    async with test_session_factory() as session:
        digest = (
            await session.execute(
                select(AIDigest).where(AIDigest.order_id == order_id)
            )
        ).scalar_one()
        assert digest.status == AIDigestStatus.FAILED
        dl = (
            await session.execute(
                select(DeadLetter).where(DeadLetter.target_id == order_id)
            )
        ).scalars().all()
        assert any(d.channel == "ai_summary" for d in dl)
