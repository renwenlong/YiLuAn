"""Admin manual cache invalidation endpoint.

S3-DEV-005-CACHE-INVALIDATE — POST /api/v1/admin/cache/invalidate.

ADR-0048 §6 + design doc ``S3-trust-precheck-ui.md`` line 224 +
PRD-001 v1.4 §F8. 4 硬要求 per 魈 task comment ``79ce3e34``:

1. ``AdminAuditLog`` must be written (admin_id / order_id / cards /
   timestamp / source IP follow ``view_prep_package`` pattern in
   ``app/api/v1/admin/prep_packages.py``).
2. Rate limit ``5/minute per admin`` via slowapi ``@limiter.limit``
   with a key_func that extracts the Authorization token so two admins
   on the same NAT do not share a bucket.
3. Per-card audit tag — the request's ``cards`` list is stored
   verbatim in :attr:`AdminAuditLog.reason` so per-card remediation
   drives are reconstructable from the audit table alone.
4. Cache key is **single** ``precheck:order:{order_id}`` (魈 Q4 #4 —
   aggregator packs all 4 cards into one key, do not introduce
   per-card keys).

**Stub edition behavior** — until S3-DEV-003-PRECHECK-BACKEND fills
``OrderPrecheckAggregator.evaluate``, this endpoint returns **501
Not Implemented**. The defensive Redis ``DEL`` *does* run before the
501 (the cache is genuinely cleared, ops drills can rely on that);
the audit row is also persisted before the 501 so accountability
holds even on the stub path.

Auth model:

* ``Depends(get_super_admin)`` — only ``AdminRole.super_`` may invoke
  this endpoint (魈 amend comment ``34af879e``). ``ops`` / ``finance``
  roles get 403.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.openapi_meta import err
from app.core.rate_limit import limiter
from app.database import get_db
from app.dependencies import CurrentAdmin, DBSession
from app.models.admin_audit_log import AdminAuditLog
from app.models.admin_user import AdminRole, AdminUser
from app.schemas.admin_cache import (
    CacheInvalidateRequest,
    CacheInvalidateResponse,
)
from app.services.order_precheck_aggregator import OrderPrecheckAggregator

router = APIRouter(prefix="/cache", tags=["admin-cache"])


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


async def get_super_admin(current_admin: CurrentAdmin) -> AdminUser:
    """Require ``AdminRole.super_`` (魈 amend comment ``34af879e``).

    ``ops`` / ``finance`` admins get 403 — they have generic admin JWT
    but are not authorized for cache invalidation. ``super`` is the
    smallest sufficient privilege; we deliberately do not gate by
    individual username because role-level checks survive personnel
    changes (which the username allowlist would not).
    """
    if current_admin.role != AdminRole.super_:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="super_admin role required for cache invalidate",
        )
    return current_admin


SuperAdmin = Annotated[AdminUser, Depends(get_super_admin)]


AuditSession = Annotated[AsyncSession, Depends(get_db)]
"""Dedicated DB session for AdminAuditLog persistence.

Reuses ``get_db`` so the test suite's ``override_get_db`` (SQLite
in-memory) and any production replicas continue to work, but FastAPI
treats this as a separate dependency from :data:`DBSession`. We get
two independent ``AsyncSession`` instances, each with its own
transaction. We ``commit`` the audit session inside the handler so
the audit row is durable even when the request session rolls back
(e.g. 501 stub path raises an exception).
"""


def _admin_rate_limit_key(request: Request) -> str:
    """slowapi key_func that buckets by admin token (魈 hard req #2).

    slowapi's ``key_func`` runs before FastAPI deps resolve, so we
    cannot use a decoded ``AdminUser`` here. We bucket by the raw
    ``Authorization`` header value instead — since each admin has a
    distinct JWT, this produces the same per-admin partitioning
    without needing to decode the token.

    Falls back to the request client IP if Authorization is missing
    (e.g. preflight). The endpoint itself will 401 in that case, so
    the rate-limit bucket choice is moot, but we still want a
    deterministic key to keep slowapi happy.

    **Known trade-off**: an admin who re-logs-in (logout + login or
    refresh-token rotation) gets a *new* JWT and therefore a fresh
    rate-limit bucket — the 5/min budget effectively resets. We
    accept this because the login endpoint is itself throttled, so
    a real attacker who steals or guesses ``super_admin`` credentials
    still cannot re-mint tokens fast enough to evade the cache-invalidate
    limit in practice (token mint < 1/min). The trade-off is a known
    limitation, not a bypass; see PRD-001 v1.4 §F8 for the threat model.
    """
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return f"admin:{auth[7:]}"
    return f"ip:{request.client.host if request.client else 'unknown'}"


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post(
    "/invalidate",
    response_model=CacheInvalidateResponse,
    summary="admin 手动失效订单 precheck 缓存并触发重算 (super_admin only)",
    description=(
        "admin (仅 super) 手动触发某订单 precheck:order:{order_id} 缓存失效 + "
        "OrderPrecheckAggregator 重算 + WS broadcast。\n\n"
        "**stub 阶段返 501** (本 PR S3-DEV-005-CACHE-INVALIDATE 范围)。\n"
        "aggregator.evaluate 在 S3-DEV-003-PRECHECK-BACKEND 实装后, "
        "本 endpoint 不动, 自动返 200 (invalidated_keys + broadcast=true)。\n\n"
        "保证 (即使 501 回应)：\n"
        "* defensive Redis DEL precheck:order:{order_id} 已执行;\n"
        "* AdminAuditLog 已写 (admin_id / order_id / cards / timestamp)。\n\n"
        "rate limit: 5/min per admin (按 Authorization token 分桶)。"
    ),
    responses={
        **err(401, 403, 404, 422, 429, 500),
        501: {
            "description": (
                "OrderPrecheckAggregator stub 未实装 evaluate / SET / broadcast "
                "(S3-DEV-005-CACHE-INVALIDATE 范围)。PRECHECK-BACKEND 接管后翻 200。"
            ),
        },
    },
)
@limiter.limit("5/minute", key_func=_admin_rate_limit_key)
async def invalidate_cache(
    request: Request,
    body: CacheInvalidateRequest,
    admin: SuperAdmin,
    session: DBSession,  # noqa: ARG001 — kept for DI symmetry; audit uses dedicated session
    audit_session: AuditSession,
) -> CacheInvalidateResponse:
    # AC #1 + #3: write the audit row in a **dedicated** session that
    # commits independently of the request-scoped transaction.
    #
    # ``DBSession`` (via ``get_db``) rolls back on any exception, so a
    # 501 from the stub path would drop the audit row if we used the
    # same session — violating 魈 hard requirement #1 ("AdminAuditLog
    # 必写"). ``AuditSession`` is a second injection of ``get_db`` and
    # FastAPI gives us a fresh session per dep; we ``commit`` it here
    # so the audit trace is durable even when the aggregator raises.
    #
    # ``cards`` is JSON-friendly comma-joined into the ``reason`` text
    # column for per-card forensics (魈 Q4 #3). Sorting makes the row
    # stable across client orderings (eases dedup / log analysis).
    cards_repr = (
        ",".join(sorted(body.cards)) if body.cards else "*all"
    )
    audit_session.add(
        AdminAuditLog(
            target_type="precheck_cache",
            target_id=body.order_id,
            action="invalidate",
            operator=admin.username,
            reason=f"cards={cards_repr}",
        )
    )
    await audit_session.commit()

    # AC #4 + stub orchestrator. ``invalidate_and_recompute`` will:
    #   1. run defensive ``redis DEL precheck:order:{order_id}``
    #      (real, ships in this task);
    #   2. call ``evaluate`` (stub → NotImplementedError).
    #
    # We catch ``NotImplementedError`` and surface 501 to the admin so
    # the response shape is deterministic during the stub window.
    # PRECHECK-BACKEND swaps the body for real evaluate / SET /
    # broadcast and the same endpoint starts returning 200; **no
    # endpoint code changes** are required for that flip.
    aggregator = OrderPrecheckAggregator(request.app.state.redis)
    try:
        result = await aggregator.invalidate_and_recompute(
            order_id=body.order_id,
            cards=body.cards,
        )
    except NotImplementedError as exc:
        # Audit row is already committed via the session; the
        # defensive DEL also already ran inside the aggregator before
        # ``evaluate`` raised. We surface 501 so the admin client
        # knows the operation is only partially applied (cache
        # cleared, no recompute, no broadcast). Detail string is
        # stable so monitoring can alert on the stub window closing.
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=(
                "precheck aggregator evaluate stub — "
                "S3-DEV-003-PRECHECK-BACKEND must land before this "
                "endpoint returns 200. Defensive cache DEL has run; "
                "audit row is persisted."
            ),
        ) from exc

    return CacheInvalidateResponse(**result)
