"""[S3-DEV-002-PREP-GENERATE-WITH-BUDGETGUARD / ADR-0048 §8 P4 acceptance test]

集成测试 — 4 路径覆盖 (acceptance criterion #5):

1. **happy**: ALLOW → LLM 返 valid JSON → status=active, fallback_reason=None
2. **soft warning 90% WARN**: redis seed 到 90%+, ALLOW(降 FALLBACK 仍调 LLM)→
   status=active, 但 fire info alert(此测仅 verify 不阻调用 + 累计 cost)
3. **EXHAUSTED 100%+**: redis seed >100% → REJECT → status=active_fallback_template +
   fallback_reason=BUDGET_EXHAUSTED, 4 块 content 从 template
4. **LLM error 3 retries fail**: monkeypatch chat_completion 抛 RetryableError → 
   3 retry 后 fail → status=generation_failed + fallback_reason=LLM_ERROR

monkeypatch policy (Q2 拍板): patch 
``app.services.ai_summary.deepseek_client.chat_completion`` 返各场景定值.
真 redis (FakeRedis _BudgetRedis) + 真 PG (test_session_factory).

mock LLM JSON 输出固定 4 块结构 + 不含 blocklist 关键词 (避免误 L2 拦截).
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select

# 注意: 别名导入避免 pytest collect-by-name 陷阱 (MEMORY 2026-06-10)
from tests.conftest import test_session_factory as _session_factory

# 显式声明依赖的 fixture plugin (defense-in-depth)
pytest_plugins = ["tests.services.test_ai_summary"]  # 提供 _BudgetRedis 共享

from app.models.preparation_package import PrepStatus, PreparationPackage
from app.models.prompt_version import PromptVersion
from app.services.ai_budget_guard import AIBudgetGuard, BudgetAxis
from app.services.ai_summary import deepseek_client as ds
from app.utils.outbound import RetryableError
from app.services.prep_generate_service import (
    FallbackReason,
    _load_fallback_template,
    generate_for_order,
    reset_fallback_cache,
)


# ─────────────────────────── shared fixture seed ───────────────────────────

VALID_LLM_JSON = """{
  "carry_items": ["身份证", "医保卡", "病历本"],
  "pre_visit_notes": "请提前到院,准备好相关材料。",
  "possible_questions": ["请问需要做什么检查?", "是否需要复诊?"],
  "companion_focus_points": ["陪同到诊室", "记录医嘱", "协助取药"]
}"""


async def _seed_prompt_version() -> PromptVersion:
    """seed 一行 s3_prep active PromptVersion(测试场景共用)."""
    async with _session_factory() as session:
        # 清旧 row 防 UQ 冲(axis+version unique)
        stmt = select(PromptVersion).where(
            PromptVersion.axis == "s3_prep",
        )
        for old in (await session.execute(stmt)).scalars().all():
            await session.delete(old)
        await session.commit()

        row = PromptVersion(
            id=uuid.uuid4(),
            axis="s3_prep",
            version=f"v0.test-{uuid.uuid4().hex[:8]}",
            git_commit_hash="0" * 40,
            prompt_text="system: 你是医疗助手, 帮用户准备就诊用品. 用户主诉: {chief_complaint}",
            model="deepseek-chat",
            max_tokens=1500,
            is_active=True,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row


async def _seed_pending_package(order_id: uuid.UUID) -> PreparationPackage:
    """seed 一行 PreparationPackage(status=pending), 等待 generate."""
    async with _session_factory() as session:
        pkg = PreparationPackage(
            order_id=order_id,
            status=PrepStatus.pending,
        )
        session.add(pkg)
        await session.commit()
        await session.refresh(pkg)
        return pkg


async def _read_package(order_id: uuid.UUID) -> PreparationPackage | None:
    async with _session_factory() as session:
        stmt = select(PreparationPackage).where(
            PreparationPackage.order_id == order_id,
        )
        return (await session.execute(stmt)).scalar_one_or_none()


# ─────────────────────────── fixture: redis ────────────────────────────────

# `redis` fixture 来自 tests/services/test_ai_summary.py (pytest_plugins 已声明)


@pytest.fixture(autouse=True)
def _reset_fallback_cache():
    """每 test 前清 template cache(防 test 间污染)."""
    reset_fallback_cache()
    yield
    reset_fallback_cache()


# ─────────────────────────── happy path ────────────────────────────────────


class TestHappyPath:
    """AC#5 路径 1: budget ALLOW + LLM valid → status=active."""

    @pytest.mark.asyncio
    async def test_happy_status_active_with_full_trace(
        self, redis, monkeypatch
    ):
        # 1. seed
        pv = await _seed_prompt_version()
        order_id = uuid.uuid4()
        await _seed_pending_package(order_id)

        # 2. monkeypatch LLM 返 valid JSON (mock_llm_happy)
        async def mock_chat(*, prompt, max_tokens, system=None):
            return ds.DeepSeekChatResult(
                content=VALID_LLM_JSON,
                model="deepseek-chat",
                prompt_tokens=200,
                completion_tokens=300,
                cost_yuan=Decimal("0.005000"),
                truncated=False,
            )
        monkeypatch.setattr(
            "app.services.prep_generate_service.ds.chat_completion",
            mock_chat,
        )

        # 3. 调用
        async with _session_factory() as session:
            result = await generate_for_order(
                session, redis,
                order_id=order_id,
                user_chief_complaint="头痛 2 天",
            )

        # 4. 断言: status=active + 全 trace 元数据
        assert result.status == PrepStatus.active
        assert result.fallback_reason is None
        assert result.trace_id is not None and len(result.trace_id) == 36
        assert result.prompt_version_id == pv.id
        assert result.model == "deepseek-chat"
        assert result.estimated_cost_yuan > Decimal("0")
        assert result.actual_cost_yuan > Decimal("0")
        assert result.generation_time_ms > 0
        assert result.carry_items == ["身份证", "医保卡", "病历本"]
        assert "提前到院" in result.pre_visit_notes
        assert len(result.possible_questions) == 2
        assert len(result.companion_focus_points) == 3


# ─────────────────────────── 90% WARN ─────────────────────────────────────


class TestSoftWarning:
    """AC#5 路径 2: budget 90-99% WARN → 仍 ALLOW 调 LLM → status=active."""

    @pytest.mark.asyncio
    async def test_soft_warning_still_allows_llm(
        self, redis, monkeypatch
    ):
        # 1. seed
        await _seed_prompt_version()
        order_id = uuid.uuid4()
        await _seed_pending_package(order_id)

        # 2. redis seed 到 90% 日预算上限
        guard = AIBudgetGuard(BudgetAxis.S3_PREP)
        # daily_budget_yuan 默认 100.0; seed 95 → 95% 已用
        # 加 0.005 estimated 后 95.005 = 95.005% (≥90% 软门限)
        key = guard._daily_key()
        await redis.set(key, str(float(guard.daily_budget_yuan) * 0.95))

        # 3. monkeypatch LLM 返 valid JSON
        async def mock_chat(*, prompt, max_tokens, system=None):
            return ds.DeepSeekChatResult(
                content=VALID_LLM_JSON,
                model="deepseek-chat",
                prompt_tokens=200,
                completion_tokens=300,
                cost_yuan=Decimal("0.005000"),
                truncated=False,
            )
        monkeypatch.setattr(
            "app.services.prep_generate_service.ds.chat_completion",
            mock_chat,
        )

        # 4. 调用
        async with _session_factory() as session:
            result = await generate_for_order(
                session, redis,
                order_id=order_id,
                user_chief_complaint="持续咳嗽",
            )

        # 5. 断言: 90% WARN 不阻 LLM, status=active
        assert result.status == PrepStatus.active
        assert result.fallback_reason is None
        assert result.actual_cost_yuan > Decimal("0")
        # redis daily cost 应已 commit
        spent = await guard.get_today_spent(redis)
        assert spent > Decimal("95")


# ─────────────────────────── 100%+ EXHAUSTED → fallback ───────────────────


class TestBudgetExhausted:
    """AC#5 路径 3: budget 100%+ → REJECT → fallback template."""

    @pytest.mark.asyncio
    async def test_exhausted_uses_fallback_template(
        self, redis, monkeypatch
    ):
        # 1. seed
        pv = await _seed_prompt_version()
        order_id = uuid.uuid4()
        await _seed_pending_package(order_id)

        # 2. redis seed 到 100%+ (101 > 100 上限)
        guard = AIBudgetGuard(BudgetAxis.S3_PREP)
        key = guard._daily_key()
        await redis.set(key, str(float(guard.daily_budget_yuan) * 1.01))

        # 3. monkeypatch LLM (不应被调; 加 spy 验)
        called = []
        async def spy_chat(*, prompt, max_tokens, system=None):
            called.append(1)
            return ds.DeepSeekChatResult(
                content=VALID_LLM_JSON, model="deepseek-chat",
                prompt_tokens=100, completion_tokens=100,
                cost_yuan=Decimal("0.001"),
            )
        monkeypatch.setattr(
            "app.services.prep_generate_service.ds.chat_completion",
            spy_chat,
        )

        # 4. 调用
        async with _session_factory() as session:
            result = await generate_for_order(
                session, redis,
                order_id=order_id,
                user_chief_complaint="腹痛",
            )

        # 5. 断言: status=active_fallback_template + fallback_reason=BUDGET_EXHAUSTED
        assert result.status == PrepStatus.active_fallback_template
        assert result.fallback_reason == FallbackReason.BUDGET_EXHAUSTED
        assert called == [], "LLM 不应被调用(BudgetGuard 拦在前)"
        # 4 块字段来自 fallback template (verify)
        tpl = _load_fallback_template()
        assert result.carry_items == tpl["carry_items"]
        assert result.companion_focus_points == tpl["companion_focus_points"]
        assert result.actual_cost_yuan == Decimal("0")
        assert result.prompt_version_id == pv.id  # 仍写入 trace


# ─────────────────────────── LLM error 3 retries fail ────────────────────


class TestLLMError3Retries:
    """AC#5 路径 4: LLM error 3 retries 后 fail → generation_failed."""

    @pytest.mark.asyncio
    async def test_llm_3_retry_fail_status_generation_failed(
        self, redis, monkeypatch
    ):
        # 1. seed
        pv = await _seed_prompt_version()
        order_id = uuid.uuid4()
        await _seed_pending_package(order_id)

        # 2. monkeypatch LLM 总抛 RetryableError(@outbound_call 装饰器内部已
        #    max_retries=3 处理 — 我 patch 完整 chat_completion 暴露最终抛)
        call_count = []
        async def mock_chat_always_error(*, prompt, max_tokens, system=None):
            call_count.append(1)
            raise RetryableError("simulated LLM 503")
        monkeypatch.setattr(
            "app.services.prep_generate_service.ds.chat_completion",
            mock_chat_always_error,
        )

        # 3. 调用
        async with _session_factory() as session:
            result = await generate_for_order(
                session, redis,
                order_id=order_id,
                user_chief_complaint="发烧",
            )

        # 4. 断言: status=generation_failed + fallback_reason=LLM_ERROR
        assert result.status == PrepStatus.generation_failed
        assert result.fallback_reason == FallbackReason.LLM_ERROR
        assert result.prompt_version_id == pv.id
        assert result.actual_cost_yuan == Decimal("0")
        assert call_count, "LLM 至少被调一次(monkeypatch 直接代替, retry 在装饰器内)"
        # budget 已 release (redis daily cost 应不超 0)
        guard = AIBudgetGuard(BudgetAxis.S3_PREP)
        spent = await guard.get_today_spent(redis)
        assert spent == Decimal("0")
