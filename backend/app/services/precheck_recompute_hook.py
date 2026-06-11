"""Precheck recompute hook helper — S3-DEV-003 c5.

Centralises the 'after a contract / insurance / preparation /
companion verification status flip, recompute the precheck summary
and broadcast the new state to connected WS clients' pattern across
4 mutation sites so each call site stays a single import + one-line
helper invocation.

Design references
-----------------
- ``docs/design/S3-trust-precheck-ui.md`` §4.1 (4 信任卡 hook list)
- ADR-0048 §7.0 (ABAC defence-in-depth — hook never serialises
  business fields directly; passes through the Layer-1 schema)
- ADR-0051 r3 §1.2.3 dev mirror #6 (fail-loud in staging+, fail-open
  in dev)

Failure mode contract
---------------------
- Hook NEVER raises into the caller's transaction. Caller mutated
  business state successfully; the hook is best-effort downstream
  reaction. Failures are logged + swallowed.
- All hooks accept the **same** ``app`` handle the request scope has
  (or background-task injected) so the broker / facade can resolve.
- ``aggregator`` is constructed fresh per hook call (per-request
  scope) using the caller's session + Redis. Construction is cheap
  (two attribute assignments) so we do not memoise.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Sequence
from uuid import UUID

from app.services.order_precheck_aggregator import OrderPrecheckAggregator
from app.services.precheck_broadcast import (
    broadcast_all_ready,
    broadcast_blocked,
)

if TYPE_CHECKING:
    from fastapi import FastAPI
    from redis.asyncio import Redis
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Card identifiers used in the ``precheck.status.updated`` envelope.
# These mirror design/S3-trust-precheck-ui.md §4.1 and the
# aggregator card field keys.
CARD_CONTRACT = "contract"
CARD_INSURANCE = "insurance"
CARD_PREPARATION = "preparation"
CARD_COMPANION_CERT = "companion_cert"


async def trigger_precheck_recompute(
    *,
    app: "FastAPI",
    session: "AsyncSession",
    redis: "Redis",
    order_id: UUID,
    card: str,
) -> None:
    """Recompute the precheck summary for ``order_id`` and broadcast.

    Safe to call from inside or just after a transaction commit. The
    aggregator re-reads from the database, so reads after the caller's
    flush are guaranteed to see the new state.

    Failure mode: any exception is logged with structured context and
    swallowed. The caller's transaction is unaffected.

    Parameters
    ----------
    app
        FastAPI app handle (request.app, or app on a background task).
        Used to resolve the precheck broker.
    session
        Async SQLAlchemy session (re-used from the caller's request /
        task scope).
    redis
        Async Redis client.
    order_id
        The order whose 4-card summary should be recomputed.
    card
        Which card triggered the recompute (``contract`` /
        ``insurance`` / ``preparation`` / ``companion_cert``). Routed
        into the broadcast envelope for client-side targeting.
    """
    try:
        aggregator = OrderPrecheckAggregator(redis=redis, session=session, app=app)
        # invalidate_and_recompute performs DEL -> evaluate -> SET ->
        # internal _ws_broadcast. The internal broadcast publishes the
        # status.updated event keyed on the recomputed summary.
        #
        # We then perform the per-card envelope publish here so the
        # event carries the precise ``card`` identifier (the
        # aggregator's internal broadcast uses ``"summary"`` when the
        # caller did not pass cards_changed; we always do here for
        # better client routing).
        result = await aggregator.invalidate_and_recompute(
            order_id=order_id,
            cards=(card,),
        )
    except Exception:
        logger.exception(
            "precheck_recompute_hook.aggregator_failed",
            extra={"order_id": str(order_id), "card": card},
        )
        return

    # c6 dedup: consume the summary from orchestrator result.
    # invalidate_and_recompute already computed summary in step 2
    # and passed it to _ws_broadcast (step 4), so we reuse it here
    # for the secondary all_ready / blocked events instead of
    # calling evaluate() a third time.
    #
    # We do NOT re-issue status.updated here \u2014 aggregator._ws_broadcast
    # already did with the matching card identifier.
    summary = result.get("summary")
    if summary is None:
        # Defensive fallback: orchestrator should always include
        # summary (TypedDict contract), but if a future refactor
        # drops it, evaluate is still correct. Belt-and-suspenders.
        try:
            summary = await aggregator.evaluate(order_id)
        except Exception:
            logger.exception(
                "precheck_recompute_hook.fallback_evaluate_failed",
                extra={"order_id": str(order_id), "card": card},
            )
            return

    try:
        if summary.get("all_ready"):
            await broadcast_all_ready(app, order_id)
        else:
            blocked_reason = summary.get("blocked_reason")
            if blocked_reason:
                await broadcast_blocked(app, order_id, reason=blocked_reason)
    except Exception:
        logger.exception(
            "precheck_recompute_hook.secondary_event_failed",
            extra={"order_id": str(order_id), "card": card},
        )

    logger.debug(
        "precheck_recompute_hook.done",
        extra={
            "order_id": str(order_id),
            "card": card,
            "invalidated_keys": result.get("invalidated_keys"),
            "broadcast": result.get("broadcast"),
            "all_ready": summary.get("all_ready"),
        },
    )


async def trigger_precheck_recompute_for_orders(
    *,
    app: "FastAPI",
    session: "AsyncSession",
    redis: "Redis",
    order_ids: Sequence[UUID],
    card: str,
) -> None:
    """Fan-out version for hooks affecting multiple orders at once.

    Used by the companion verification hook: one admin approve flips a
    profile, which can invalidate dozens of in-flight orders (each
    ``order.companion_id`` matching). Fan-out is concurrent
    (``asyncio.gather``) with ``return_exceptions=True`` so a single
    order's recompute failure does not block the rest.

    Parameters
    ----------
    order_ids
        Sequence of order IDs to recompute. Empty sequence is a no-op.
    """
    if not order_ids:
        return

    coros = [
        trigger_precheck_recompute(
            app=app,
            session=session,
            redis=redis,
            order_id=oid,
            card=card,
        )
        for oid in order_ids
    ]
    results = await asyncio.gather(*coros, return_exceptions=True)

    # Per-coro errors are already logged inside trigger_precheck_recompute,
    # but the gather wrapper may still surface task-level exceptions
    # (cancelled etc.) \u2014 log a count summary for ops visibility.
    failures = [r for r in results if isinstance(r, BaseException)]
    if failures:
        logger.warning(
            "precheck_recompute_hook.fan_out_partial_failures",
            extra={
                "card": card,
                "order_count": len(order_ids),
                "failure_count": len(failures),
            },
        )


__all__ = [
    "CARD_COMPANION_CERT",
    "CARD_CONTRACT",
    "CARD_INSURANCE",
    "CARD_PREPARATION",
    "trigger_precheck_recompute",
    "trigger_precheck_recompute_for_orders",
]
