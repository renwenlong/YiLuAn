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
