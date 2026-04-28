"""[ADR-0032 / TD-MONEY-01 M3 / D-044 Q4] 资金对账 5 年保留清理 cron。

D-044 Q4 决议「分级保留」：
    - reconciliation_diffs: 5 年（监管 / 财务审计需求）
    - reconciliation_actions: 5 年（操作留痕）
    - reconciliation_runs: 永久（聚合元数据，体量小）

**M3 出口**：cron **只发现，不删除**。每周一 03:00 UTC 扫描超过 5 年的
``reconciliation_diffs`` 行，写 metric ``reconciliation_archive_candidates``，
并在日志里打出候选 ID 范围。真正的归档/删除等「D-044 Q4 第二阶段」拍板
后再落地（涉及 OSS NDJSON 归档 / 双跑 DR 演练）。

TODO（M3+）：
- 接入 OSS / S3 NDJSON 归档管道（参考 TD-OPS-02 的 payment_callback_log
  归档套路）。
- 加 ``--apply`` 命令行开关支持人工触发真删。
- 把"候选数"图表挂到 Grafana 资金对账看板。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from prometheus_client import REGISTRY, Gauge
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.reconciliation import (
    ReconciliationAction,
    ReconciliationDiff,
    ReconciliationRun,
)

logger = logging.getLogger(__name__)


# 5 years (D-044 Q4)
RETENTION_PERIOD = timedelta(days=365 * 5)


def _get_or_create_gauge(
    name: str, doc: str, labelnames: list[str]
) -> Gauge:
    existing = REGISTRY._names_to_collectors.get(name)  # type: ignore[attr-defined]
    if existing is not None:
        return existing  # type: ignore[return-value]
    return Gauge(name, doc, labelnames)


# Public metric — exposed so Grafana can chart "candidates accumulating
# despite no archive job".
RECON_ARCHIVE_CANDIDATES: Gauge = _get_or_create_gauge(
    "reconciliation_archive_candidates",
    "Number of reconciliation rows older than the 5-year retention "
    "window, awaiting archive (M3: discovery only).",
    ["table"],
)


@dataclass(frozen=True)
class CleanupReport:
    diffs_candidates: int
    actions_candidates: int
    runs_candidates: int
    cutoff: datetime


async def _count_old_rows(
    session: AsyncSession, *, cutoff: datetime
) -> CleanupReport:
    diffs_count = (
        await session.execute(
            select(func.count(ReconciliationDiff.id)).where(
                ReconciliationDiff.created_at < cutoff
            )
        )
    ).scalar() or 0

    actions_count = (
        await session.execute(
            select(func.count(ReconciliationAction.id)).where(
                ReconciliationAction.created_at < cutoff
            )
        )
    ).scalar() or 0

    # runs are kept forever per D-044 Q4, but report stat for visibility.
    runs_count = (
        await session.execute(
            select(func.count(ReconciliationRun.id)).where(
                ReconciliationRun.started_at < cutoff
            )
        )
    ).scalar() or 0

    return CleanupReport(
        diffs_candidates=int(diffs_count),
        actions_candidates=int(actions_count),
        runs_candidates=int(runs_count),
        cutoff=cutoff,
    )


async def discover_archive_candidates(
    *,
    now: datetime | None = None,
    session: AsyncSession | None = None,
) -> CleanupReport:
    """Discovery-only entry point. **Never deletes anything.**

    Updates Prometheus gauges and returns a structured report so callers
    can log / alert / unit-test against the result.
    """
    _now = now or datetime.now(timezone.utc)
    cutoff = _now - RETENTION_PERIOD

    if session is not None:
        report = await _count_old_rows(session, cutoff=cutoff)
    else:
        async with async_session() as s:
            report = await _count_old_rows(s, cutoff=cutoff)

    RECON_ARCHIVE_CANDIDATES.labels(table="reconciliation_diffs").set(
        report.diffs_candidates
    )
    RECON_ARCHIVE_CANDIDATES.labels(table="reconciliation_actions").set(
        report.actions_candidates
    )
    RECON_ARCHIVE_CANDIDATES.labels(table="reconciliation_runs").set(
        report.runs_candidates
    )

    logger.info(
        "reconciliation_cleanup discovery cutoff=%s diffs=%d actions=%d "
        "runs=%d (no rows deleted; D-044 Q4 archive pipeline pending)",
        cutoff.isoformat(),
        report.diffs_candidates,
        report.actions_candidates,
        report.runs_candidates,
    )
    return report


async def reconciliation_cleanup_job(app=None) -> dict:
    """APScheduler entry point: weekly Mon 03:00 UTC.

    Returns scheduler-friendly dict for logging.
    """
    report = await discover_archive_candidates()
    return {
        "status": "ok",
        "cutoff": report.cutoff.isoformat(),
        "diffs_candidates": report.diffs_candidates,
        "actions_candidates": report.actions_candidates,
        "runs_candidates": report.runs_candidates,
        "deleted": 0,  # M3: discovery only
    }


__all__ = [
    "RETENTION_PERIOD",
    "RECON_ARCHIVE_CANDIDATES",
    "CleanupReport",
    "discover_archive_candidates",
    "reconciliation_cleanup_job",
]
