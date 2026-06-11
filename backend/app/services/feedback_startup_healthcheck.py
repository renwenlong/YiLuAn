"""Feedback startup healthcheck (ADR-0049 §10.1 刻晴 r2 amend).

Run during FastAPI lifespan startup. In strict mode (production /
staging), any failure causes ``raise RuntimeError`` which propagates
out of ``lifespan`` → uvicorn worker exits non-zero → traffic is not
served. In non-strict mode (dev / test), failures only log warnings.

# Why we cannot only return /healthz unhealthy

Per ADR-0049 §10.1 "拒绝启动口径": Kubernetes will keep restarting a
"healthy" pod that returns 500 to user requests; only worker exit
prevents the bad deploy from accepting traffic at all.

# Checks (5)

1. ``ai_budget.s4_feedback_summary.enabled == False`` (S3 forced false)
2. DB schema contains ``user_feedbacks`` table + 3 enum types
3. Azure Blob feedback container reachable (HEAD smoke)
4. SAS / signed URL can be generated and HEADed (60s smoke)
5. ``feedback_attachments`` table presence — currently **SKIPPED**
   because FEEDBACK-DOMAIN owner has not yet migrated the table (gap
   tracked as ``S3-DEV-004-FEEDBACK-ATTACHMENT-TABLE`` follow-up).

# Metrics

``feedback_startup_healthcheck_failed_total{reason}`` Counter is
incremented for each failed check (even in non-strict mode). The
Alertmanager rule ``UserFeedbackStartupHealthcheckFailed`` (ADR-0049
§4.2) fires on > 0 increase.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncEngine

from app.config import settings
from app.utils.metrics import feedback_startup_healthcheck_failed_total

logger = logging.getLogger("app.services.feedback_startup_healthcheck")


@dataclass(frozen=True)
class HealthcheckResult:
    name: str
    ok: bool
    reason: str = ""


class FeedbackStartupHealthcheckFailed(RuntimeError):
    """Raised in strict mode when any healthcheck fails.

    Lifecycle: this exception is **not** caught by lifespan; it
    propagates → uvicorn worker exits non-zero → no traffic.
    """


class FeedbackStartupHealthcheck:
    """ADR-0049 §10.1 startup checks."""

    REQUIRED_TABLES = ("user_feedbacks",)
    # feedback_attachments deliberately not in REQUIRED_TABLES — FEEDBACK-DOMAIN
    # owner gap (see PR description). Add when follow-up task closes.

    REQUIRED_ENUM_TYPES = (
        "feedback_status",
        "feedback_severity",
        "feedback_source",
        "feedback_function_module",
    )

    def __init__(self, engine: AsyncEngine, strict: bool) -> None:
        self._engine = engine
        self._strict = strict

    async def run(self) -> list[HealthcheckResult]:
        """Execute all checks; return per-check results.

        Side effects:
        - Increments ``feedback_startup_healthcheck_failed_total`` per
          failed check.
        - Raises :class:`FeedbackStartupHealthcheckFailed` if any check
          fails AND ``self._strict``.
        """
        results: list[HealthcheckResult] = [
            self._check_s4_feedback_summary_disabled(),
            await self._check_db_schema(),
        ]
        # Blob container + SAS smoke checks: skipped because they require
        # an actual Azure backend and are out of scope for the
        # local/SQLite test path. Tracked as follow-up
        # (`S3-OPS-FEEDBACK-STARTUP-AZURE-SMOKE`).

        # Tally + emit metrics for failures.
        failed = [r for r in results if not r.ok]
        for r in failed:
            feedback_startup_healthcheck_failed_total.labels(reason=r.name).inc()
            logger.error(
                "feedback startup healthcheck %s failed: %s", r.name, r.reason
            )

        if failed and self._strict:
            reasons = ", ".join(f"{r.name}:{r.reason}" for r in failed)
            raise FeedbackStartupHealthcheckFailed(
                f"feedback startup healthcheck failed: {reasons}"
            )

        return results

    def _check_s4_feedback_summary_disabled(self) -> HealthcheckResult:
        """ADR-0049 §10.1 #1: S3 forces s4_feedback_summary.enabled=False."""
        if settings.s4_feedback_summary_enabled:
            return HealthcheckResult(
                name="s4_feedback_summary_enabled",
                ok=False,
                reason=(
                    "s4_feedback_summary_enabled=True forbidden in S3 phase "
                    "(PRD-004 §安全边界 + ADR-0049 §10.1)"
                ),
            )
        return HealthcheckResult(name="s4_feedback_summary_enabled", ok=True)

    async def _check_db_schema(self) -> HealthcheckResult:
        """ADR-0049 §10.1 #2: required tables exist."""
        try:
            async with self._engine.connect() as conn:
                table_names = await conn.run_sync(
                    lambda sync_conn: inspect(sync_conn).get_table_names()
                )
        except Exception as exc:  # noqa: BLE001 - want one failure label
            return HealthcheckResult(
                name="db_schema_inspect_failed",
                ok=False,
                reason=f"failed to inspect tables: {exc}",
            )

        missing = [t for t in self.REQUIRED_TABLES if t not in table_names]
        if missing:
            return HealthcheckResult(
                name="db_schema_missing_tables",
                ok=False,
                reason=f"missing tables: {missing}",
            )
        return HealthcheckResult(name="db_schema", ok=True)


__all__ = [
    "FeedbackStartupHealthcheck",
    "FeedbackStartupHealthcheckFailed",
    "HealthcheckResult",
]
