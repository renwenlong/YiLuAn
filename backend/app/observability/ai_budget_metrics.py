"""[S3-DEV-002] AIBudgetGuard Prometheus 指标 (ADR-0048 §3.2).

设计同 ``ai_summary_metrics``: 进程级单例 + get-or-create 防重复注册。

为什么独立模块?
----------
S2 ``ai_summary_*`` 系列已存在且**带 BC 真源**(零改名), 本模块为 S3
准备包 + 未来 axis 提供**通用 multi-axis** counter, 用 ``axis`` label
区分 (``s2_summary`` / ``s3_prep``). S2 调用方仍写老 metric 不变,
**只有走 AIBudgetGuard 路径才写新 metric** (PRD-001 §F2 + ADR-0048
§3.3 BudgetAxis enum)。

Counters
--------
- ``ai_budget_reserved_cny_total{axis}``        -- check_and_reserve 累计预扣 ¥
- ``ai_budget_committed_cny_total{axis}``       -- 实际花掉的 ¥ (release/commit diff 校准)
- ``ai_budget_check_total{axis, result}``       -- check 决策 (allow / fallback / reject)
  - allow         = 在限内 + 已预扣
  - fallback      = 软门限超 / 单订单超 → fallback template (本次不扣)
  - reject        = 硬门限超 / redis 不可用 → 拒绝调用
- ``ai_budget_threshold_alerts_total{axis, severity}`` -- threshold 触达 alert
  (info=90%, warning=100%)

Cardinality 控制
--------------
axis = ``s2_summary`` / ``s3_prep`` 两个枚举值, 未来加 axis 同步加 enum.
不允许 axis 用动态字符串。
"""
from __future__ import annotations

from typing import Iterable

from prometheus_client import REGISTRY, Counter

__all__ = [
    "AI_BUDGET_RESERVED_CNY_TOTAL",
    "AI_BUDGET_COMMITTED_CNY_TOTAL",
    "AI_BUDGET_CHECK_TOTAL",
    "AI_BUDGET_THRESHOLD_ALERTS_TOTAL",
]


def _get_or_create_counter(
    name: str, doc: str, labelnames: Iterable[str]
) -> Counter:
    """get-or-create 防 importlib reload 重复注册。"""
    existing = REGISTRY._names_to_collectors.get(name)  # type: ignore[attr-defined]
    if existing is not None:
        return existing  # type: ignore[return-value]
    return Counter(name, doc, list(labelnames))


AI_BUDGET_RESERVED_CNY_TOTAL: Counter = _get_or_create_counter(
    "ai_budget_reserved_cny",
    (
        "Cumulative AI budget reservations in CNY (yuan), by axis. "
        "Increments by ``estimated_cost_yuan`` on each "
        "``AIBudgetGuard.check_and_reserve`` success. "
        "Labels: axis (s2_summary / s3_prep)."
    ),
    ("axis",),
)

AI_BUDGET_COMMITTED_CNY_TOTAL: Counter = _get_or_create_counter(
    "ai_budget_committed_cny",
    (
        "Cumulative AI budget committed (actual) cost in CNY (yuan), by axis. "
        "Increments by ``actual_cost_yuan`` on each "
        "``AIBudgetGuard.report_actual_cost`` (可能 < reserved). "
        "Labels: axis (s2_summary / s3_prep)."
    ),
    ("axis",),
)

AI_BUDGET_CHECK_TOTAL: Counter = _get_or_create_counter(
    "ai_budget_check",
    (
        "AIBudgetGuard.check_and_reserve decisions by axis + result. "
        "result ∈ allow / fallback / reject. "
        "allow = 在限内 + 已预扣; "
        "fallback = 软门限超 (90-99%) 但仍允许, 或单订单超 → 走 template; "
        "reject = 日预算用完 (100%+) 或 redis 不可用。"
    ),
    ("axis", "result"),
)

AI_BUDGET_THRESHOLD_ALERTS_TOTAL: Counter = _get_or_create_counter(
    "ai_budget_threshold_alerts",
    (
        "AI budget threshold alerts fired by axis + severity. "
        "severity ∈ info (90% warn) / warning (100% exhausted). "
        "Alertmanager rule 监听该 counter rate 触发实际通知 "
        "(无需 backend 直接 POST webhook, 走 Prom-native path)."
    ),
    ("axis", "severity"),
)
