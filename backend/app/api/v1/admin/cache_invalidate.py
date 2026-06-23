"""Admin manual cache invalidation endpoint.

S3-DEV-005-CACHE-INVALIDATE — POST /api/v1/admin/cache/invalidate.

ADR-0048 §6 + design doc ``S3-trust-precheck-ui.md`` line 224 +
PRD-001 v1.4 §F8. 4 硬要求 per 魈 task comment ``79ce3e34``:

1. ``AdminAuditLog`` must be written (admin_id / order_id / cards /
   timestamp / source IP follow ``view_prep_package`` pattern in
   ``app/api/v1/admin/prep_packages.py``).
2. Rate limit ``5/minute per admin`` via slowapi ``@limiter.limit``
   with a key_func that decodes the bearer JWT and buckets by its
   ``sub`` (admin_id) claim, so two admins on the same NAT do not
   share a bucket **and** a single admin's re-login does not reset
   the bucket (S3-OPS-RATE-LIMIT-PER-ADMIN-ID removed the PR #250
   token-keyed trade-off; the limit value stays 5/min).
3. Per-card audit tag — the request's ``cards`` list is stored
   verbatim in :attr:`AdminAuditLog.reason` so per-card remediation
   drives are reconstructable from the audit table alone.
4. Cache key is **single** ``precheck:order:{order_id}`` (魈 Q4 #4 —
   aggregator packs all 4 cards into one key, do not introduce
   per-card keys).

**c2 evaluate landed**: S3-DEV-003-PRECHECK-BACKEND c2 fills
``OrderPrecheckAggregator.evaluate`` + ``_redis_set``, so this
endpoint now returns 200 with real ``invalidated_keys`` +
``broadcast`` (broadcast still ``False`` until c4 WS infra lands).
The audit row is persisted before aggregator runs so failure
modes still leave a forensic trail.

Auth model:

* ``Depends(get_super_admin)`` — only ``AdminRole.super_`` may invoke
  this endpoint (魈 amend comment ``34af879e``). ``ops`` / ``finance``
  roles get 403.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.openapi_meta import err
from app.core.admin_jwt import decode_admin_token
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
(e.g. aggregator / cache layer raises an unexpected exception).
"""


def _admin_rate_limit_key(request: Request) -> str:
    """slowapi key_func that buckets by decoded ``admin_id`` (S3-OPS-RATE-LIMIT-PER-ADMIN-ID).

    slowapi's ``key_func`` runs before FastAPI deps resolve, so we cannot
    read a resolved ``AdminUser`` here. We instead decode the bearer JWT
    *in-place* via :func:`decode_admin_token` and bucket by its ``sub``
    claim (the AdminUser PK, identical across re-logins). This removes the
    PR #250 trade-off where an admin re-login minted a new JWT and thus a
    fresh 5/min bucket: ``sub`` is stable, so re-login now hits the **same**
    bucket (AC#1/#2). Distinct admins carry distinct ``sub`` claims and stay
    isolated (AC#3).

    Fallback (AC#5): if Authorization is missing/malformed, the token fails
    to decode (expired / wrong type / bad signature), or ``sub`` is absent,
    we fall back to the client IP and **never** raise — ``decode_admin_token``
    raises :class:`UnauthorizedException` on failure, which we swallow here
    so the rate-limit layer cannot 500. The endpoint's own auth dependency
    will still 401/403 the request, so the bucket choice for an unauthorized
    caller is moot; the IP fallback only keeps slowapi's key deterministic.

    Note: the limit value (5/min) is unchanged from PR #250 — this task only
    re-keys the bucket dimension, not the threshold (AC#4).
    """
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
        if token:
            try:
                payload = decode_admin_token(token)
                sub = payload.get("sub")
                if sub:
                    return f"admin:{sub}"
            except Exception:
                # decode failure (expired / invalid / non-admin type) — do
                # not raise from a key_func; fall through to IP so the
                # endpoint's auth dep handles the 401/403 (AC#5).
                pass
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
        "**S3-DEV-003 c2 evaluate 已落**: 本 endpoint 返 200 + invalidated_keys + "
        "broadcast (broadcast=False 直到 c4 WS infra 落)。\n\n"
        "保证 (200 响应)：\n"
        "* defensive Redis DEL precheck:order:{order_id} 已执行;\n"
        "* OrderPrecheckAggregator.evaluate 重算 4 卡 + redis SET (TTL 5min);\n"
        "* AdminAuditLog 已写 (admin_id / order_id / cards / timestamp)。\n\n"
        "rate limit: 5/min per admin (按 decoded admin_id 分桶 — "
        "S3-OPS-RATE-LIMIT-PER-ADMIN-ID 消除 PR #250 'admin re-login 重置 bucket' trade-off)。"
    ),
    responses=err(401, 403, 404, 422, 429, 500),
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
    # ``DBSession`` (via ``get_db``) rolls back on any exception. We
    # use a second session for the audit row so failures further down
    # the call chain (aggregator error, redis outage, etc.) still leave
    # a durable forensic trail — satisfying 魈 hard requirement #1
    # ("AdminAuditLog 必写").
    #
    # ``cards`` is JSON-friendly comma-joined into the ``reason`` text
    # column for per-card forensics (魈 Q4 #3). Sorting makes the row
    # stable across client orderings (eases dedup / log analysis).
    cards_repr = ",".join(sorted(body.cards)) if body.cards else "*all"
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

    # AC #4 + S3-DEV-003 c2 evaluate landed: ``invalidate_and_recompute``
    # now returns a real summary. The endpoint just relays
    # ``invalidated_keys`` + ``broadcast`` to the admin.
    #
    # S3-DEV-003 c5: ``_ws_broadcast`` now real. Pass app so the
    # aggregator can publish via the precheck broadcast facade. When
    # no WS subscriber is connected to the order_id room, broadcast
    # still records ``True`` (publish succeeded, no recipients).
    aggregator = OrderPrecheckAggregator(
        request.app.state.redis,
        session=session,
        app=request.app,
    )
    result = await aggregator.invalidate_and_recompute(
        order_id=body.order_id,
        cards=body.cards,
    )

    # c6 dedup: orchestrator returns ``summary`` for internal hook
    # reuse, but admin endpoint contract stays 2 fields only.
    # Explicit field pick prevents ABAC side-channel via summary key
    # leaking 4-card detail to admin without proper UI gating.
    return CacheInvalidateResponse(
        invalidated_keys=result["invalidated_keys"],
        broadcast=result["broadcast"],
    )
