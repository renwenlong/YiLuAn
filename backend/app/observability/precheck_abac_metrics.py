"""Prometheus metric for ADR-0048 §4.3 + S3-DEV-003 design §6.3
ABAC Layer 2.5 owner-gate filter counter.

由 ``backend/app/api/v1/deps_precheck.py`` 在
:func:`assert_order_owner_or_404` 的 deny 分支 +1.

Metric:
  - ``precheck_abac_filtered_total{endpoint, user_role, filter_reason}``
    Counter — ABAC layer 2.5 deny 分支累计

Label dimensions (task `S3-DEV-003-PRECHECK-ABAC-COUNTER` AC#2):
  - ``endpoint``: precheck-status (REST) / precheck-status-ws (WS handler)
  - ``user_role``: patient / admin / companion (CurrentPatient gate
    上游已 raise 403, 但 future-proof 保留 label 维度)
  - ``filter_reason``: order_not_found / abac_owner_mismatch

灰度回滚信号 (design §6.3): alertmanager rule 监
``rate(precheck_abac_filtered_total{filter_reason="abac_owner_mismatch"}[5m]) > <threshold>``
→ 通知 PM+keqing+architect (信任度异常 / 越权枚举攻击信号).

Spec drift (PR description 详): design §4.3 line 228 老 spec
``{card, field}`` 与 task AC `{endpoint, user_role, filter_reason}` 矛盾,
按架构师 ratify (反案 #45 v3 已 surface), 实施以 task AC 为准.
"""

from __future__ import annotations

from prometheus_client import REGISTRY, Counter

_FILTERED_TOTAL_NAME = "precheck_abac_filtered_total"


def _get_or_create_counter(name: str, doc: str, labelnames: list[str]) -> Counter:
    # 防 multi-import 重复注册 (pytest collection 多 import 路径会触发).
    if name in REGISTRY._names_to_collectors:  # type: ignore[attr-defined]
        existing = REGISTRY._names_to_collectors[name]  # type: ignore[attr-defined]
        return existing  # type: ignore[return-value]
    return Counter(name, doc, labelnames)


PRECHECK_ABAC_FILTERED_TOTAL: Counter = _get_or_create_counter(
    _FILTERED_TOTAL_NAME,
    (
        "ABAC Layer 2.5 owner-gate deny 累计 (ADR-0048 §4.3 + design §6.3); "
        "labels: endpoint / user_role / filter_reason; "
        "alertmanager 监 rate>threshold → 越权枚举信号"
    ),
    ["endpoint", "user_role", "filter_reason"],
)


# Label value constants (避免 typo + IDE 补全)
FILTER_REASON_ORDER_NOT_FOUND = "order_not_found"
FILTER_REASON_ABAC_OWNER_MISMATCH = "abac_owner_mismatch"

ENDPOINT_PRECHECK_STATUS = "precheck-status"
ENDPOINT_PRECHECK_STATUS_WS = "precheck-status-ws"

USER_ROLE_PATIENT = "patient"
USER_ROLE_ADMIN = "admin"
USER_ROLE_COMPANION = "companion"


__all__ = [
    "ENDPOINT_PRECHECK_STATUS",
    "ENDPOINT_PRECHECK_STATUS_WS",
    "FILTER_REASON_ABAC_OWNER_MISMATCH",
    "FILTER_REASON_ORDER_NOT_FOUND",
    "PRECHECK_ABAC_FILTERED_TOTAL",
    "USER_ROLE_ADMIN",
    "USER_ROLE_COMPANION",
    "USER_ROLE_PATIENT",
]
