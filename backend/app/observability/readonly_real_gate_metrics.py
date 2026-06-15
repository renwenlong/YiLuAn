"""Prometheus metrics for ADR-0053 §AC#6 read-only flag real T-7 cron gate.

由 ``backend/app/cron/readonly_flag_real_gate.py`` 在每轮 cron 跑后 +1.

Metric:
  - ``readonly_real_gate_run_total{result}`` Counter — 每轮跑结果 (GO/NOGO)
  - ``readonly_real_gate_nogo_total{reason}`` Counter — NOGO 细分原因

alertmanager rule 监 ``rate(readonly_real_gate_nogo_total[1d]) > 0`` →
通知 PM+keqing+architect (哨兵 1 红).
"""

from __future__ import annotations

from prometheus_client import REGISTRY, Counter

_RUN_TOTAL_NAME = "readonly_real_gate_run_total"
_NOGO_TOTAL_NAME = "readonly_real_gate_nogo_total"


def _get_or_create_counter(name: str, doc: str, labelnames: list[str]) -> Counter:
    # 防 multi-import 重复注册 (pytest collection 多 import 路径会触发).
    if name in REGISTRY._names_to_collectors:  # type: ignore[attr-defined]
        existing = REGISTRY._names_to_collectors[name]  # type: ignore[attr-defined]
        return existing  # type: ignore[return-value]
    return Counter(name, doc, labelnames)


READONLY_REAL_GATE_RUN_TOTAL: Counter = _get_or_create_counter(
    _RUN_TOTAL_NAME,
    "ADR-0053 read-only real T-7 cron gate 每轮跑结果 (GO/NOGO)",
    ["result"],
)

READONLY_REAL_GATE_NOGO_TOTAL: Counter = _get_or_create_counter(
    _NOGO_TOTAL_NAME,
    (
        "ADR-0053 read-only real T-7 cron gate NOGO 细分原因 — "
        "alertmanager rule 监 rate>0 → 通知 PM+keqing+architect (\u54e8\u5175 1 \u7ea2)"
    ),
    ["reason"],
)


__all__ = [
    "READONLY_REAL_GATE_NOGO_TOTAL",
    "READONLY_REAL_GATE_RUN_TOTAL",
]
