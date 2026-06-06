"""Insurance issuance compensation cron (S3-DEV-001-INSURANCE-DOMAIN / AC#3).

# 三档补偿 schedule (ADR-0046 §3.4 同款, ADR-0047 §3.3)

| Attempt # | After | Triggered by |
|-----------|-------|--------------|
| 1 | T+5min after issue_failed   | `compensate_5min_job`  |
| 2 | T+30min after 1st retry failed | `compensate_30min_job` |
| 3 | T+2h after 2nd retry failed | `compensate_2h_job`    |
| ≥4 | (no further retry)         | admin alert via alertmanager |

We implement the schedule as **three independent cron triggers** rather than
exponential-backoff-from-failure-time, because:

1. APScheduler interval triggers don't natively support per-row backoff
2. Polling all `issue_failed` rows every 5min is cheap (partial index)
3. ``retry_count`` field selects which "tier" each row is in:
   - retry_count=0 → eligible for 5min cron
   - retry_count=1 → eligible for 30min cron (after ≥30min since last retry)
   - retry_count=2 → eligible for 2h cron (after ≥2h since last retry)
   - retry_count=3 → permanently failed (admin alert, no further cron picks it)

The "after N min" guard is enforced by checking ``updated_at`` against
``now() - interval`` in the SELECT WHERE clause.

# Distributed lock (D-018 同款)

Each cron acquires a PG advisory lock (or Redis NX fallback) so multi-replica
deployments don't double-issue. Lock + business work share one AsyncSession
because PG advisory lock is per-connection.

# S3 阶段 vendor=PLACEHOLDER

S3 phase the vendor call is a stub returning success immediately. The
compensation cron is implemented in full so switching to a real vendor next
iter requires no scheduler changes — only the ``_issue_with_vendor`` helper.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.distributed_lock import acquire_scheduler_lock
from app.database import async_session
from app.models.service_insurance_record import (
    PLACEHOLDER_VENDOR_NAME,
    InsuranceStatus,
    ServiceInsuranceRecord,
)
from app.services.insurance_state_machine import (
    MAX_RETRY_COUNT,
    assert_transition_legal,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Cron schedule (interval in seconds + per-tier "min age" guard)
# ---------------------------------------------------------------------------


# How often each cron job runs (scheduler-side interval, NOT per-row delay).
TIER_1_INTERVAL_SECONDS = 5 * 60  # check eligible rows every 5 min
TIER_2_INTERVAL_SECONDS = 30 * 60  # check eligible rows every 30 min
TIER_3_INTERVAL_SECONDS = 2 * 60 * 60  # check eligible rows every 2 h

# Per-row "min age since updated_at" — gates retry pickup to enforce the
# 5min/30min/2h backoff between attempts for any single row.
TIER_1_MIN_AGE_SECONDS = 5 * 60
TIER_2_MIN_AGE_SECONDS = 30 * 60
TIER_3_MIN_AGE_SECONDS = 2 * 60 * 60


# Distributed lock keys (one per tier so tiers can progress in parallel
# across replicas, but each tier serializes within itself).
INSURANCE_CRON_TIER1_LOCK_KEY = "yiluan:scheduler:insurance-compensation:tier1"
INSURANCE_CRON_TIER2_LOCK_KEY = "yiluan:scheduler:insurance-compensation:tier2"
INSURANCE_CRON_TIER3_LOCK_KEY = "yiluan:scheduler:insurance-compensation:tier3"
INSURANCE_CRON_LOCK_TTL_SECONDS = 50  # Redis-fallback TTL only


# ---------------------------------------------------------------------------
# Vendor stub (S3 phase placeholder)
# ---------------------------------------------------------------------------


async def _issue_with_vendor(
    record: ServiceInsuranceRecord,
) -> tuple[bool, str | None]:
    """Stub: pretend to call vendor and succeed (S3 PLACEHOLDER_VENDOR phase).

    Returns ``(success, vendor_policy_no)``. Next iter replaces this with a
    real HTTP call to the insurance vendor API. The compensation cron does
    not care which vendor — only the success bool and policy_no string.
    """
    # S3: vendor is PLACEHOLDER, always succeeds; policy_no is deterministic.
    if record.vendor_name == PLACEHOLDER_VENDOR_NAME:
        short_id = str(record.order_id)[:8]
        return True, f"PLACEHOLDER-{short_id}"
    # Next-iter real-vendor branch goes here.
    return False, None


# ---------------------------------------------------------------------------
# Per-tier compensation logic
# ---------------------------------------------------------------------------


async def _retry_tier(
    *,
    tier: int,
    lock_key: str,
    min_age_seconds: int,
    app=None,
) -> dict:
    """Retry one tier of ``issue_failed`` rows whose retry_count matches.

    Args:
        tier: 1 / 2 / 3 — selects retry_count tier-1 (==0/1/2) eligibility
        lock_key: distributed lock key for this tier
        min_age_seconds: how long since updated_at before a row is eligible
        app: FastAPI app (for redis_client access in lock fallback)

    Returns ``{"status": "ok"|"skipped", "retried": int, "succeeded": int}``
    for test assertion + scheduler logging.
    """
    if tier not in (1, 2, 3):
        raise ValueError(f"tier must be 1/2/3, got {tier}")

    # retry_count value that makes a row eligible for THIS tier:
    # tier 1 → rows with retry_count=0 (first retry)
    # tier 2 → rows with retry_count=1 (second retry after first failed)
    # tier 3 → rows with retry_count=2 (third retry after second failed)
    eligible_retry_count = tier - 1

    redis_client = None
    if app is not None:
        redis_client = getattr(app.state, "redis", None)

    cutoff = datetime.now(timezone.utc) - timedelta(seconds=min_age_seconds)
    summary = {"status": "ok", "retried": 0, "succeeded": 0}

    try:
        async with async_session() as session:
            lock = acquire_scheduler_lock(
                session=session,
                redis_client=redis_client,
                key=lock_key,
                ttl=INSURANCE_CRON_LOCK_TTL_SECONDS,
            )
            async with lock:
                if not lock.acquired:
                    logger.debug(
                        "insurance_compensation.skipped_no_lock",
                        extra={"tier": tier},
                    )
                    return {"status": "skipped", "retried": 0, "succeeded": 0}

                # Pick eligible rows: failed + at correct retry tier + waited long enough
                stmt = (
                    select(ServiceInsuranceRecord)
                    .where(
                        ServiceInsuranceRecord.status == InsuranceStatus.issue_failed,
                        ServiceInsuranceRecord.retry_count == eligible_retry_count,
                        ServiceInsuranceRecord.updated_at <= cutoff,
                    )
                    .limit(100)  # batch cap; next cron tick picks the rest
                )
                result = await session.execute(stmt)
                rows = list(result.scalars())

                for record in rows:
                    summary["retried"] += 1
                    success, policy_no = await _issue_with_vendor(record)
                    if success:
                        # Guard: ensure transition is legal (defensive)
                        assert_transition_legal(record.status, InsuranceStatus.active)
                        record.status = InsuranceStatus.active
                        record.vendor_policy_no = policy_no
                        record.issued_at = datetime.now(timezone.utc)
                        record.failure_reason = None
                        summary["succeeded"] += 1
                        logger.info(
                            "insurance_compensation.retry_succeeded",
                            extra={
                                "tier": tier,
                                "insurance_id": str(record.id),
                                "order_id": str(record.order_id),
                            },
                        )
                    else:
                        # Bump retry_count; if it reaches MAX, the row stays
                        # in issue_failed but no further tier will pick it
                        # (no tier matches retry_count=3).
                        record.retry_count += 1
                        record.failure_reason = f"vendor returned failure on tier-{tier} retry"
                        logger.warning(
                            "insurance_compensation.retry_failed",
                            extra={
                                "tier": tier,
                                "insurance_id": str(record.id),
                                "retry_count": record.retry_count,
                                "permanently_failed": record.retry_count >= MAX_RETRY_COUNT,
                            },
                        )

                await session.commit()
                return summary

    except Exception:
        logger.exception("insurance_compensation.cron_error", extra={"tier": tier})
        return {"status": "error", "retried": summary["retried"], "succeeded": 0}


async def compensate_tier_1_job(app=None) -> dict:
    """Retry insurance issuance for rows in issue_failed with retry_count=0.

    Eligibility: updated_at ≤ now - 5min.
    """
    return await _retry_tier(
        tier=1,
        lock_key=INSURANCE_CRON_TIER1_LOCK_KEY,
        min_age_seconds=TIER_1_MIN_AGE_SECONDS,
        app=app,
    )


async def compensate_tier_2_job(app=None) -> dict:
    """Retry tier 2: retry_count=1, updated_at ≤ now - 30min."""
    return await _retry_tier(
        tier=2,
        lock_key=INSURANCE_CRON_TIER2_LOCK_KEY,
        min_age_seconds=TIER_2_MIN_AGE_SECONDS,
        app=app,
    )


async def compensate_tier_3_job(app=None) -> dict:
    """Retry tier 3: retry_count=2, updated_at ≤ now - 2h."""
    return await _retry_tier(
        tier=3,
        lock_key=INSURANCE_CRON_TIER3_LOCK_KEY,
        min_age_seconds=TIER_3_MIN_AGE_SECONDS,
        app=app,
    )


__all__ = [
    "INSURANCE_CRON_LOCK_TTL_SECONDS",
    "INSURANCE_CRON_TIER1_LOCK_KEY",
    "INSURANCE_CRON_TIER2_LOCK_KEY",
    "INSURANCE_CRON_TIER3_LOCK_KEY",
    "TIER_1_INTERVAL_SECONDS",
    "TIER_1_MIN_AGE_SECONDS",
    "TIER_2_INTERVAL_SECONDS",
    "TIER_2_MIN_AGE_SECONDS",
    "TIER_3_INTERVAL_SECONDS",
    "TIER_3_MIN_AGE_SECONDS",
    "compensate_tier_1_job",
    "compensate_tier_2_job",
    "compensate_tier_3_job",
]
