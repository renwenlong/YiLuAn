"""[S3-DEV-002-PREP-GENERATE-WITH-BUDGETGUARD / ADR-0048 §6 §8 P4]

Preparation package generate service
-------------------------------------

将 preparation_packages 从 ``status=pending`` 状态推到 ``status=active`` /
``status=active_fallback_template`` / ``status=generation_failed``.

调用链 (从 cron worker):

```
prep_generate_job (app/cron/prep_generate.py)
  └─ acquire scheduler-lock
  └─ for each pending PreparationPackage row:
       └─ acquire per-order Redis lock TTL 120s
       └─ PrepGenerateService.generate_for_order(order_id) ← 本模块
            ├─ L1 input filter (ai_prep_filter)         → block → fallback (L1_BLOCKED)
            ├─ AIBudgetGuard(S3_PREP).check_and_reserve  → REJECT → fallback (BUDGET_EXHAUSTED)
            ├─ deepseek_client.chat_completion (max 3 retries — 已由 outbound_call 装饰)
            │                                             → 3 retry fail → generation_failed (LLM_ERROR)
            ├─ L2 output filter                          → block → fallback (L2_BLOCKED)
            └─ report_actual_cost + write trace_id / prompt_version_id / costs / time_ms
       └─ release per-order Redis lock
```

ADR-0048 §6 全链路 trace_id 派生:
  - cron 启每 1 分钟扫一批 pending row → 每 order 一个 trace_id = uuid4()
  - 后续 admin trace 查询 / metric label 都用此 trace_id

AC mapping (S3-DEV-002-PREP-GENERATE-WITH-BUDGETGUARD):
  AC#1 (cron + lock)            → app/cron/prep_generate.py
  AC#2 (BudgetGuard 拦截)        → check_and_reserve REJECT → fallback path
  AC#3 (status 状态机)            → _persist_outcome 收 _GenerateOutcome
  AC#4 (DB 字段写)               → _persist_outcome
  AC#5 (4 路径集成测试)           → backend/tests/integration/test_prep_generate_with_budgetguard.py

LLM 调 fail 重试由 ``@outbound_call`` 装饰器(deepseek_client.chat_completion)
自动 ``max_retries=settings.deepseek_max_retries`` (默认 3) 处理.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.preparation_package import PrepStatus, PreparationPackage
from app.models.prompt_version import PromptVersion
from app.services.ai_budget_guard import (
    AIBudgetGuard,
    BudgetAxis,
    BudgetDecision,
)
from app.services.ai_prep_filter import AIPrepKeywordFilter
from app.services.ai_summary import deepseek_client as ds

logger = logging.getLogger("app.services.prep_generate")


# ─────────────────────────── fallback_reason enum ──────────────────────────

# 字符串常量(避免再起 enum, 与 model 字段 Mapped[str | None] 一致)
class FallbackReason:
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    L1_BLOCKED = "L1_BLOCKED"
    L2_BLOCKED = "L2_BLOCKED"
    LLM_ERROR = "LLM_ERROR"


# ─────────────────────────── fallback template ────────────────────────────

_FALLBACK_TEMPLATE_PATH = (
    Path(__file__).resolve().parents[3]
    / "docs"
    / "medical-content"
    / "prep-fallback-template.yml"
)

_fallback_cache: dict[str, Any] | None = None


def _load_fallback_template() -> dict[str, Any]:
    """加载并缓存 fallback template yml. 模块级缓存(进程生命期)."""
    global _fallback_cache
    if _fallback_cache is None:
        if not _FALLBACK_TEMPLATE_PATH.exists():
            raise PrepGenerateConfigError(
                f"fallback template not found: {_FALLBACK_TEMPLATE_PATH}"
            )
        with open(_FALLBACK_TEMPLATE_PATH, encoding="utf-8") as f:
            _fallback_cache = yaml.safe_load(f) or {}
    return _fallback_cache


def reset_fallback_cache() -> None:
    """测试 hook: 清缓存以重新加载 template (热更/test isolation)."""
    global _fallback_cache
    _fallback_cache = None


class PrepGenerateConfigError(Exception):
    """启动配置错误(template 缺 / active prompt 缺) — fail-fast."""


# ─────────────────────────── 内部数据结构 ──────────────────────────────────

@dataclass
class _GenerateOutcome:
    """generate_for_order 内部 outcome — _persist_outcome 转写 DB."""
    status: PrepStatus
    carry_items: list[str] = field(default_factory=list)
    pre_visit_notes: str | dict | None = None
    possible_questions: list[str] = field(default_factory=list)
    companion_focus_points: list[str] = field(default_factory=list)
    trace_id: str = ""
    prompt_version_id: uuid.UUID | None = None
    model: str | None = None
    estimated_cost_yuan: Decimal = Decimal("0")
    actual_cost_yuan: Decimal = Decimal("0")
    generation_time_ms: int = 0
    fallback_reason: str | None = None


# ─────────────────────────── PromptVersion 查询 ───────────────────────────

async def _get_active_prompt_version(
    session: AsyncSession,
) -> PromptVersion:
    """读 axis=s3_prep 当前 active prompt version. fail-fast if none."""
    stmt = select(PromptVersion).where(
        PromptVersion.axis == BudgetAxis.S3_PREP.value,
        PromptVersion.is_active.is_(True),
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise PrepGenerateConfigError(
            "no active PromptVersion for axis=s3_prep (run startup_validator)"
        )
    return row


# ─────────────────────────── fallback outcome builder ────────────────────

def _build_fallback_outcome(
    *,
    trace_id: str,
    prompt_version_id: uuid.UUID | None,
    model: str | None,
    estimated_cost_yuan: Decimal,
    fallback_reason: str,
    generation_time_ms: int,
) -> _GenerateOutcome:
    """从 fallback template 构造 outcome (status=active_fallback_template)."""
    tpl = _load_fallback_template()
    return _GenerateOutcome(
        status=PrepStatus.active_fallback_template,
        carry_items=list(tpl.get("carry_items") or []),
        pre_visit_notes=tpl.get("pre_visit_notes"),
        possible_questions=list(tpl.get("possible_questions") or []),
        companion_focus_points=list(tpl.get("companion_focus_points") or []),
        trace_id=trace_id,
        prompt_version_id=prompt_version_id,
        model=model,
        estimated_cost_yuan=estimated_cost_yuan,
        actual_cost_yuan=Decimal("0"),
        generation_time_ms=generation_time_ms,
        fallback_reason=fallback_reason,
    )


# ─────────────────────────── 持久化 ────────────────────────────────────────

async def _persist_outcome(
    session: AsyncSession,
    *,
    package: PreparationPackage,
    outcome: _GenerateOutcome,
) -> PreparationPackage:
    """单事务 commit. 状态 + 内容 + trace 元数据一次写完."""
    package.status = outcome.status
    package.carry_items = outcome.carry_items or None
    package.pre_visit_notes = outcome.pre_visit_notes
    package.possible_questions = outcome.possible_questions or None
    package.companion_focus_points = outcome.companion_focus_points or None
    package.trace_id = outcome.trace_id or None
    package.prompt_version_id = outcome.prompt_version_id
    package.model = outcome.model
    package.estimated_cost_yuan = outcome.estimated_cost_yuan
    package.actual_cost_yuan = outcome.actual_cost_yuan
    package.generation_time_ms = outcome.generation_time_ms
    package.fallback_reason = outcome.fallback_reason
    await session.commit()
    await session.refresh(package)
    return package


# ─────────────────────────── LLM 输出 → outcome 字段 ──────────────────────

def _parse_llm_output(content: str) -> dict[str, Any]:
    """LLM 返回内容应为 JSON, 包含 4 块 key. 解析失败抛 ValueError."""
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM output not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"LLM output not JSON object: {type(data).__name__}")
    return data


# ─────────────────────────── 主入口 ────────────────────────────────────────

async def generate_for_order(
    session: AsyncSession,
    redis,
    *,
    order_id: uuid.UUID,
    user_chief_complaint: str = "",
) -> PreparationPackage:
    """主入口: 把 pending PreparationPackage 推到 terminal 状态.

    返回 refreshed PreparationPackage row(测试 + cron 使用).

    Pre-condition:
      - PreparationPackage row 已存在 (status=pending), 由订单创建侧 insert.
      - cron 侧已确认本 row status=pending 且持有 per-order Redis lock.

    Side effects:
      - 写 AIBudgetGuard Redis daily cost key (axis=s3_prep)
      - 触发 metric: ai_prep_filter_l1/l2_blocked_total, AI_BUDGET_RESERVED_CNY_TOTAL
      - 单 commit 写 status + content + trace 元数据
    """
    trace_id = str(uuid.uuid4())
    started_ms = time.monotonic()

    # 1. 拿 pending row + lock=update (cron 侧已 Redis lock, 此处仅 read)
    stmt = select(PreparationPackage).where(
        PreparationPackage.order_id == order_id,
    )
    package = (await session.execute(stmt)).scalar_one_or_none()
    if package is None:
        raise PrepGenerateConfigError(
            f"PreparationPackage(order_id={order_id}) not found"
        )
    if package.status != PrepStatus.pending:
        # 已被处理(其他 worker 抢过 / 重试) — 幂等返
        logger.info(
            "prep.generate skip non-pending order_id=%s status=%s",
            order_id, package.status,
        )
        return package

    # 2. 翻 status=generating(可观测中间态; 失败 / 完成都会再翻)
    package.status = PrepStatus.generating
    await session.commit()

    # 3. 拿 active prompt version
    pv = await _get_active_prompt_version(session)

    # 4. L1 input filter(主诉中触发关键词 → 不调 LLM)
    keyword_filter = AIPrepKeywordFilter()
    if user_chief_complaint:
        l1 = keyword_filter.filter_input(user_chief_complaint)
        if l1.blocked:
            logger.info(
                "prep.generate L1 blocked order_id=%s trace_id=%s category=%s",
                order_id, trace_id, l1.category,
            )
            outcome = _build_fallback_outcome(
                trace_id=trace_id,
                prompt_version_id=pv.id,
                model=pv.model,
                estimated_cost_yuan=Decimal("0"),
                fallback_reason=FallbackReason.L1_BLOCKED,
                generation_time_ms=int((time.monotonic() - started_ms) * 1000),
            )
            return await _persist_outcome(session, package=package, outcome=outcome)

    # 5. AIBudgetGuard 预检 — 用 prompt 文本估 token 数粗算成本
    estimated_prompt_tokens = max(len(pv.prompt_text) // 2, 100)
    max_completion = pv.max_tokens or 1500
    estimated_cost = ds.estimate_cost_yuan(
        estimated_prompt_tokens, max_completion
    )

    guard = AIBudgetGuard(BudgetAxis.S3_PREP)
    check = await guard.check_and_reserve(
        redis,
        order_id=str(order_id),
        estimated_cost_yuan=estimated_cost,
    )
    if check.decision == BudgetDecision.REJECT:
        logger.info(
            "prep.generate budget REJECT order_id=%s trace_id=%s reason=%s",
            order_id, trace_id, check.reason,
        )
        outcome = _build_fallback_outcome(
            trace_id=trace_id,
            prompt_version_id=pv.id,
            model=pv.model,
            estimated_cost_yuan=estimated_cost,
            fallback_reason=FallbackReason.BUDGET_EXHAUSTED,
            generation_time_ms=int((time.monotonic() - started_ms) * 1000),
        )
        return await _persist_outcome(session, package=package, outcome=outcome)
    # ALLOW 或 FALLBACK(90-99% WARN) 都继续调 LLM(WARN 上层不强制 fallback,
    # 只 fire info alert — 与 S2 ai_summary 同语义)

    # 6. LLM 调用(@outbound_call 已内置 max 3 retries; 抛 RetryableError 重试结束 / 抛 NonRetryableError 立即失败)
    user_prompt = pv.prompt_text.format(
        chief_complaint=user_chief_complaint or "(未提供)"
    ) if "{chief_complaint}" in pv.prompt_text else (
        f"{pv.prompt_text}\n\n用户主诉:\n{user_chief_complaint or '(未提供)'}"
    )
    try:
        llm_result = await ds.chat_completion(
            prompt=user_prompt, max_tokens=max_completion,
        )
    except Exception as exc:
        # 3 次 retry 后仍 fail(或 NonRetryableError 立即 fail)
        await guard.release(
            redis,
            reservation_id=check.reservation_id,
            reserved_cost_yuan=estimated_cost,
        )
        logger.warning(
            "prep.generate LLM error order_id=%s trace_id=%s exc=%r",
            order_id, trace_id, exc,
        )
        # generation_failed(不走 fallback template — 留待后续 cron retry)
        outcome = _GenerateOutcome(
            status=PrepStatus.generation_failed,
            trace_id=trace_id,
            prompt_version_id=pv.id,
            model=pv.model,
            estimated_cost_yuan=estimated_cost,
            actual_cost_yuan=Decimal("0"),
            generation_time_ms=int((time.monotonic() - started_ms) * 1000),
            fallback_reason=FallbackReason.LLM_ERROR,
        )
        return await _persist_outcome(session, package=package, outcome=outcome)

    # 7. 上报实际成本(usage 差额 commit / refund)
    actual_cost = ds.estimate_cost_yuan(
        llm_result.prompt_tokens, llm_result.completion_tokens
    )
    await guard.report_actual_cost(
        redis,
        reservation_id=check.reservation_id,
        actual_cost_yuan=actual_cost,
        estimated_cost_yuan=estimated_cost,
    )

    # 8. L2 output filter(LLM 越界关键词 → fallback)
    l2 = keyword_filter.filter_output(llm_result.content)
    if l2.blocked:
        logger.info(
            "prep.generate L2 blocked order_id=%s trace_id=%s category=%s",
            order_id, trace_id, l2.category,
        )
        outcome = _build_fallback_outcome(
            trace_id=trace_id,
            prompt_version_id=pv.id,
            model=pv.model,
            estimated_cost_yuan=estimated_cost,
            fallback_reason=FallbackReason.L2_BLOCKED,
            generation_time_ms=int((time.monotonic() - started_ms) * 1000),
        )
        outcome.actual_cost_yuan = actual_cost
        return await _persist_outcome(session, package=package, outcome=outcome)

    # 9. 解析 LLM 输出 → 4 块字段
    try:
        parsed = _parse_llm_output(llm_result.content)
    except ValueError as exc:
        logger.warning(
            "prep.generate LLM output parse fail order_id=%s trace_id=%s exc=%s",
            order_id, trace_id, exc,
        )
        # JSON 解析失败按 L2_BLOCKED 同等处理: fallback 而非 generation_failed
        # (推因: 内容已生成 + 已扣费, 但解析失败属语义问题, 不走 retry)
        outcome = _build_fallback_outcome(
            trace_id=trace_id,
            prompt_version_id=pv.id,
            model=pv.model,
            estimated_cost_yuan=estimated_cost,
            fallback_reason=FallbackReason.L2_BLOCKED,
            generation_time_ms=int((time.monotonic() - started_ms) * 1000),
        )
        outcome.actual_cost_yuan = actual_cost
        return await _persist_outcome(session, package=package, outcome=outcome)

    # 10. happy: status=active + 写 4 块字段 + 全 trace 元数据
    outcome = _GenerateOutcome(
        status=PrepStatus.active,
        carry_items=list(parsed.get("carry_items") or []),
        pre_visit_notes=parsed.get("pre_visit_notes"),
        possible_questions=list(parsed.get("possible_questions") or []),
        companion_focus_points=list(parsed.get("companion_focus_points") or []),
        trace_id=trace_id,
        prompt_version_id=pv.id,
        model=llm_result.model,
        estimated_cost_yuan=estimated_cost,
        actual_cost_yuan=actual_cost,
        generation_time_ms=int((time.monotonic() - started_ms) * 1000),
        fallback_reason=None,
    )
    return await _persist_outcome(session, package=package, outcome=outcome)
