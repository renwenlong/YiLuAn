"""Family-share REST endpoints (ADR-0036 §2.7 + PRD-001 v1.2 §4, S2-DEV-002).

Six endpoints land under two routers (one mounted under
``/orders/{order_id}/shares`` for owner-side flows, one under
``/shares`` for family-viewer-side flows) and are aggregated by
:mod:`app.api.v1.router` via :data:`router`.

OpenAPI baseline (S2-DEV-004) snapshots every field name & required
flag — any drift must clear an explicit re-review.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis

from app.api.v1.openapi_meta import err
from app.config import settings
from app.core import error_codes
from app.core.redis import get_redis
from app.dependencies import CurrentUser, DBSession
from app.exceptions import (
    BadRequestException,
    ForbiddenException,
    NotFoundException,
    ServiceUnavailableException,
    TooManyRequestsException,
    UnauthorizedException,
)
from app.models.order_share_token import ACTIVE_TOKEN_CAP_PER_ORDER
from app.repositories.order import OrderRepository
from app.schemas.share import (
    CreateShareRequest,
    CreateShareResponse,
    ExchangeSessionRequest,
    ExchangeSessionResponse,
    ListSharesResponse,
    SendOtpRequest,
    SendOtpResponse,
    ShareOrderResponse,
    ShareTokenResponse,
)
from app.services.providers.sms.base import mask_phone_sms
from app.services.share import (
    ShareService,
    build_share_url,
    decode_share_session,
)
from app.services.share_otp import (
    OtpInvalidError,
    OtpRateLimitedError,
    OtpSendError,
    OtpService,
)

# Two routers so URL prefixes stay close to the spec. They are both
# included under ``api_v1_router`` by ``app.api.v1.router``.
router = APIRouter(tags=["share"])
_orders_share_router = APIRouter(prefix="/orders/{order_id}/shares")
_shares_router = APIRouter(prefix="/shares")


# Bearer security for the family-viewer endpoints; we re-implement the
# dep locally because the JWT ``type`` differs from access tokens.
_share_bearer = HTTPBearer(auto_error=True)


async def _require_share_session(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_share_bearer)],
) -> dict:
    """Decode + validate the family-viewer share_session JWT."""
    return decode_share_session(credentials.credentials)


# Helpers --------------------------------------------------------------------


async def _ensure_order_owner(
    *,
    session,
    order_id: UUID,
    user_id: UUID,
):
    repo = OrderRepository(session)
    order = await repo.get_by_id(order_id)
    if order is None:
        raise NotFoundException("Order not found")
    # ADR-0036 §2.5 注: token 永远绑在「下单人」(order.patient_id) 维度。
    if order.patient_id != user_id:
        raise ForbiddenException("Only the order owner can manage shares")
    return order


def _token_to_response(token) -> ShareTokenResponse:
    return ShareTokenResponse(
        id=token.id,
        share_token=token.token,
        share_url=build_share_url(token.token),
        share_scope=token.share_scope,
        share_expires_at=token.expires_at,
        share_revoked_at=token.revoked_at,
        created_at=token.created_at,
        first_accessed_at=token.first_accessed_at,
        distinct_accessor_count=token.distinct_accessor_count,
    )


# Owner-side endpoints --------------------------------------------------------


@_orders_share_router.post(
    "",
    response_model=CreateShareResponse,
    status_code=201,
    summary="下单人创建家属分享 token",
    description=(
        "创建一条 OrderShareToken 并返回短链。"
        f"单订单 active token 数硬上限 = {ACTIVE_TOKEN_CAP_PER_ORDER}，"
        "已达上限时自动 revoke 最老一条。"
    ),
    responses={**err(401, 403, 404, 422, 500)},
)
async def create_share(
    order_id: UUID,
    body: CreateShareRequest,
    current_user: CurrentUser,
    session: DBSession,
):
    # S2-OPS-011 火度门：FEATURE_SHARE_F2_ENABLED=false 热关 F2 入口
    if not settings.feature_share_f2_enabled:
        raise ServiceUnavailableException(
            "F2 分享入口已临时关闭，请稍后重试",
            error_code=error_codes.SHARE_F2_DISABLED,
        )
    # S2-OPS-011: readonly 模式下也拒创建新 share_token
    if settings.readonly_share_sessions:
        raise ServiceUnavailableException(
            "分享服务临时只读，不允许创建新分享",
            error_code=error_codes.SHARE_SESSIONS_READONLY,
        )
    order = await _ensure_order_owner(
        session=session, order_id=order_id, user_id=current_user.id
    )
    svc = ShareService(session)
    token, active_count = await svc.create_share(
        order_id=order_id,
        owner_id=current_user.id,
        share_scope=body.share_scope,
        order_completed_at=getattr(order, "completed_at", None),
    )
    await session.commit()
    payload = _token_to_response(token).model_dump()
    payload["share_active_count"] = active_count
    return CreateShareResponse(**payload)


@_orders_share_router.get(
    "",
    response_model=ListSharesResponse,
    summary="下单人查看当前 active 分享 token",
    description=(
        "下单人（owner）查询指定订单下当前处于 active 状态的家属分享 token 列表，"
        "返回 token 概要及 ``share_active_count`` 计数。需 owner 身份鉴权。"
    ),
    responses={**err(401, 403, 404, 500)},
)
async def list_shares(
    order_id: UUID,
    current_user: CurrentUser,
    session: DBSession,
):
    await _ensure_order_owner(
        session=session, order_id=order_id, user_id=current_user.id
    )
    svc = ShareService(session)
    rows = await svc.list_active(order_id=order_id)
    items = [_token_to_response(r) for r in rows]
    return ListSharesResponse(items=items, share_active_count=len(items))


@_orders_share_router.delete(
    "/{token_id}",
    status_code=204,
    summary="下单人吊销指定分享 token",
    description=(
        "幂等吊销。WS 服务端读 ``revoked_at``，已建立的家属连接将以 "
        "code 4013 主动断开（S2-DEV-003 实现）。"
    ),
    responses={**err(401, 403, 404, 500)},
)
async def revoke_share(
    order_id: UUID,
    token_id: UUID,
    current_user: CurrentUser,
    session: DBSession,
):
    await _ensure_order_owner(
        session=session, order_id=order_id, user_id=current_user.id
    )
    svc = ShareService(session)
    await svc.revoke(
        order_id=order_id, token_id=token_id, revoked_by=current_user.id
    )
    await session.commit()


# Viewer-side endpoints -------------------------------------------------------


@_shares_router.post(
    "/{token}/otp",
    response_model=SendOtpResponse,
    summary="家属端（iOS/H5）请求下发短信验证码",
    description=(
        "iOS App / 外部浏览器无微信静默授权时的降级路径（ADR-0036 §2.2）。"
        "双轴频控：单 token 24h ≤ 5 次、单手机号 1h ≤ 3 个不同 token，"
        "超限 429 转人工。成功后验证码有效期 5min。"
    ),
    responses={**err(429, 422, 500)},
)
async def send_share_otp(
    token: str,
    body: SendOtpRequest,
    redis: Annotated[Redis, Depends(get_redis)],
):
    otp_svc = OtpService(redis)
    try:
        await otp_svc.send_otp(token_value=token, phone=body.phone)
    except OtpRateLimitedError as exc:
        raise TooManyRequestsException(str(exc)) from exc
    except OtpSendError as exc:
        raise BadRequestException(str(exc)) from exc
    return SendOtpResponse(
        sent=True,
        masked_phone=mask_phone_sms(body.phone),
        expires_in=settings.share_otp_ttl_seconds,
    )


@_shares_router.post(
    "/{token}/session",
    response_model=ExchangeSessionResponse,
    summary="家属端用 token + openid/(phone+otp) 换 share_session JWT",
    description=(
        "微信小程序静默路径传 ``wx_openid``；iOS / 外部浏览器路径先调 "
        "``POST /shares/{token}/otp`` 收码，再传 ``phone`` + ``otp``（6 位）。"
        "过期 / 已 revoke 的 token、验证码错误/过期 一律 401。"
    ),
    responses={**err(401, 422, 500)},
)
async def exchange_session(
    token: str,
    body: ExchangeSessionRequest,
    session: DBSession,
    redis: Annotated[Redis, Depends(get_redis)],
):
    # S2-OPS-011 火度门：READONLY_SHARE_SESSIONS=true 冻结新会话
    # （已发 share_session JWT 仍可继续读视图，仅拒新 exchange）
    if settings.readonly_share_sessions:
        raise ServiceUnavailableException(
            "分享服务临时只读，不允许创建新会话",
            error_code=error_codes.SHARE_SESSIONS_READONLY,
        )
    # iOS/H5 OTP path: verify phone+otp first to obtain the phone-hash
    # accessor. 微信路径走 openid 直通。
    verified_accessor: str | None = None
    if not body.wx_openid:
        if not (body.phone and body.otp):
            raise UnauthorizedException(
                "Share session requires wx_openid or phone+otp"
            )
        otp_svc = OtpService(redis)
        try:
            verified_accessor = await otp_svc.verify_otp(
                token_value=token, phone=body.phone, code=body.otp
            )
        except OtpInvalidError as exc:
            raise UnauthorizedException(str(exc)) from exc

    svc = ShareService(session)
    jwt_str, exp, row = await svc.exchange_session(
        token_value=token,
        wx_openid=body.wx_openid,
        verified_accessor=verified_accessor,
    )
    await session.commit()
    return ExchangeSessionResponse(
        share_session=jwt_str,
        share_session_expires_at=exp,
        share_scope=row.share_scope,
        order_id=row.order_id,
    )


@_shares_router.get(
    "/session/order",
    response_model=ShareOrderResponse,
    summary="家属端用 share_session 拉脱敏订单视图",
    description=(
        "返回 §2.5 PII 表筛选后的字段集。``scope=progress_only`` 时"
        "影像 + AI 摘要的 can_* 标志为 false (AC#21)。"
    ),
    responses={**err(401, 403, 404, 500)},
)
async def get_share_session_order(
    session: DBSession,
    session_payload: Annotated[dict, Depends(_require_share_session)],
):
    svc = ShareService(session)
    token_row = await svc.load_token_from_session(session_payload)
    order_repo = OrderRepository(session)
    order = await order_repo.get_by_id(token_row.order_id)
    if order is None:
        raise NotFoundException("Order not found")

    companion = None
    companion_id = getattr(order, "companion_id", None)
    if companion_id is not None:
        from app.repositories.user import UserRepository

        companion = await UserRepository(session).get_by_id(companion_id)

    view = ShareService.build_share_order_view(
        order=order,
        share_scope=token_row.share_scope,
        companion=companion,
    )
    return ShareOrderResponse(**view)


# Public aggregation ---------------------------------------------------------

router.include_router(_orders_share_router)
router.include_router(_shares_router)
