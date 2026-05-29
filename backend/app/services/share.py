"""Family-share service (ADR-0036 §2.2/§2.3/§2.5, S2-DEV-002).

Owns the four high-level operations behind the W20 Top1 family
companion endpoints:

* ``create_share`` — order owner mints a new share token.
* ``revoke_share`` — order owner revokes a single token; the WS layer
  (S2-DEV-003) reads ``revoked_at`` and closes connections with code
  4013.
* ``exchange_session`` — family viewer trades token + (openid | otp)
  for a 30-minute ``share_session`` JWT.
* ``build_share_order_view`` — desensitized read-only order payload
  for the family-facing GET endpoint.

JWT signing reuses :mod:`app.core.security` settings (same secret /
algorithm) but stamps a dedicated ``type=share_session`` claim so the
viewer JWT can never be promoted into an access token.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Final
from uuid import UUID

import jwt
from jwt import PyJWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.pii import mask_name
from app.exceptions import (
    ForbiddenException,
    NotFoundException,
    UnauthorizedException,
)
from app.models.order_share_token import (
    ACTIVE_TOKEN_CAP_PER_ORDER,
    OrderShareToken,
    ShareScope,
)
from app.repositories.order_share_token import OrderShareTokenRepository

SHARE_URL_TEMPLATE: Final[str] = "https://m.yiluan.cn/s/{token}"
SHARE_SESSION_TTL: Final[timedelta] = timedelta(minutes=30)
SHARE_SESSION_TOKEN_TYPE: Final[str] = "share_session"
# Defense-in-depth alongside `type`: pin JWT audience so even if the same
# secret/algorithm is ever reused for a different surface, a stolen share
# session can't replay against, say, an access-token endpoint that forgets
# to check `type`. See ADR-0036 §3.5 #5 + S1-DEV-001 review 三.1.
SHARE_SESSION_AUDIENCE: Final[str] = "share"


def build_share_url(token: str) -> str:
    return SHARE_URL_TEMPLATE.format(token=token)


def _sign_share_session(
    *,
    token_id: UUID,
    order_id: UUID,
    share_scope: ShareScope,
    accessor_openid: str | None,
    issued_at: datetime,
    expires_at: datetime,
) -> str:
    payload = {
        "type": SHARE_SESSION_TOKEN_TYPE,
        "aud": SHARE_SESSION_AUDIENCE,
        "tid": str(token_id),
        "oid": str(order_id),
        "scope": share_scope.value,
        "acc": accessor_openid,
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    return jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def decode_share_session(token: str) -> dict:
    """Decode + structurally validate a share_session JWT.

    Raises :class:`UnauthorizedException` for any failure (expired,
    bad signature, wrong type, ``alg=none``) — Top1 §3.5 #5 requirement.
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            audience=SHARE_SESSION_AUDIENCE,
        )
    except PyJWTError as exc:
        raise UnauthorizedException("Invalid or expired share session") from exc
    if payload.get("type") != SHARE_SESSION_TOKEN_TYPE:
        raise UnauthorizedException("Invalid share session type")
    return payload


class ShareService:
    """Order-owner + family-viewer flows for family share links."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.tokens = OrderShareTokenRepository(session)

    # -- owner-side: mint / list / revoke ----------------------------------

    async def create_share(
        self,
        *,
        order_id: UUID,
        owner_id: UUID,
        share_scope: ShareScope,
        order_completed_at: datetime | None,
    ) -> tuple[OrderShareToken, int]:
        token = await self.tokens.create_with_active_cap(
            order_id=order_id,
            created_by=owner_id,
            order_completed_at=order_completed_at,
            share_scope=share_scope,
        )
        try:
            from app.observability.share_metrics import (
                SHARE_TOKEN_CREATED_TOTAL,
            )

            SHARE_TOKEN_CREATED_TOTAL.labels(
                share_scope=getattr(share_scope, "value", str(share_scope))
            ).inc()
        except Exception:  # metrics never break the create path
            pass
        active = await self.tokens.list_active_for_order(order_id)
        return token, len(active)

    async def list_active(
        self, *, order_id: UUID
    ) -> list[OrderShareToken]:
        return list(await self.tokens.list_active_for_order(order_id))

    async def revoke(
        self,
        *,
        order_id: UUID,
        token_id: UUID,
        revoked_by: UUID,
    ) -> None:
        # Re-load to assert cross-order isolation (Top1 §3.5 #3).
        row = await self.tokens.get_by_id(token_id)
        if row is None or row.order_id != order_id:
            raise NotFoundException("Share token not found")
        if row.revoked_at is not None:
            return  # idempotent revoke
        await self.tokens.revoke(row, revoked_by=revoked_by)

    # -- viewer-side: exchange / read --------------------------------------

    async def exchange_session(
        self,
        *,
        token_value: str,
        wx_openid: str | None,
        otp: str | None,
    ) -> tuple[str, datetime, OrderShareToken]:
        if not wx_openid and not otp:
            # We intentionally return 401 (not 422) so we don't leak a
            # "token exists, only auth is bad" signal.
            raise UnauthorizedException("Share session requires wx_openid or otp")

        row = await self.tokens.get_by_token(token_value)
        if row is None:
            raise UnauthorizedException("Invalid share token")
        if not row.is_active:
            # Covers both ``revoked_at is not None`` and ``expires_at <= now``.
            raise UnauthorizedException("Share token expired or revoked")

        # OTP path is currently the trusted-stub seam for S2-DEV-002 — the
        # real Aliyun-SMS OTP verifier (existing `services.sms`) plugs in
        # via S2-DEV-006 hardening. For now an OTP must be exactly 6
        # digits to clear the door; openid path is fully trusted to the
        # caller because the controller has already done wx.jscode2session.
        accessor: str
        if wx_openid:
            accessor = wx_openid
        else:
            if not (otp and otp.isdigit() and len(otp) == 6):
                raise UnauthorizedException("Invalid OTP")
            accessor = f"otp:{otp[-2:]}"  # accessor surrogate, last 2 only

        # Bump access aggregates (first/last/distinct).
        await self.tokens.record_access(row, accessor_openid=accessor)

        now = datetime.now(timezone.utc)
        exp = now + SHARE_SESSION_TTL
        jwt_str = _sign_share_session(
            token_id=row.id,
            order_id=row.order_id,
            share_scope=row.share_scope,
            accessor_openid=accessor,
            issued_at=now,
            expires_at=exp,
        )
        return jwt_str, exp, row

    async def load_token_from_session(self, payload: dict) -> OrderShareToken:
        """Reload + re-validate the underlying token for every viewer
        request — a revoked token cuts off mid-session (§3.5 #2)."""
        token_id_str = payload.get("tid")
        if not token_id_str:
            raise UnauthorizedException("Invalid share session: missing token id")
        try:
            token_id = UUID(token_id_str)
        except ValueError as exc:
            raise UnauthorizedException(
                "Invalid share session: malformed token id"
            ) from exc
        row = await self.tokens.get_by_id(token_id)
        if row is None or not row.is_active:
            raise UnauthorizedException("Share token expired or revoked")
        return row

    # -- viewer-side: desensitized order view ------------------------------

    @staticmethod
    def build_share_order_view(
        *,
        order,  # app.models.Order
        share_scope: ShareScope,
        companion=None,  # app.models.User | None
    ) -> dict:
        """Apply §2.5 PII rules + §2.7 field set."""
        is_full = share_scope == ShareScope.FULL
        companion_view = None
        if companion is not None:
            companion_view = {
                "name": getattr(companion, "real_name", None)
                or getattr(companion, "nickname", None),
                "avatar_url": getattr(companion, "avatar_url", None),
            }
        return {
            "order_id": order.id,
            "order_number": order.order_number,
            "status": (
                order.status.value
                if hasattr(order.status, "value")
                else order.status
            ),
            "service_type": (
                order.service_type.value
                if hasattr(order.service_type, "value")
                else order.service_type
            ),
            "appointment_date": str(order.appointment_date),
            "appointment_time": str(order.appointment_time),
            "hospital_name": getattr(order, "hospital_name", None),
            "patient_name_masked": mask_name(
                getattr(order, "patient_name", None)
            ),
            "companion": companion_view,
            "share_scope": share_scope,
            "can_view_images": is_full,
            "can_view_ai_summary": is_full,
            "timeline": None,  # populated in S2-DEV-003 (timeline join)
        }


__all__ = [
    "ACTIVE_TOKEN_CAP_PER_ORDER",
    "SHARE_SESSION_TTL",
    "SHARE_SESSION_AUDIENCE",
    "SHARE_SESSION_TOKEN_TYPE",
    "SHARE_URL_TEMPLATE",
    "ShareService",
    "build_share_url",
    "decode_share_session",
]
