"""HTTP request metrics — powers the canary 5xx rollback gate (S2-OPS-001).

PRD-001 v1.2 §8.1 rollback rule #1: 5xx error rate > 2% for 30min → rollback.
That needs a per-status-class request counter scraped at /metrics. We keep it
deliberately low-cardinality: only the status *class* (2xx/3xx/4xx/5xx) and the
HTTP method, never the raw path (which would explode cardinality).
"""
from __future__ import annotations

from prometheus_client import REGISTRY, Counter


def _get_or_create_counter(name, doc, labelnames):
    existing = REGISTRY._names_to_collectors.get(name)
    if existing is not None:
        return existing
    return Counter(name, doc, list(labelnames))


HTTP_REQUESTS_TOTAL: Counter = _get_or_create_counter(
    "http_requests",
    (
        "HTTP requests served, labelled by method and status class "
        "(2xx/3xx/4xx/5xx). Denominator+numerator for the canary 5xx "
        "rollback gate."
    ),
    ("method", "status_class"),
)


def status_class(status_code: int) -> str:
    return f"{status_code // 100}xx"
