"""[S2-DEV-005] AI summary orchestrator.

Pipeline
--------
1. **Budget gate**: pre-check daily cap (Redis ``incrbyfloat`` reserve);
   on ``BudgetExhausted`` → write degraded template + return.
2. **Per-order cap**: compute ``max_tokens`` so worst-case cost ≤ ¥0.05;
   if prompt alone exceeds the cap → degrade with reason
   ``per_order_truncated``.
3. **LLM call**: ``deepseek_client.chat_completion``. RetryableError /
   circuit open → degrade with the matching reason + release budget.
4. **Post-check**: blocklist match → degrade ``post_check_blocked``.
5. **Persist**: upsert ``AIDigest`` row (unique on ``order_id``); commit
   the actual cost so the daily counter ends at ground truth.
6. **Metrics**: ``ai_summary_cost_cny_total`` += actual cost,
   ``ai_summary_degraded_total{reason}`` or
   ``ai_summary_generated_total{status}``.

Failure surface
---------------
Anything unexpected → ``ai_summary_generated_total{status="failed"}`` +
``dead_letter`` row + ``status=FAILED`` in DB. Never re-raises into the
caller (this is a best-effort background job; order flow must not block).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Final
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.ai_digest import AIDigest, AIDigestStatus
from app.observability.ai_summary_metrics import (
    AI_SUMMARY_COST_CNY_TOTAL,
    AI_SUMMARY_DEGRADED_TOTAL,
    AI_SUMMARY_GENERATED_TOTAL,
)
from app.services.ai_summary import budget as ai_budget
from app.services.ai_summary import deepseek_client as ds
from app.services.ai_summary.post_check import (
    BlocklistChecker,
    get_default_checker,
)
from app.services.dead_letter import record_dead_letter
from app.utils.outbound import RetryableError

logger = logging.getLogger("app.services.ai_summary.digester")

DEGRADED_TEMPLATE: Final[str] = "今日就诊已结束，详情可咨询陪诊师"
SYSTEM_PROMPT: Final[str] = (
    "你是医疗陪诊摘要助手。请用 80 字以内的中文，向患者家属客观汇报本次"
    "就诊过程：何时到院、做了什么检查、医生主要交代什么。**不要给出诊断、"
    "用药建议或紧急程度判断**——这是医师的职责，不是你的。"
)


@dataclass(frozen=True)
class DigestOutcome:
    status: AIDigestStatus
    summary: str
    cost_yuan: Decimal
    degraded_reason: str | None
    model: str | None


async def generate_digest(
    *,
    session: AsyncSession,
    redis,
    order_id: UUID,
    prompt: str,
    checker: BlocklistChecker | None = None,
    now: datetime | None = None,
) -> DigestOutcome:
    """Run the full pipeline for a single order. Never raises."""
    checker = checker or get_default_checker()
    now = now or datetime.now(timezone.utc)
    per_order_cap = Decimal(str(settings.ai_per_order_budget_yuan))

    # ---- Step 1: per-order budget → bound max_tokens
    # Rough prompt-token estimate: 1 token ≈ 1.7 Chinese chars (conservative
    # over-estimate keeps us under budget when actual tokenization wins).
    estimated_prompt_tokens = max(1, int(len(prompt) / 1.5) + len(SYSTEM_PROMPT))
    max_completion = ds.estimate_max_completion_tokens_for_budget(
        estimated_prompt_tokens, per_order_cap
    )
    if max_completion == 0:
        return await _degrade(
            session=session,
            redis=redis,
            order_id=order_id,
            reason="per_order_truncated",
            reserved=Decimal("0"),
            now=now,
        )

    # ---- Step 2: daily budget gate (reserve estimated worst-case cost)
    estimated_worst = ds.estimate_cost_yuan(
        estimated_prompt_tokens, max_completion
    )
    try:
        await ai_budget.check_and_reserve(redis, estimated_worst, now=now)
    except ai_budget.BudgetExhausted:
        return await _degrade(
            session=session,
            redis=redis,
            order_id=order_id,
            reason="daily_budget",
            reserved=Decimal("0"),
            now=now,
        )

    # ---- Step 3: LLM call
    try:
        result = await ds.chat_completion(
            prompt=prompt, max_tokens=max_completion, system=SYSTEM_PROMPT
        )
    except RetryableError as exc:
        await ai_budget.release(redis, estimated_worst, now=now)
        reason = (
            "circuit_open"
            if "Circuit breaker open" in str(exc)
            else "provider_timeout"
        )
        return await _degrade(
            session=session,
            redis=redis,
            order_id=order_id,
            reason=reason,
            reserved=Decimal("0"),
            now=now,
        )
    except Exception as exc:  # NonRetryable or anything truly unexpected
        await ai_budget.release(redis, estimated_worst, now=now)
        await _record_failure(session, order_id, exc)
        return DigestOutcome(
            status=AIDigestStatus.FAILED,
            summary="",
            cost_yuan=Decimal("0"),
            degraded_reason="provider_failed",
            model=None,
        )

    # ---- Step 4: post-check
    check = checker.check(result.content)
    if check.blocked:
        await ai_budget.commit(redis, result.cost_yuan, estimated_worst, now=now)
        return await _persist_and_metric(
            session=session,
            order_id=order_id,
            status=AIDigestStatus.DEGRADED,
            summary=DEGRADED_TEMPLATE,
            cost_yuan=result.cost_yuan,
            model=result.model,
            degraded_reason="post_check_blocked",
        )

    # ---- Step 5: success path (or truncated → still degraded)
    await ai_budget.commit(redis, result.cost_yuan, estimated_worst, now=now)
    if result.truncated:
        return await _persist_and_metric(
            session=session,
            order_id=order_id,
            status=AIDigestStatus.DEGRADED,
            summary=result.content or DEGRADED_TEMPLATE,
            cost_yuan=result.cost_yuan,
            model=result.model,
            degraded_reason="per_order_truncated",
        )

    return await _persist_and_metric(
        session=session,
        order_id=order_id,
        status=AIDigestStatus.OK,
        summary=result.content,
        cost_yuan=result.cost_yuan,
        model=result.model,
        degraded_reason=None,
    )


# ---------------------------------------------------------------------------
# helpers


async def _degrade(
    *,
    session: AsyncSession,
    redis,
    order_id: UUID,
    reason: str,
    reserved: Decimal,
    now: datetime,
) -> DigestOutcome:
    if reserved > 0:
        await ai_budget.release(redis, reserved, now=now)
    return await _persist_and_metric(
        session=session,
        order_id=order_id,
        status=AIDigestStatus.DEGRADED,
        summary=DEGRADED_TEMPLATE,
        cost_yuan=Decimal("0"),
        model=None,
        degraded_reason=reason,
    )


async def _persist_and_metric(
    *,
    session: AsyncSession,
    order_id: UUID,
    status: AIDigestStatus,
    summary: str,
    cost_yuan: Decimal,
    model: str | None,
    degraded_reason: str | None,
) -> DigestOutcome:
    existing = (
        await session.execute(select(AIDigest).where(AIDigest.order_id == order_id))
    ).scalar_one_or_none()
    if existing is None:
        row = AIDigest(
            order_id=order_id,
            status=status,
            summary=summary,
            model=model,
            cost_yuan=cost_yuan,
            degraded_reason=degraded_reason,
        )
        session.add(row)
    else:
        existing.status = status
        existing.summary = summary
        existing.model = model
        existing.cost_yuan = cost_yuan
        existing.degraded_reason = degraded_reason
    await session.commit()

    if cost_yuan > 0 and model:
        AI_SUMMARY_COST_CNY_TOTAL.labels(model=model).inc(float(cost_yuan))
    if status == AIDigestStatus.DEGRADED and degraded_reason:
        AI_SUMMARY_DEGRADED_TOTAL.labels(reason=degraded_reason).inc()
    AI_SUMMARY_GENERATED_TOTAL.labels(status=status.value).inc()

    return DigestOutcome(
        status=status,
        summary=summary,
        cost_yuan=cost_yuan,
        degraded_reason=degraded_reason,
        model=model,
    )


async def _record_failure(session: AsyncSession, order_id: UUID, exc: Exception) -> None:
    AI_SUMMARY_GENERATED_TOTAL.labels(status="failed").inc()
    try:
        await record_dead_letter(
            session=session,
            channel="ai_summary",
            reason="ai_summary_generate_failed",
            target_type="order",
            target_id=order_id,
            payload={"order_id": str(order_id), "error": str(exc)},
        )
    except Exception as inner:
        logger.error("ai_summary dead_letter record failed: %s", inner)
    # Persist a FAILED row so the gallery query doesn't keep hammering us.
    existing = (
        await session.execute(select(AIDigest).where(AIDigest.order_id == order_id))
    ).scalar_one_or_none()
    if existing is None:
        session.add(
            AIDigest(
                order_id=order_id,
                status=AIDigestStatus.FAILED,
                summary=None,
                degraded_reason="provider_failed",
                cost_yuan=Decimal("0"),
            )
        )
    else:
        existing.status = AIDigestStatus.FAILED
        existing.degraded_reason = "provider_failed"
    await session.commit()


__all__ = ["DEGRADED_TEMPLATE", "DigestOutcome", "generate_digest"]
