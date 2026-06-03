"""Application-wide error codes (machine-readable).

Use these constants instead of inline string literals when raising
``AppException`` with an ``error_code``. The frontend (微信小程序 / iOS)
relies on these codes to drive UX flows (e.g. redirect to bind-phone page
when ``PHONE_REQUIRED`` is returned), so they must remain stable.

Naming: SCREAMING_SNAKE_CASE, prefixed by domain. Backwards-incompatible
changes require updating the frontend dispatchers in:
- ``wechat/services/request.js``
- ``ios/YiLuAn/Core/Networking/APIClient.swift``
"""
from __future__ import annotations

# --- Profile / account preconditions ---
PHONE_REQUIRED = "PHONE_REQUIRED"
"""User has not bound a mobile phone yet; must bind before continuing."""

REALNAME_REQUIRED = "REALNAME_REQUIRED"  # reserved for future实名校验
VERIFICATION_PENDING = "VERIFICATION_PENDING"  # reserved
VERIFICATION_REQUIRED = "VERIFICATION_REQUIRED"
"""Operation needs the user to be verified (e.g. companion qualification approved)."""

# --- Payment ---
PAYMENT_REQUIRED = "PAYMENT_REQUIRED"
"""Operation requires the user to complete payment first."""

# --- Order domain ---
ORDER_HAS_UNPAID = "ORDER_HAS_UNPAID"
ORDER_NOT_FOUND = "ORDER_NOT_FOUND"
ORDER_TRANSITION_INVALID = "ORDER_TRANSITION_INVALID"

# --- Companion ---
COMPANION_PROFILE_EXISTS = "COMPANION_PROFILE_EXISTS"
COMPANION_NOT_VERIFIED = "COMPANION_NOT_VERIFIED"

# --- Payment / refund ---
PAYMENT_REFUND_FAILED = "PAYMENT_REFUND_FAILED"
PAYMENT_PROVIDER_ERROR = "PAYMENT_PROVIDER_ERROR"

# --- OTP / SMS ---
OTP_INVALID = "OTP_INVALID"
OTP_LOCKED = "OTP_LOCKED"
SMS_RATE_LIMITED = "SMS_RATE_LIMITED"

# --- S2-OPS-011 火度门 feature flag 热切 ---
SHARE_F2_DISABLED = "SHARE_F2_DISABLED"
"""F2 入口已被火度手动关闭（FEATURE_SHARE_F2_ENABLED=false），拒创建新 share_token。"""

SHARE_SESSIONS_READONLY = "SHARE_SESSIONS_READONLY"
"""share session 被冻结为只读模式（READONLY_SHARE_SESSIONS=true），拒生新会话 / 拒 WS。已发会话可继续读视图。"""


__all__ = [
    "PHONE_REQUIRED",
    "REALNAME_REQUIRED",
    "VERIFICATION_PENDING",
    "VERIFICATION_REQUIRED",
    "PAYMENT_REQUIRED",
    "ORDER_HAS_UNPAID",
    "ORDER_NOT_FOUND",
    "ORDER_TRANSITION_INVALID",
    "COMPANION_PROFILE_EXISTS",
    "COMPANION_NOT_VERIFIED",
    "PAYMENT_REFUND_FAILED",
    "PAYMENT_PROVIDER_ERROR",
    "OTP_INVALID",
    "OTP_LOCKED",
    "SMS_RATE_LIMITED",
    "SHARE_F2_DISABLED",
    "SHARE_SESSIONS_READONLY",
]
