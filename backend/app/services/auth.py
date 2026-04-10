import random
import string
from uuid import UUID

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.exceptions import BadRequestException, ConflictException, UnauthorizedException
from app.models.user import User
from app.repositories.user import UserRepository
from app.schemas.auth import RefreshTokenResponse, TokenResponse, UserResponse
from app.services.wechat import WeChatAPIClient
from app.services.sms import get_sms_provider


OTP_TTL = 300
OTP_RATE_LIMIT = 60
DEV_OTP = "000000"


class AuthService:
    def __init__(self, session: AsyncSession, redis_client: aioredis.Redis):
        self.user_repo = UserRepository(session)
        self.redis = redis_client
        self.session = session

    async def send_otp(self, phone: str) -> None:
        rate_key = f"otp:rate:{phone}"
        if await self.redis.get(rate_key):
            raise BadRequestException("Please wait 60 seconds before requesting a new code")

        code = "".join(random.choices(string.digits, k=6))

        otp_key = f"otp:{phone}"
        await self.redis.set(otp_key, code, ex=OTP_TTL)
        await self.redis.set(rate_key, "1", ex=OTP_RATE_LIMIT)

        if settings.sms_provider == "mock":
            print(f"[DEV] OTP for {phone}: {code}")
        else:
            sms = get_sms_provider()
            success = await sms.send(phone, code)
            if not success:
                raise BadRequestException("短信发送失败，请稍后重试")

    async def verify_otp(self, phone: str, code: str) -> TokenResponse:
        otp_key = f"otp:{phone}"

        is_dev = settings.environment == "development"
        if is_dev and code == DEV_OTP:
            pass
        else:
            stored_code = await self.redis.get(otp_key)
            if stored_code is None:
                raise BadRequestException("OTP code expired or not found")
            if stored_code != code:
                raise BadRequestException("Invalid OTP code")
            await self.redis.delete(otp_key)

        user = await self.user_repo.get_by_phone(phone)
        if user is None:
            user = User(phone=phone)
            user = await self.user_repo.create(user)

        if not user.is_active:
            raise UnauthorizedException("Account is disabled")

        token_data = {"sub": str(user.id), "role": user.role.value if user.role else None, "roles": user.get_roles()}
        access_token = create_access_token(token_data)
        refresh_token = create_refresh_token(token_data)

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            user=UserResponse.model_validate(user),
        )

    async def refresh_token(self, refresh_token_str: str) -> RefreshTokenResponse:
        payload = decode_token(refresh_token_str)
        if payload is None:
            raise UnauthorizedException("Invalid refresh token")

        if payload.get("type") != "refresh":
            raise UnauthorizedException("Invalid token type: expected refresh token")

        user_id = payload.get("sub")
        if not user_id:
            raise UnauthorizedException("Invalid token: missing subject")

        try:
            uid = UUID(user_id)
        except ValueError:
            raise UnauthorizedException("Invalid token: malformed subject")

        user = await self.user_repo.get_by_id(uid)
        if user is None:
            raise UnauthorizedException("User not found")
        if not user.is_active:
            raise UnauthorizedException("Account is disabled")

        token_data = {"sub": str(user.id), "role": user.role.value if user.role else None, "roles": user.get_roles()}
        new_access = create_access_token(token_data)
        new_refresh = create_refresh_token(token_data)

        return RefreshTokenResponse(access_token=new_access, refresh_token=new_refresh)

    async def wechat_login(self, code: str) -> TokenResponse:
        DEV_WX_CODE = "dev_test_code"
        DEV_WX_OPENID = "dev_openid_000"

        is_dev = settings.environment == "development"
        if is_dev and code == DEV_WX_CODE:
            openid = DEV_WX_OPENID
            unionid = None
        else:
            result = await WeChatAPIClient.code2session(code)
            openid = result["openid"]
            unionid = result.get("unionid")

        user = await self.user_repo.get_by_wechat_openid(openid)
        if user is None:
            user = User(wechat_openid=openid, wechat_unionid=unionid)
            user = await self.user_repo.create(user)

        if not user.is_active:
            raise UnauthorizedException("Account is disabled")

        token_data = {"sub": str(user.id), "role": user.role.value if user.role else None, "roles": user.get_roles()}
        access_token = create_access_token(token_data)
        refresh_token = create_refresh_token(token_data)

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            user=UserResponse.model_validate(user),
        )

    async def bind_phone(self, user_id: UUID, phone: str, code: str) -> User:
        otp_key = f"otp:{phone}"

        is_dev = settings.environment == "development"
        if is_dev and code == DEV_OTP:
            pass
        else:
            stored_code = await self.redis.get(otp_key)
            if stored_code is None:
                raise BadRequestException("OTP code expired or not found")
            if stored_code != code:
                raise BadRequestException("Invalid OTP code")
            await self.redis.delete(otp_key)

        user = await self.user_repo.get_by_id(user_id)
        if user is None:
            raise UnauthorizedException("User not found")

        if user.phone is not None:
            raise BadRequestException("User already has a phone number bound")

        existing = await self.user_repo.get_by_phone(phone)
        if existing is not None and existing.id != user.id:
            raise ConflictException("Phone number already registered to another account")

        user.phone = phone
        await self.session.flush()
        await self.session.refresh(user)
        return user
