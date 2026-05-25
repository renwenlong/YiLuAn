"""Telemetry ingest endpoint — frontend logger / funnel sink.

Routes
------
POST /api/v1/telemetry/events
    Public-ish ingest. Auth is **optional** — frontend funnel emits
    pre-login events (browse list, view detail) before the user is
    authenticated. If a valid bearer token is present we attach
    ``user_id``; otherwise we record it as anonymous.

Rate limit
----------
Hard-capped at 120/min/IP via the existing ``slowapi`` limiter.

PII policy
----------
The schema validator (``schemas/telemetry.py``) rejects payloads that
contain CN mobile numbers / 身份证 / bank-card-like digit runs as a
defence-in-depth measure.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.api.v1.openapi_meta import err
from app.core.rate_limit import limiter
from app.core.security import decode_token
from app.dependencies import DBSession
from app.models.telemetry_event import TelemetryEvent
from app.schemas.telemetry import (
    TelemetryEventAccepted,
    TelemetryEventCreate,
)

router = APIRouter(prefix="/telemetry", tags=["telemetry"])


# auto_error=False so the dep doesn't 401 unauthenticated callers; we *want*
# to accept anonymous funnel pings.
_optional_bearer = HTTPBearer(auto_error=False)


async def _maybe_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
) -> UUID | None:
    """Best-effort user resolution. Never raises — telemetry must not 401."""
    if credentials is None:
        return None
    try:
        payload = decode_token(credentials.credentials)
        if not payload or payload.get("type") != "access":
            return None
        sub = payload.get("sub")
        if not sub:
            return None
        return UUID(str(sub))
    except Exception:  # noqa: BLE001 — telemetry must never fail on auth quirks
        return None


@router.post(
    "/events",
    response_model=TelemetryEventAccepted,
    summary="上报埋点 / 异常事件",
    description=(
        "前端 `utils/logger.report` 通道 + `utils/analytics` 漏斗事件统一入口。\n\n"
        "**鉴权**：可选。带 `Authorization: Bearer <token>` 时会关联 `user_id`，"
        "否则匿名落库。\n\n"
        "**限流**：同一 IP 每分钟最多 120 次。\n\n"
        "**PII 拒收**：payload / client_meta 含手机号 / 身份证 / 卡号样式字符串"
        "时返回 422。"
    ),
    responses={**err(422, 429)},
    status_code=202,
)
@limiter.limit("120/minute")
async def ingest_event(
    body: TelemetryEventCreate,
    request: Request,
    session: DBSession,
    user_id: UUID | None = Depends(_maybe_user_id),
) -> TelemetryEventAccepted:
    event = TelemetryEvent(
        event_type=body.event_type,
        payload=body.payload or {},
        client_meta=body.client_meta or {},
        user_id=user_id,
        client_ts=body.ts,
    )
    session.add(event)
    await session.commit()
    return TelemetryEventAccepted(accepted=True)
