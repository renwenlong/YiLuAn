import random
import string
from uuid import UUID

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.exceptions import BadRequestException, ConflictException, TooManyRequestsException, UnauthorizedException
from app.models.user import User
from app.repositories.user import UserRepository
from app.schemas.auth import RefreshTokenResponse, TokenResponse, UserResponse
from app.services.wechat import WeChatAPIClient
from app.services.providers.sms import (
    SMSRateLimiter,
    get_sms_provider,
    mask_phone_sms,
)


OTP_TTL = 300
OTP_RATE_LIMIT = 60  # legacy 60s key, kept for backward-compat
DEV_OTP = "000000"
OTP_FAIL_MAX = 5
OTP_FAIL_LOCK_SECONDS = 900  # 15 minutes


class AuthService:
    def __init__(self, session: AsyncSession, redis_client: aioredis.Redis):
        self.user_repo = UserRepository(session)
        self.redis = redis_client
        self.session = session

    async def send_otp(self, phone: str) -> None:
        # Per-phone rate limiting (60s + 1h windows). Backed by Redis;
        # see app.services.providers.sms.rate_limit for details.
        limiter = SMSRateLimiter(self.redis)
        decision = await limiter.check_and_record(phone)
        if not decision.allowed:
            masked = mask_phone_sms(phone)
            if decision.reason == "per_minute_exceeded":
                # Keep the legacy substring "60 seconds" so existing API
                # consumers / tests that match on it continue to work.
                raise BadRequestException(
                    f"Please wait 60 seconds before requesting a new code (retry in {decision.retry_after_seconds}s, {masked})"
                )
            raise BadRequestException(
                f"该号码 1 小时内验证码请求已达上限，请稍后再试 ({masked})"
            )

        # Legacy 60s key — kept so external observers / dashboards reading
        # otp:rate:* don't break. The new limiter is the source of truth.
        await self.redis.set(f"otp:rate:{phone}", "1", ex=OTP_RATE_LIMIT)

        code = "".join(random.choices(string.digits, k=6))
        otp_key = f"otp:{phone}"
        await self.redis.set(otp_key, code, ex=OTP_TTL)

        sms = get_sms_provider()
        result = await sms.send_otp(phone, code)
        if not result.ok:
            raise BadRequestException(
                f"短信发送失败 ({result.code})，请稍后重试"
            )

    async def verify_otp(self, phone: str, code: str) -> TokenResponse:
        fail_key = f"otp:fail:{phone}"

        # Check if locked out
        fail_count = await self.redis.get(fail_key)
        if fail_count is not None and int(fail_count) >= OTP_FAIL_MAX:
            ttl = await self.redis.ttl(fail_key)
            raise TooManyRequestsException(
                detail=f"Too many failed attempts, please try again in 15 minutes",
                retry_after=max(ttl, 0),
            )

        otp_key = f"otp:{phone}"

        is_dev = settings.environment == "development"
        if is_dev and code == DEV_OTP:
            pass
        else:
            stored_code = await self.redis.get(otp_key)
            if stored_code is None:
                await self._record_otp_failure(fail_key)
                raise BadRequestException("OTP code expired or not found")
            if stored_code != code:
                await self._record_otp_failure(fail_key)
                raise BadRequestException("Invalid OTP code")
            await self.redis.delete(otp_key)

        # Success — clear fail counter
        await self.redis.delete(fail_key)

        user = await self.user_repo.get_by_phone(phone)
        if user is None:
            user = User(phone=phone)
            user = await self.user_repo.create(user)

        if user.is_deleted:
            raise UnauthorizedException("Account has been deleted")
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

    async def _record_otp_failure(self, fail_key: str) -> None:
        count = await self.redis.incr(fail_key)
        if count == 1:
            await self.redis.expire(fail_key, OTP_FAIL_LOCK_SECONDS)

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
        if user.is_deleted:
            raise UnauthorizedException("Account has been deleted")
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

        if user.is_deleted:
            raise UnauthorizedException("Account has been deleted")
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
