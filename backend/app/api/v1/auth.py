from fastapi import APIRouter, Request

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


@router.post("/send-otp", summary="发送验证码", description="向指定手机号发送短信验证码，用于登录或绑定手机。")
@limiter.limit("5/minute")
async def send_otp(body: SendOTPRequest, request: Request, session: DBSession):
    service = AuthService(session, request.app.state.redis)
    await service.send_otp(body.phone)
    return {"message": "OTP sent successfully"}


@router.post("/verify-otp", response_model=TokenResponse, summary="验证短信验证码", description="校验手机号和验证码，验证通过后返回JWT令牌对。首次登录自动注册。")
async def verify_otp(body: VerifyOTPRequest, request: Request, session: DBSession):
    service = AuthService(session, request.app.state.redis)
    return await service.verify_otp(body.phone, body.code)


@router.post("/refresh", response_model=RefreshTokenResponse, summary="刷新令牌", description="使用refresh_token换取新的access_token。")
async def refresh_token(body: RefreshTokenRequest, request: Request, session: DBSession):
    service = AuthService(session, request.app.state.redis)
    return await service.refresh_token(body.refresh_token)


@router.post("/wechat-login", response_model=TokenResponse, summary="微信登录", description="使用微信授权code登录，后端调用微信code2session接口完成认证。")
async def wechat_login(body: WeChatLoginRequest, request: Request, session: DBSession):
    service = AuthService(session, request.app.state.redis)
    return await service.wechat_login(body.code)


@router.post("/bind-phone", response_model=UserResponse, summary="绑定手机号", description="已登录用户绑定手机号，需提供手机号和短信验证码。")
async def bind_phone(
    body: PhoneBindRequest,
    request: Request,
    session: DBSession,
    current_user: CurrentUser,
):
    service = AuthService(session, request.app.state.redis)
    user = await service.bind_phone(current_user.id, body.phone, body.code)
    return UserResponse.model_validate(user)
