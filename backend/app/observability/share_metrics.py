"""[S2-DEV-006] Family-share token anomaly / lifecycle Prometheus 指标。

设计同其它 observability 模块: 进程级单例 + get-or-create 防重注册。

Counters:
- ``share_token_auto_revoked_total{reason}``  -- scanner 自动 revoke 的 token
    reason ∈ distinct_accessor_exceeded (24h 窗口 distinct openid > 5)
- ``share_access_logged_total``               -- 记录的家属访问次数 (审计基线)
"""
from __future__ import annotations

from typing import Iterable

from prometheus_client import REGISTRY, Counter

__all__ = [
    "SHARE_TOKEN_AUTO_REVOKED_TOTAL",
    "SHARE_ACCESS_LOGGED_TOTAL",
    "SHARE_TOKEN_CREATED_TOTAL",
    "SHARE_OTP_INVALID_TOTAL",
    "SHARE_OTP_SENT_TOTAL",
]


def _get_or_create_counter(
    name: str, doc: str, labelnames: Iterable[str]
) -> Counter:
    existing = REGISTRY._names_to_collectors.get(name)  # type: ignore[attr-defined]
    if existing is not None:
        return existing  # type: ignore[return-value]
    return Counter(name, doc, list(labelnames))


SHARE_TOKEN_AUTO_REVOKED_TOTAL: Counter = _get_or_create_counter(
    "share_token_auto_revoked",
    (
        "Family-share tokens auto-revoked by the anomaly scanner. Non-trivial "
        "values mean a token URL likely leaked (too many distinct viewers in "
        "24h). Wire an alert on rate > 0."
    ),
    ("reason",),
)

SHARE_ACCESS_LOGGED_TOTAL: Counter = _get_or_create_counter(
    "share_access_logged",
    "Family-share view accesses recorded into the audit log.",
    (),
)

SHARE_TOKEN_CREATED_TOTAL: Counter = _get_or_create_counter(
    "share_token_created",
    (
        "Family-share tokens successfully created. Denominator for the canary "
        "abuse-rate rollback gate (auto_revoked / created). Labels: share_scope."
    ),
    ("share_scope",),
)

SHARE_OTP_INVALID_TOTAL: Counter = _get_or_create_counter(
    "share_otp_invalid",
    (
        "[S2-DEV-011] Rejected OTP attempts on the iOS/H5 share fallback path. "
        "reason ∈ rate_limited (双轴频控超限) / wrong_code / expired. A spike on "
        "rate_limited = 号池滥用或链接泄露; wire to the share-abuse signal family."
    ),
    ("reason",),
)

SHARE_OTP_SENT_TOTAL: Counter = _get_or_create_counter(
    "share_otp_sent",
    "[S2-DEV-011] OTP SMS successfully dispatched via Aliyun (cost driver).",
    (),
)
