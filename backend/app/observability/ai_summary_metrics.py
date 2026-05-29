"""[S2-DEV-005] AI summary job 相关 Prometheus 指标。

设计同 ``payment_metrics`` / ``reconciliation_metrics``: 进程级单例 +
get-or-create 防重复注册。

Counters (PRD-001 §F2 + ADR-0036):
- ``ai_summary_cost_cny_total{model}``    -- 真实花掉的 ¥, 按 model 分桶
- ``ai_summary_degraded_total{reason}``   -- 降级原因, 灰度回滚阈值之一
    reason ∈ daily_budget / per_order_truncated / post_check_blocked
             / provider_failed / provider_timeout / circuit_open
- ``ai_summary_generated_total{status}``  -- ok/degraded/failed 三档
"""
from __future__ import annotations

from typing import Iterable

from prometheus_client import REGISTRY, Counter

__all__ = [
    "AI_SUMMARY_COST_CNY_TOTAL",
    "AI_SUMMARY_DEGRADED_TOTAL",
    "AI_SUMMARY_GENERATED_TOTAL",
]


def _get_or_create_counter(
    name: str, doc: str, labelnames: Iterable[str]
) -> Counter:
    existing = REGISTRY._names_to_collectors.get(name)  # type: ignore[attr-defined]
    if existing is not None:
        return existing  # type: ignore[return-value]
    return Counter(name, doc, list(labelnames))


AI_SUMMARY_COST_CNY_TOTAL: Counter = _get_or_create_counter(
    "ai_summary_cost_cny",
    (
        "Cumulative AI summary cost in CNY (yuan). Increments by the actual "
        "post-truncation price charged per generation. Labels: model "
        "(e.g. ``deepseek-chat``). Used by the daily-budget watchdog."
    ),
    ("model",),
)

AI_SUMMARY_DEGRADED_TOTAL: Counter = _get_or_create_counter(
    "ai_summary_degraded",
    (
        "AI summary generations that fell back to template / partial output. "
        "Reason label is one of: daily_budget, per_order_truncated, "
        "post_check_blocked, provider_failed, provider_timeout, circuit_open."
    ),
    ("reason",),
)

AI_SUMMARY_GENERATED_TOTAL: Counter = _get_or_create_counter(
    "ai_summary_generated",
    "AI summary generations by terminal status (ok / degraded / failed).",
    ("status",),
)
