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


@router.post("/send-otp")
@limiter.limit("5/minute")
async def send_otp(body: SendOTPRequest, request: Request, session: DBSession):
    service = AuthService(session, request.app.state.redis)
    await service.send_otp(body.phone)
    return {"message": "OTP sent successfully"}


@router.post("/verify-otp", response_model=TokenResponse)
async def verify_otp(body: VerifyOTPRequest, request: Request, session: DBSession):
    service = AuthService(session, request.app.state.redis)
    return await service.verify_otp(body.phone, body.code)


@router.post("/refresh", response_model=RefreshTokenResponse)
async def refresh_token(body: RefreshTokenRequest, request: Request, session: DBSession):
    service = AuthService(session, request.app.state.redis)
    return await service.refresh_token(body.refresh_token)


@router.post("/wechat-login", response_model=TokenResponse)
async def wechat_login(body: WeChatLoginRequest, request: Request, session: DBSession):
    service = AuthService(session, request.app.state.redis)
    return await service.wechat_login(body.code)


@router.post("/bind-phone", response_model=UserResponse)
async def bind_phone(
    body: PhoneBindRequest,
    request: Request,
    session: DBSession,
    current_user: CurrentUser,
):
    service = AuthService(session, request.app.state.redis)
    user = await service.bind_phone(current_user.id, body.phone, body.code)
    return UserResponse.model_validate(user)
