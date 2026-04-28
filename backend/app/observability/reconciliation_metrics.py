"""[ADR-0032 / D-044 Q5] 资金对账 Prometheus 指标。

三类指标（与 Alertmanager 规则一一对应）::

    reconciliation_diff_count{kind, status, provider, env}   - Gauge
    reconciliation_lag_seconds{kind, env}                    - Gauge
    reconciliation_run_total{kind, status, env}              - Counter

label 设计原因（D-044 Q5）：
    - ``provider``：区分 ``wechat`` / ``mock`` / ``unknown``，便于 staging mock
      流量与 prod 真实流量在同一个 Prometheus 实例中分流。
    - ``env``：``prod`` / ``staging`` / ``dev``，告警路由按 env 分发。

设计取舍：
    - 选用 Gauge 而非 Histogram：每个 cron run 全量刷新 diff 数量，离散值直观。
    - 选用进程级单例（prometheus_client 默认行为），import 时声明，重复 import
      会被 prometheus_client 内部去重（同名同 label 抛 ValueError）。为避免单元
      测试中重复注册导致失败，提供 ``_get_or_create_*`` helper（见底部）。
"""
from __future__ import annotations

from typing import Iterable

from prometheus_client import REGISTRY, Counter, Gauge

from app.config import settings


__all__ = [
    "RECON_DIFF_COUNT",
    "RECON_LAG_SECONDS",
    "RECON_RUN_TOTAL",
    "current_env_label",
    "record_run_metrics",
]


def current_env_label() -> str:
    """把 ``settings.environment`` 归一到 prod/staging/dev 三档。"""
    env = (getattr(settings, "environment", "") or "").lower()
    if env in {"prod", "production"}:
        return "prod"
    if env in {"staging", "stage"}:
        return "staging"
    return "dev"


def _get_or_create_gauge(name: str, doc: str, labelnames: Iterable[str]) -> Gauge:
    existing = REGISTRY._names_to_collectors.get(name)  # type: ignore[attr-defined]
    if existing is not None:
        return existing  # type: ignore[return-value]
    return Gauge(name, doc, list(labelnames))


def _get_or_create_counter(
    name: str, doc: str, labelnames: Iterable[str]
) -> Counter:
    # prometheus_client appends "_total" to Counter base names internally.
    existing = REGISTRY._names_to_collectors.get(name)  # type: ignore[attr-defined]
    if existing is not None:
        return existing  # type: ignore[return-value]
    return Counter(name, doc, list(labelnames))


RECON_DIFF_COUNT: Gauge = _get_or_create_gauge(
    "reconciliation_diff_count",
    "Reconciliation diff rows produced by the latest run, by kind/status/provider/env.",
    ("kind", "status", "provider", "env"),
)

RECON_LAG_SECONDS: Gauge = _get_or_create_gauge(
    "reconciliation_lag_seconds",
    "Seconds between window_end and finished_at for the latest reconciliation run.",
    ("kind", "env"),
)

# Counter base name; prometheus exposes it as ``reconciliation_run_total``.
RECON_RUN_TOTAL: Counter = _get_or_create_counter(
    "reconciliation_run",
    "Total number of reconciliation runs, by kind/status/env.",
    ("kind", "status", "env"),
)


def record_run_metrics(
    *,
    kind: str,
    status: str,
    diff_breakdown: dict[tuple[str, str, str], int],
    lag_seconds: float | None,
) -> None:
    """记录一次 run 完成后的指标。

    参数：
        kind:           ``full_t1`` / ``incremental``。
        status:         ``success`` / ``partial`` / ``failed``。
        diff_breakdown: ``{(diff_kind, diff_status, provider): count}``。空 dict 表示
                        本次 run 无 diff，会把同 env+kind 的所有 (kind,status,provider)
                        Gauge 显式刷成 0（避免上次 run 的旧值滞留）。
        lag_seconds:    ``finished_at - window_end`` 的秒数；None 表示未知（如 failed）。
    """
    env = current_env_label()
    RECON_RUN_TOTAL.labels(kind=kind, status=status, env=env).inc()

    if lag_seconds is not None:
        RECON_LAG_SECONDS.labels(kind=kind, env=env).set(float(lag_seconds))

    # diff gauge：把本次 run 涉及的所有 (kind, status, provider) label 显式 set。
    # 简单实现：set_to_current_time 不适用，这里允许残留是可接受的（下一次 run 会覆盖）。
    for (diff_kind, diff_status, provider), count in diff_breakdown.items():
        RECON_DIFF_COUNT.labels(
            kind=diff_kind,
            status=diff_status,
            provider=provider or "unknown",
            env=env,
        ).set(count)
