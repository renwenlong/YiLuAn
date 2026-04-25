import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class SendOTPRequest(BaseModel):
    phone: str = Field(
        ...,
        description="中国大陆手机号，11 位数字，1[3-9] 开头",
        examples=["13800138000"],
    )

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        if not re.match(r"^1[3-9]\d{9}$", v):
            raise ValueError("Invalid phone number format")
        return v


class VerifyOTPRequest(BaseModel):
    phone: str = Field(..., description="手机号", examples=["13800138000"])
    code: str = Field(..., description="6 位短信验证码", examples=["123456"])

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        if not re.match(r"^1[3-9]\d{9}$", v):
            raise ValueError("Invalid phone number format")
        return v

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        if not re.match(r"^\d{6}$", v):
            raise ValueError("OTP code must be 6 digits")
        return v


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(
        ...,
        description="登录或上次刷新返回的 refresh_token",
        examples=["eyJhbGciOiJIUzI1NiIsInR5..."],
    )


class UserResponse(BaseModel):
    id: UUID = Field(..., description="用户 UUID")
    phone: str | None = Field(None, description="手机号；微信注册账号未绑定时为 null", examples=["13800138000"])
    role: str | None = Field(None, description="当前活跃角色", examples=["patient"])
    roles: list[str] = Field(default_factory=list, description="该账号已开通的全部角色集合", examples=[["patient", "companion"]])
    display_name: str | None = Field(None, description="昵称", examples=["小明"])
    avatar_url: str | None = Field(None, description="头像 URL")
    created_at: datetime = Field(..., description="账号创建时间")

    model_config = {"from_attributes": True}

    @field_validator("roles", mode="before")
    @classmethod
    def parse_roles(cls, v):
        if isinstance(v, str):
            return [r for r in v.split(",") if r]
        return v or []


class TokenResponse(BaseModel):
    access_token: str = Field(..., description="JWT 访问令牌（默认 1 小时过期）", examples=["eyJhbGciOi..."])
    refresh_token: str = Field(..., description="刷新令牌（默认 30 天过期，一次性使用）", examples=["eyJhbGciOi..."])
    user: UserResponse = Field(..., description="登录用户信息")


class RefreshTokenResponse(BaseModel):
    access_token: str = Field(..., description="新的 JWT 访问令牌")
    refresh_token: str = Field(..., description="新的刷新令牌（旧 token 同时失效）")


class WeChatLoginRequest(BaseModel):
    code: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="微信小程序 wx.login() 拿到的临时凭证 code",
        examples=["0a1B2cD3eFgHiJkLmN4o5P6q"],
    )


class PhoneBindRequest(BaseModel):
    phone: str = Field(..., description="待绑定手机号", examples=["13800138000"])
    code: str = Field(..., description="6 位短信验证码", examples=["123456"])

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        if not re.match(r"^1[3-9]\d{9}$", v):
            raise ValueError("Invalid phone number format")
        return v

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        if not re.match(r"^\d{6}$", v):
            raise ValueError("OTP code must be 6 digits")
        return v
