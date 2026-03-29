from fastapi import APIRouter, Request

from app.dependencies import DBSession
from app.schemas.auth import (
    RefreshTokenRequest,
    RefreshTokenResponse,
    SendOTPRequest,
    TokenResponse,
    VerifyOTPRequest,
)
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/send-otp")
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
