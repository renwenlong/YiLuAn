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
    ) -> str | None:
        """Revoke share token; return its token value when actually revoked,
        or None on idempotent re-revoke / unknown id.

        S2-TEST-006R3 AC#9: caller uses the returned token value to dispatch
        a server-side close 4013 to any live family WS bound to that token.
        """
        # Re-load to assert cross-order isolation (Top1 §3.5 #3).
        row = await self.tokens.get_by_id(token_id)
        if row is None or row.order_id != order_id:
            raise NotFoundException("Share token not found")
        if row.revoked_at is not None:
            return None  # idempotent revoke; do not re-broadcast close
        token_value = row.token
        await self.tokens.revoke(row, revoked_by=revoked_by)
        return token_value

    # -- viewer-side: exchange / read --------------------------------------

    async def exchange_session(
        self,
        *,
        token_value: str,
        wx_openid: str | None,
        verified_accessor: str | None,
    ) -> tuple[str, datetime, OrderShareToken]:
        if not wx_openid and not verified_accessor:
            # We intentionally return 401 (not 422) so we don't leak a
            # "token exists, only auth is bad" signal.
            raise UnauthorizedException(
                "Share session requires wx_openid or a verified OTP"
            )

        row = await self.tokens.get_by_token(token_value)
        if row is None:
            raise UnauthorizedException("Invalid share token")
        if not row.is_active:
            # Covers both ``revoked_at is not None`` and ``expires_at <= now``.
            raise UnauthorizedException("Share token expired or revoked")

        # accessor identity:
        #   · 微信静默路径 → openid (controller already ran jscode2session)
        #   · iOS/H5 OTP 路径 → phone-hash accessor, 已由 OtpService.verify_otp
        #     真验证 (S2-DEV-011); service 层不再做 6 位 stub 直通。
        accessor: str
        if wx_openid:
            accessor = wx_openid
        else:
            assert verified_accessor is not None  # guarded above
            accessor = verified_accessor

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
    def build_companion_cert_view(
        companion_profile,  # app.models.companion_profile.CompanionProfile | None
    ) -> dict | None:
        """Map ``CompanionProfile`` → 9-field cert sub-object dict.

        Returns ``None`` when ``companion_profile is None`` (caller decides
        whether to wrap in ``CompanionPublicCertView`` or leave null).

        魈 2026-06-11 拍板 (S3-DEV-005-SHARE-CONTRACT Ghost #1 D 改良版):
        - 三态映射 model.verification_status → PRD-001 §F8 UI 三态 enum
        - 颜色/icon/文案三层 backend hardcode, 三端 0 mapping 自由度 (PM-005-2/3)
        - 绝不出 real_name / id_number / certification_image_url (ABAC layer 1)
        """
        if companion_profile is None:
            return None

        from app.models.companion_profile import VerificationStatus

        vs = getattr(companion_profile, "verification_status", None)
        if vs == VerificationStatus.verified:
            status_enum = "verified"
            badge_color = "green"
            badge_icon = "check"
            detail_text = "该陪诊师已完成资质认证"
        elif vs == VerificationStatus.pending:
            status_enum = "pending_supplement"
            badge_color = "yellow"
            badge_icon = "clock"
            detail_text = "该陪诊师临时证明有效，资质补交中"
        else:
            # ``rejected`` 或 None 都归 unverified (对外不区分)
            status_enum = "unverified"
            badge_color = "gray"
            badge_icon = "dash"
            detail_text = "该陪诊师尚未完成资质认证"

        # cert_count: PRD-001 §F8 "资质件数" — model 当前只有
        # certification_type (单个) + certifications (Text json), 未拆列表.
        # 仅 verified 状 + 有 certification_type 计 1, 其他 0. 后续
        # PRD-001 v1.5 拆 multi-cert table 时重映射.
        cert_type_val = getattr(companion_profile, "certification_type", None)
        cert_count = 1 if (vs == VerificationStatus.verified and cert_type_val) else 0

        # cert_verified_at: 优先 verification_completed_at (魈 r2 加,
        # admin approve 实际时间), fallback certified_at (凭证颁发日).
        verified_at = getattr(
            companion_profile, "verification_completed_at", None
        ) or getattr(companion_profile, "certified_at", None)
        if vs != VerificationStatus.verified:
            verified_at = None  # pending/rejected 不出时间

        # cert_pseudonym_name: 化名 — model 未落专字段, S3 本 task null
        # (PRD-001 v1.5 拆 companion_pseudonym table 时接入, 现仅占位).
        # 严禁 fallback real_name (ABAC layer 1 + PM-005-3/4).
        pseudonym = None

        # cert_work_id: model.certification_no 是证件号 (同质但不完全等于
        # 平台工号); PRD-001 v1.5 拆 work_id 时更新. S3 仅 verified
        # 状下暴露, 限 PC + 4 位 hash 脱敏.
        work_id = None
        if vs == VerificationStatus.verified:
            cert_no = getattr(companion_profile, "certification_no", None)
            if cert_no:
                # 脱敏: 取后 4 位, 前加 'PC' 前缀 (与 PRD §F8 例 'PC0042' 对齐)
                tail = cert_no[-4:].rjust(4, "0")
                work_id = f"PC{tail}"

        return {
            "cert_status": status_enum,
            "cert_type": cert_type_val if vs == VerificationStatus.verified else None,
            "cert_count": cert_count,
            "cert_verified_at": verified_at,
            "cert_pseudonym_name": pseudonym,
            "cert_work_id": work_id,
            "cert_badge_color": badge_color,
            "cert_badge_icon": badge_icon,
            "cert_detail_text": detail_text,
        }

    @staticmethod
    def build_share_order_view(
        *,
        order,  # app.models.Order
        share_scope: ShareScope,
        companion=None,  # app.models.User | None
        companion_profile=None,  # app.models.companion_profile.CompanionProfile | None
    ) -> dict:
        """Apply §2.5 PII rules + §2.7 field set.

        S3-DEV-005-SHARE-CONTRACT: 加 ``companion_profile`` 参以构建
        ``companion.cert_status`` sub-object (PM-005-1~5). 向后兼容 —
        不传 profile 时 cert_status=None (未认证陪诊师 / 无 profile).
        """
        is_full = share_scope == ShareScope.FULL
        companion_view = None
        if companion is not None:
            cert_view = ShareService.build_companion_cert_view(companion_profile)
            # S3-BUG-004-SHARE-COMPANION-NAME-PII-LEAK: User model 0
            # ``real_name`` / ``nickname`` 字段 (fact check: grep + python
            # inspect(User).columns 双验), 旧 ``getattr(companion, "real_name")
            # or getattr(companion, "nickname")`` 永返 None 是 silent author
            # bug, 不是 ABAC layer 1 漏出. 改用唯一存在的 ``display_name``
            # 字段, fallback 通名 "陪诊师" (跟 lifecycle.py:143/216 + review.py:97
            # 套路一致). 绝不 fallback ``real_name`` (即使后期 User 加字段,
            # 也走 CompanionProfile pseudonym 路径).
            companion_view = {
                "name": getattr(companion, "display_name", None)
                or "陪诊师",
                "avatar_url": getattr(companion, "avatar_url", None),
                "cert_status": cert_view,
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
