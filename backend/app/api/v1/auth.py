from fastapi import APIRouter, Request

from app.api.v1.openapi_meta import err
from app.dependencies import CurrentUser, DBSession
from app.core.rate_limit import limiter
from app.schemas.auth import (
    PhoneBindRequest,
    RefreshTokenRequest,
    RefreshTokenResponse,
    SendOTPRequest,
    TokenResponse,
    UserResponse,
    VerifyOTPRequest,
    WeChatLoginRequest,
)
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/send-otp",
    summary="发送短信验证码",
    description=(
        "向指定手机号发送 6 位短信验证码，用于登录或绑定手机号。\n\n"
        "**限流**：同一 IP 每分钟最多 5 次。\n\n"
        "**有效期**：验证码 5 分钟内有效。\n\n"
        "**幂等**：同一手机号 60 秒内重复请求会复用未过期的验证码。"
    ),
    responses={
        200: {
            "description": "已发送",
            "content": {"application/json": {"example": {"message": "OTP sent successfully"}}},
        },
        **err(422, 429, 500),
    },
)
@limiter.limit("5/minute")
async def send_otp(body: SendOTPRequest, request: Request, session: DBSession):
    service = AuthService(session, request.app.state.redis)
    await service.send_otp(body.phone)
    return {"message": "OTP sent successfully"}


@router.post(
    "/verify-otp",
    response_model=TokenResponse,
    summary="校验短信验证码并登录",
    description=(
        "校验手机号 + 6 位验证码。校验通过后：\n\n"
        "- 若手机号已注册 → 返回该用户的 JWT 令牌对；\n"
        "- 若手机号未注册 → 自动注册一个新用户后返回令牌对。\n\n"
        "返回的 `access_token` 默认 1 小时过期，`refresh_token` 默认 30 天过期。"
    ),
    responses={**err(400, 422, 500)},
)
async def verify_otp(body: VerifyOTPRequest, request: Request, session: DBSession):
    service = AuthService(session, request.app.state.redis)
    return await service.verify_otp(body.phone, body.code)


@router.post(
    "/refresh",
    response_model=RefreshTokenResponse,
    summary="刷新访问令牌",
    description=(
        "使用 `refresh_token` 换取新的 `access_token` 和 `refresh_token`。"
        "旧的 refresh_token 会被撤销（一次性使用）。"
    ),
    responses={**err(401, 422, 500)},
)
async def refresh_token(body: RefreshTokenRequest, request: Request, session: DBSession):
    service = AuthService(session, request.app.state.redis)
    return await service.refresh_token(body.refresh_token)


@router.post(
    "/wechat-login",
    response_model=TokenResponse,
    summary="微信小程序登录",
    description=(
        "通过微信小程序 `wx.login()` 拿到的临时 `code` 完成登录。"
        "后端会调用微信 `code2session` 接口获取 `openid` 并完成账号映射。"
        "首次登录会创建一个无手机号的账号，后续可通过 `/auth/bind-phone` 绑定手机号。"
    ),
    responses={**err(400, 422, 500)},
)
async def wechat_login(body: WeChatLoginRequest, request: Request, session: DBSession):
    service = AuthService(session, request.app.state.redis)
    return await service.wechat_login(body.code)


@router.post(
    "/bind-phone",
    response_model=UserResponse,
    summary="为当前账号绑定手机号",
    description=(
        "已登录用户绑定手机号，需要提供手机号 + 验证码。"
        "用于「微信注册账号」补充绑定手机号场景。"
    ),
    responses={**err(400, 401, 422, 500)},
)
async def bind_phone(
    body: PhoneBindRequest,
    request: Request,
    session: DBSession,
    current_user: CurrentUser,
):
    service = AuthService(session, request.app.state.redis)
    user = await service.bind_phone(current_user.id, body.phone, body.code)
    return UserResponse.model_validate(user)
