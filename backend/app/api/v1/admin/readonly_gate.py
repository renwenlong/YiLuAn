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
    request: Request,
    admin: CurrentAdmin,
    session: DBSession,
    store: ComplaintRateStoreDep,
) -> ComplaintRateResponse:
    """ADR-0053 §AC#4 entry."""
    # 1) record sample to redis (or in-proc fallback)
    try:
        await store.record_rate(payload.rate)
    except Exception as exc:  # noqa: BLE001 — redis 不可用时不阻 PM, 报 500
        logger.exception("[complaint_rate] record fail rate=%s err=%s", payload.rate, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="complaint_rate_record_failed",
        ) from exc

    # 2) AdminAuditLog 同事务写 (red line #1)
    # placeholder target_id (UUID) — 这里 audit 是 "PM 注入指标" 事件, 没具体 target
    # 用 admin 自己的 user_id 作 target_id, target_type='readonly_complaint_rate_sample'
    audit = AdminAuditLog(
        target_type="readonly_complaint_rate_sample",
        target_id=_CONFIG_TARGET,
        action="record",
        operator=str(admin.id),
        reason=(f"rate={payload.rate:.4f}%" + (f"; note={payload.note}" if payload.note else "")),
    )
    session.add(audit)
    await session.flush()
    await session.commit()

    # 3) read fresh rolling avg post-insert (best-effort, fail = None)
    rolling = None
    try:
        rolling = await store.get_rolling_average(window_days=7)
    except Exception:  # noqa: BLE001
        logger.warning(
            "[complaint_rate] rolling_avg read failed post-insert, "
            "returning recorded=True without average"
        )

    logger.info(
        "[complaint_rate] admin=%s recorded rate=%.4f%% rolling_7d=%s",
        admin.id,
        payload.rate,
        rolling,
    )

    return ComplaintRateResponse(
        recorded=True,
        rate=payload.rate,
        rolling_average_7d=rolling,
    )
