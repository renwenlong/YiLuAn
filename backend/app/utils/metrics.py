"""
Business metrics for Prometheus (SP-03).

All counters defined here; import and .inc() from service layer.
"""

from prometheus_client import Counter

order_created_total = Counter(
    "order_created",
    "Orders created",
    ["service_type"],
)

order_paid_total = Counter(
    "order_paid",
    "Orders paid",
    ["service_type"],
)

order_cancelled_total = Counter(
    "order_cancelled",
    "Orders cancelled",
    ["service_type", "cancelled_by"],
)

payment_callback_received_total = Counter(
    "payment_callback_received",
    "Payment callbacks received",
    ["status"],
)
