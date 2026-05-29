"""[ADR-0035 §3 P0-C / W19-P0-06] 支付回调相关 Prometheus 指标。

聚焦"回调入口异常"——空 transaction_id 这种本不该到达业务层的"无幂等键"
回调，必须在 record_callback_or_skip 层拦下并计数，以便告警/复盘看到
provider/上游网关是否在偷偷塞脏数据。

设计同 reconciliation_metrics：进程级单例 + get-or-create 避重复注册。
"""
from __future__ import annotations

from typing import Iterable

from prometheus_client import REGISTRY, Counter


__all__ = ["PAYMENT_CALLBACK_EMPTY_TXN_TOTAL"]


def _get_or_create_counter(
    name: str, doc: str, labelnames: Iterable[str]
) -> Counter:
    existing = REGISTRY._names_to_collectors.get(name)  # type: ignore[attr-defined]
    if existing is not None:
        return existing  # type: ignore[return-value]
    return Counter(name, doc, list(labelnames))


# Counter base name；prometheus 暴露为 ``payment_callback_empty_txn_total``。
PAYMENT_CALLBACK_EMPTY_TXN_TOTAL: Counter = _get_or_create_counter(
    "payment_callback_empty_txn",
    (
        "Payment callbacks rejected because the upstream payload contained "
        "no transaction_id (no idempotency key). Non-zero values indicate "
        "either a misbehaving PSP or an integration regression — investigate."
    ),
    ("provider", "callback_type"),
)
