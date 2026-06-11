"""Feedback endpoint rate limiter (ADR-0049 §3.2.1, 阻塞 #2 修复).

# Why redis-backed sliding window

ADR-0049 §3.2.1 defines per-user quotas across 1h and 24h windows:

| Endpoint | Hourly | Daily |
|----------|--------|-------|
| POST /users/feedbacks | 10 | 50 |
| POST /users/feedbacks/{parent}/append | 30 | 100 |
| POST /admin/feedbacks | 60 | — (admin) |

A true token bucket needs per-tenant state across replicas → redis
SETNX + EXPIRE pattern. We mirror ``providers/sms/rate_limit.py``
style (sliding window with redis backend, in-process fallback for
unit tests + single-worker dev).

# Why FastAPI Depends (not middleware)

Each endpoint has a distinct quota and different key derivation
(``user_id`` for user endpoints; ``admin_id`` for admin endpoint).
Middleware would force a path-based switch which leaks the routing
contract into infrastructure code. Depends keeps the limiter pluggable
per endpoint with explicit DI of the user/admin entity.

# Why per-endpoint factory (not generic instance)

``_FeedbackRateLimit`` is a stateful callable bound to specific
(endpoint_name, hourly_cap, daily_cap, key_source) at module import
time, so OpenAPI / dependency-overrides see them as distinct ``Depends``
nodes. Three module-level singletons:

- ``feedback_submit_ratelimit`` — POST /users/feedbacks (10/h + 50/d)
- ``feedback_append_ratelimit`` — POST /users/feedbacks/{parent}/append (30/h + 100/d)
- ``feedback_admin_create_ratelimit`` — POST /admin/feedbacks (60/h)

# Counter integration

Every 429 response **must** bump
``feedback_ratelimit_429_total{user_id, endpoint}`` (ADR-0049 §4.2).
Done inline before raising HTTPException.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, status
from redis.asyncio import Redis

from app.core.redis import get_redis
from app.dependencies import CurrentAdmin, CurrentUser
from app.utils.metrics import feedback_ratelimit_429_total

logger = logging.getLogger("app.api.v1.feedback_ratelimit")

# In-process fallback store: {redis_key: [unix_ts, unix_ts, ...]}.
# Module-level so pytest can clear in fixtures.
_INPROC_STORE: dict[str, list[float]] = {}


@dataclass(frozen=True)
class _LimitConfig:
    endpoint_name: str
    hourly: int
    daily: int  # 0 == no daily cap


# ADR-0049 §3.2.1 quotas (frozen, change → ADR amend → review).
_SUBMIT_LIMITS = _LimitConfig(
    endpoint_name="users_feedbacks_submit",
    hourly=10,
    daily=50,
)
_APPEND_LIMITS = _LimitConfig(
    endpoint_name="users_feedbacks_append",
    hourly=30,
    daily=100,
)
_ADMIN_CREATE_LIMITS = _LimitConfig(
    endpoint_name="admin_feedbacks_create",
    hourly=60,
    daily=0,  # admin endpoint not daily-capped per ADR
)


async def _check_window(
    *,
    redis: Redis | None,
    actor_key: str,
    endpoint_name: str,
    window_seconds: int,
    limit: int,
    now: float,
) -> tuple[bool, int]:
    """Return (allowed, retry_after_seconds).

    Sliding window: read all timestamps for this (actor, endpoint, window)
    bucket; drop expired; deny if remaining ≥ limit. On accept, record
    a new timestamp with TTL = window_seconds.
    """
    redis_key = f"ratelimit:feedback:{endpoint_name}:{actor_key}:{window_seconds}"
    cutoff = now - window_seconds

    if redis is not None:
        # Redis path: use a Lua-like sequence via ZSET (score=ts).
        # NOTE: use numeric 0 as low bound (not "-inf" string) for
        # compatibility with in-test mock redis fixtures that don't
        # implement string-encoded score range.
        pipe = redis.pipeline()
        pipe.zremrangebyscore(redis_key, 0, cutoff)
        pipe.zcard(redis_key)
        _, current = await pipe.execute()
        current = int(current or 0)
        if current >= limit:
            # Worst-case retry_after = full window (a hash-redis fallback
            # without zrange returns full window; production redis path
            # would use ``zrange(0,0,withscores=True)`` for precise hint).
            retry_after = window_seconds
            if hasattr(redis, "zrange"):
                try:
                    earliest = await redis.zrange(
                        redis_key, 0, 0, withscores=True
                    )
                    if earliest:
                        _, earliest_ts = earliest[0]
                        retry_after = max(
                            1, int((earliest_ts + window_seconds) - now)
                        )
                except Exception:
                    # Mock redis without ZSET support — keep worst-case hint.
                    retry_after = window_seconds
            return False, retry_after
        await redis.zadd(redis_key, {str(now): now})
        await redis.expire(redis_key, window_seconds)
        return True, 0

    # In-process fallback (tests / single-worker dev).
    bucket = _INPROC_STORE.setdefault(redis_key, [])
    # Drop expired in place.
    bucket[:] = [t for t in bucket if t > cutoff]
    if len(bucket) >= limit:
        earliest_ts = bucket[0]
        retry_after = max(1, int((earliest_ts + window_seconds) - now))
        return False, retry_after
    bucket.append(now)
    return True, 0


async def _enforce(
    *,
    redis: Redis | None,
    actor_key: str,
    config: _LimitConfig,
) -> None:
    """Run hourly+daily check; raise 429 + Retry-After on first hit."""
    now = time.time()

    allowed, retry_after = await _check_window(
        redis=redis,
        actor_key=actor_key,
        endpoint_name=config.endpoint_name,
        window_seconds=3600,
        limit=config.hourly,
        now=now,
    )
    if not allowed:
        feedback_ratelimit_429_total.labels(
            user_id=actor_key,
            endpoint=config.endpoint_name,
        ).inc()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"feedback_ratelimit_hourly: {config.hourly}/h exceeded; "
                f"retry after {retry_after}s"
            ),
            headers={"Retry-After": str(retry_after)},
        )

    if config.daily > 0:
        allowed, retry_after = await _check_window(
            redis=redis,
            actor_key=actor_key,
            endpoint_name=config.endpoint_name,
            window_seconds=86400,
            limit=config.daily,
            now=now,
        )
        if not allowed:
            feedback_ratelimit_429_total.labels(
                user_id=actor_key,
                endpoint=config.endpoint_name,
            ).inc()
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"feedback_ratelimit_daily: {config.daily}/d exceeded; "
                    f"retry after {retry_after}s"
                ),
                headers={"Retry-After": str(retry_after)},
            )


# ---------------------------------------------------------------------------
# Public FastAPI dependencies
# ---------------------------------------------------------------------------


async def feedback_submit_ratelimit(
    current_user: CurrentUser,
    redis: Annotated[Redis | None, Depends(get_redis)] = None,
) -> None:
    """ADR-0049 §3.2.1: POST /users/feedbacks → 10/h + 50/d per user."""
    await _enforce(
        redis=redis,
        actor_key=str(current_user.id),
        config=_SUBMIT_LIMITS,
    )


async def feedback_append_ratelimit(
    current_user: CurrentUser,
    redis: Annotated[Redis | None, Depends(get_redis)] = None,
) -> None:
    """ADR-0049 §3.2.1: POST /users/feedbacks/{parent}/append → 30/h + 100/d per user."""
    await _enforce(
        redis=redis,
        actor_key=str(current_user.id),
        config=_APPEND_LIMITS,
    )


async def feedback_admin_create_ratelimit(
    current_admin: CurrentAdmin,
    redis: Annotated[Redis | None, Depends(get_redis)] = None,
) -> None:
    """ADR-0049 §3.2.1: POST /admin/feedbacks → 60/h per admin (no daily cap)."""
    await _enforce(
        redis=redis,
        actor_key=f"admin:{current_admin.id}",
        config=_ADMIN_CREATE_LIMITS,
    )


def _reset_inproc_store_for_tests() -> None:
    """Test-only: clear the in-process bucket store."""
    _INPROC_STORE.clear()
