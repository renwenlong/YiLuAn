"""ADR-0053 §AC#4 — Read-only flag complaint rate manual injection endpoint.

POST /api/v1/admin/readonly/complaint-rate — PM weekly manual POST 注入
customer complaint rate sample, redis ZSET 7d sliding window. Cron gate
``check_readonly_flag_real_gate()`` 每日 02:00 UTC 读 rolling average.

design `S2-OPS-A-readonly-metric-dashboard.md` §5.3 r1 amend (黄线 #3):
客诉率 manual 注入, follow-up task `S3-OPS-CUSTOMER-SUPPORT-METRIC-INTEGRATION`
后接客服系统 API 自动化.

Auth: Depends(CurrentAdmin) — token-based, AdminAuditLog 同事务写
(避免 PR #250 cache-invalidate 反 pattern 事务分裂; ADR-0053 r4 amend §5.3).
"""

from __future__ import annotations

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.dependencies import CurrentAdmin, DBSession
from app.models.admin_audit_log import AdminAuditLog
from app.services.readonly_complaint_rate_store import (
    ComplaintRateStore,
    get_complaint_rate_store,
)

logger = logging.getLogger(__name__)

# Sentinel target_id for config-level audit rows (no specific entity target).
# Matches the pattern in ``app/api/v1/admin/ai_blocklist.py``.
_CONFIG_TARGET = UUID("00000000-0000-0000-0000-000000000000")

router = APIRouter(prefix="/readonly", tags=["admin", "readonly-gate"])


# ===========================================================================
# Schema
# ===========================================================================


class ComplaintRateRequest(BaseModel):
    """PM weekly manual POST body."""

    rate: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="Customer complaint rate as percent (0.0~100.0). "
        "Example 0.05 = 0.05% (5 complaints per 10000 sessions).",
        examples=[0.05],
    )
    note: str | None = Field(
        default=None,
        max_length=500,
        description="Optional PM 注入说明 (来源 / 周期 / 异常分析)",
    )


class ComplaintRateResponse(BaseModel):
    """Response after recording a sample."""

    recorded: bool
    rate: float
    rolling_average_7d: float | None = Field(
        default=None,
        description="Current 7-day rolling average after the new sample is added.",
    )


# ===========================================================================
# Dependency injector for ComplaintRateStore (test-friendly)
# ===========================================================================


def _get_complaint_rate_store_dep(request: Request) -> ComplaintRateStore:
    """Resolve store via app.state.redis when available, else in-proc fallback.

    test 可 override via ``app.dependency_overrides[_get_complaint_rate_store_dep]``.
    """
    redis_client = getattr(request.app.state, "redis", None)
    return get_complaint_rate_store(redis_client=redis_client)


ComplaintRateStoreDep = Annotated[ComplaintRateStore, Depends(_get_complaint_rate_store_dep)]


# ===========================================================================
# Helper (B1 魈 PR #308 r1 review suggestion — 拆出 pure logic, 便于
# 未来 webhook / scheduled inject 复用, 规约 #2 spirit)
# ===========================================================================


async def _apply_complaint_rate_sample(
    *,
    session: DBSession,
    admin_id: int,
    payload: ComplaintRateRequest,
    store: ComplaintRateStore,
) -> tuple[bool, float | None]:
    """Record sample + write AdminAuditLog 同事务 + return rolling avg.

    Pure logic, 不依 FastAPI Request 、 HTTPException. 未来 webhook /
    scheduled injector 可复用. 异常向上抛原型 (Endpoint 负责转 HTTP).

    Returns:
        (recorded, rolling_7d): rolling 取不到时 = None (best-effort)
    """
    # 1) record sample to redis (or in-proc fallback)
    await store.record_rate(payload.rate)

    # 2) AdminAuditLog 同事务写 (red line #1, PR #250 反 pattern escape)
    audit = AdminAuditLog(
        target_type="readonly_complaint_rate_sample",
        target_id=_CONFIG_TARGET,
        action="record",
        operator=str(admin_id),
        reason=(f"rate={payload.rate:.4f}%" + (f"; note={payload.note}" if payload.note else "")),
    )
    session.add(audit)
    await session.flush()
    await session.commit()

    # 3) read fresh rolling avg post-insert (best-effort, fail = None)
    rolling: float | None = None
    try:
        rolling = await store.get_rolling_average(window_days=7)
    except Exception:  # noqa: BLE001
        logger.warning(
            "[complaint_rate] rolling_avg read failed post-insert, "
            "returning recorded=True without average"
        )

    return True, rolling


# ===========================================================================
# Endpoint
# ===========================================================================


@router.post(
    "/complaint-rate",
    response_model=ComplaintRateResponse,
    status_code=status.HTTP_200_OK,
    summary="PM weekly manual 注入 customer complaint rate (ADR-0053 §AC#4)",
    description=(
        "PM 每周手动 POST 注入客诉率 sample, redis ZSET 7 天滑动窗口. "
        "Cron gate `check_readonly_flag_real_gate` 每日 02:00 UTC 读 rolling "
        "average 比 0.1% 阈值. "
        "AdminAuditLog 同事务写 (PR #250 反 pattern 已 escape)."
    ),
)
async def post_complaint_rate(
    payload: ComplaintRateRequest,
    request: Request,  # noqa: ARG001 - reserved for future request-scoped audit hook
    admin: CurrentAdmin,
    session: DBSession,
    store: ComplaintRateStoreDep,
) -> ComplaintRateResponse:
    """ADR-0053 §AC#4 entry. 薄 wrapper; pure logic 在 ``_apply_complaint_rate_sample``."""
    try:
        recorded, rolling = await _apply_complaint_rate_sample(
            session=session,
            admin_id=admin.id,
            payload=payload,
            store=store,
        )
    except Exception as exc:  # noqa: BLE001 — redis / db 不可用时报 500
        logger.exception("[complaint_rate] apply fail rate=%s err=%s", payload.rate, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="complaint_rate_record_failed",
        ) from exc

    logger.info(
        "[complaint_rate] admin=%s recorded rate=%.4f%% rolling_7d=%s",
        admin.id,
        payload.rate,
        rolling,
    )

    return ComplaintRateResponse(
        recorded=recorded,
        rate=payload.rate,
        rolling_average_7d=rolling,
    )
