"""Admin Dashboard — at-a-glance KPI cards + recent trends (A).

Routes: /api/v1/admin/dashboard
Auth: same double-track admin (JWT preferred, legacy X-Admin-Token works).

Endpoints
---------
GET /summary
    Today's headline numbers plus a 7-day order count trend so the
    dashboard page can render 4 cards + 1 sparkline without N round-trips.

All counts use single aggregate queries (no per-row scans) and cap the
time window so this endpoint stays cheap to poll.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select

from app.core.admin_jwt import require_admin
from app.dependencies import DBSession
from app.models.companion_profile import CompanionProfile, VerificationStatus
from app.models.order import Order, OrderStatus, PaymentState, RefundState
from app.models.reconciliation import ReconciliationDiff, ReconDiffStatus
from app.models.user import User

router = APIRouter(
    prefix="/dashboard",
    tags=["admin-dashboard"],
    dependencies=[Depends(require_admin)],
)


class DashboardCard(BaseModel):
    today_order_count: int
    today_gmv: Decimal
    pending_companion_verifications: int
    open_reconciliation_diffs: int
    refund_pending_orders: int
    active_users_7d: int


class TrendPoint(BaseModel):
    date: str  # YYYY-MM-DD
    orders: int
    gmv: Decimal


class DashboardSummary(BaseModel):
    cards: DashboardCard
    trend_7d: list[TrendPoint]
    generated_at: datetime


def _today_window_utc() -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, now


@router.get(
    "/summary",
    response_model=DashboardSummary,
    summary="后台首页：KPI + 7 日趋势",
)
async def get_summary(session: DBSession) -> DashboardSummary:
    today_start, _ = _today_window_utc()

    today_count_q = select(func.count(Order.id)).where(
        Order.created_at >= today_start
    )
    today_gmv_q = select(func.coalesce(func.sum(Order.price), 0)).where(
        Order.created_at >= today_start,
        Order.payment_state == PaymentState.paid,
    )
    pending_companions_q = select(func.count(CompanionProfile.id)).where(
        CompanionProfile.verification_status == VerificationStatus.pending
    )
    open_diffs_q = select(func.count(ReconciliationDiff.id)).where(
        ReconciliationDiff.status.in_(
            [ReconDiffStatus.pending, ReconDiffStatus.mismatched]
        )
    )
    refund_pending_q = select(func.count(Order.id)).where(
        Order.refund_state.in_([RefundState.refunding, RefundState.manual_review])
    )
    active_users_q = select(func.count(User.id)).where(
        User.is_active.is_(True),
        User.created_at >= today_start - timedelta(days=7),
    )

    today_count = (await session.execute(today_count_q)).scalar_one()
    today_gmv = (await session.execute(today_gmv_q)).scalar_one()
    pending_companions = (await session.execute(pending_companions_q)).scalar_one()
    open_diffs = (await session.execute(open_diffs_q)).scalar_one()
    refund_pending = (await session.execute(refund_pending_q)).scalar_one()
    active_users = (await session.execute(active_users_q)).scalar_one()

    # 7-day trend: bucket by UTC date. Two single-statement aggregates,
    # then merge in Python to fill empty days.
    seven_days_ago = today_start - timedelta(days=6)
    bucket = func.date(Order.created_at).label("d")
    trend_count_q = (
        select(bucket, func.count(Order.id))
        .where(Order.created_at >= seven_days_ago)
        .group_by(bucket)
    )
    trend_gmv_q = (
        select(bucket, func.coalesce(func.sum(Order.price), 0))
        .where(
            Order.created_at >= seven_days_ago,
            Order.payment_state == PaymentState.paid,
        )
        .group_by(bucket)
    )

    counts = {str(d): c for d, c in (await session.execute(trend_count_q)).all()}
    gmvs = {str(d): g for d, g in (await session.execute(trend_gmv_q)).all()}

    today_date = today_start.date()
    trend: list[TrendPoint] = []
    for i in range(6, -1, -1):
        d = today_date - timedelta(days=i)
        key = d.isoformat()
        trend.append(
            TrendPoint(
                date=key,
                orders=int(counts.get(key, 0)),
                gmv=Decimal(gmvs.get(key, 0)),
            )
        )

    return DashboardSummary(
        cards=DashboardCard(
            today_order_count=int(today_count),
            today_gmv=Decimal(today_gmv),
            pending_companion_verifications=int(pending_companions),
            open_reconciliation_diffs=int(open_diffs),
            refund_pending_orders=int(refund_pending),
            active_users_7d=int(active_users),
        ),
        trend_7d=trend,
        generated_at=datetime.now(timezone.utc),
    )
