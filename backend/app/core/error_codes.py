"""Application-wide error codes (machine-readable).

Use these constants instead of inline string literals when raising
``AppException`` with an ``error_code``. The frontend (微信小程序 / iOS)
relies on these codes to drive UX flows (e.g. redirect to bind-phone page
when ``PHONE_REQUIRED`` is returned), so they must remain stable.

Naming: SCREAMING_SNAKE_CASE, prefixed by domain. Backwards-incompatible
changes require updating the frontend dispatchers in:
- ``wechat/services/api.js`` (I18N-DEV-005: error_code → error.<CODE> i18n dispatcher; 旧误引 request.js 不存在)
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
SERVICE_PACKAGE_INVALID = "SERVICE_PACKAGE_INVALID"
"""下单时 service_type 对应的 service_packages 档位不存在或已下架 (S2-REQ-003-P3)"""

ORDER_BROADCAST_NO_REJECT = "ORDER_BROADCAST_NO_REJECT"
"""广播订单无需拒绝（其他陪诊师仍可接单）— I18N-DEV-004 接线。"""

# --- Companion ---
COMPANION_PROFILE_EXISTS = "COMPANION_PROFILE_EXISTS"
COMPANION_NOT_VERIFIED = "COMPANION_NOT_VERIFIED"

# --- Payment / refund ---
PAYMENT_REFUND_FAILED = "PAYMENT_REFUND_FAILED"
PAYMENT_PROVIDER_ERROR = "PAYMENT_PROVIDER_ERROR"

PAYMENT_ALREADY_PAID = "PAYMENT_ALREADY_PAID"
"""订单已支付，拒绝重复支付 — I18N-DEV-004 接线。"""

REFUND_ALREADY_PROCESSED = "REFUND_ALREADY_PROCESSED"
"""该订单已退款，拒绝重复退款 — I18N-DEV-004 接线。"""

REFUND_ORDER_NOT_PAID = "REFUND_ORDER_NOT_PAID"
"""原订单未支付成功，无法退款 — I18N-DEV-004 接线。"""

# --- OTP / SMS ---
OTP_INVALID = "OTP_INVALID"
OTP_LOCKED = "OTP_LOCKED"
SMS_RATE_LIMITED = "SMS_RATE_LIMITED"

OTP_SEND_FAILED = "OTP_SEND_FAILED"
"""OTP 下游短信发送失败，请稍后重试 — I18N-DEV-004 接线。"""

# --- Emergency contact ---
EMERGENCY_CONTACT_NOT_FOUND = "EMERGENCY_CONTACT_NOT_FOUND"
"""紧急联系人不存在 — I18N-DEV-004 接线。"""

EMERGENCY_CONTACT_FORBIDDEN = "EMERGENCY_CONTACT_FORBIDDEN"
"""无权操作他人紧急联系人 — I18N-DEV-004 接线。"""

# --- S2-OPS-011 火度门 feature flag 热切 ---
SHARE_F2_DISABLED = "SHARE_F2_DISABLED"
"""F2 入口已被火度手动关闭（FEATURE_SHARE_F2_ENABLED=false），拒创建新 share_token。"""

SHARE_SESSIONS_READONLY = "SHARE_SESSIONS_READONLY"
"""share session 被冻结为只读模式（READONLY_SHARE_SESSIONS=true），
拒生新会话 / 拒 WS。已发会话可继续读视图。"""

# --- S2-OPS-A-CANARY-WHITELIST-LAUNCH 火度门 (AC-2 backend) ---
SHARE_F2_CANARY_NOT_WHITELISTED = "SHARE_F2_CANARY_NOT_WHITELISTED"
"""F2 入口灰度门启用 (CANARY_WHITELIST_ENABLED=true) 但调用者手机号
不在 deploy/canary/whitelist_phones.yaml 白名单内。拒创建新 share_token。用
于 "内部白名单 10% mock 灰度上线" 场景。"""


__all__ = [
    "PHONE_REQUIRED",
    "REALNAME_REQUIRED",
    "VERIFICATION_PENDING",
    "VERIFICATION_REQUIRED",
    "PAYMENT_REQUIRED",
    "ORDER_HAS_UNPAID",
    "ORDER_NOT_FOUND",
    "ORDER_TRANSITION_INVALID",
    "SERVICE_PACKAGE_INVALID",
    "ORDER_BROADCAST_NO_REJECT",
    "COMPANION_PROFILE_EXISTS",
    "COMPANION_NOT_VERIFIED",
    "PAYMENT_REFUND_FAILED",
    "PAYMENT_PROVIDER_ERROR",
    "PAYMENT_ALREADY_PAID",
    "REFUND_ALREADY_PROCESSED",
    "REFUND_ORDER_NOT_PAID",
    "OTP_INVALID",
    "OTP_LOCKED",
    "SMS_RATE_LIMITED",
    "OTP_SEND_FAILED",
    "EMERGENCY_CONTACT_NOT_FOUND",
    "EMERGENCY_CONTACT_FORBIDDEN",
    "SHARE_F2_DISABLED",
    "SHARE_SESSIONS_READONLY",
    "SHARE_F2_CANARY_NOT_WHITELISTED",
]
