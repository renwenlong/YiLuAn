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

# WebSocket idle timeout (TD-MSG-04 / C-12).
# Incremented every time a server-side WS connection is closed because the
# client failed to send any frame within the idle window (default 90s).
ws_idle_timeout_total = Counter(
    "ws_idle_timeout_total",
    "WebSocket connections closed due to server-side idle timeout",
    ["channel"],  # "notifications" | "chat"
)

# WebSocket auth handshake outcome (PR: WS auth via first frame).
# Replaces the legacy `?token=***` query-string auth path.
# `result` values:
#   - success         : first frame was a valid {type:"auth", token:"..."}
#   - timeout         : no frame within WS_AUTH_HANDSHAKE_TIMEOUT_SECONDS
#   - invalid_frame   : first frame was not a valid auth payload (bad json /
#                       wrong type / missing token)
#   - invalid_token   : token decode/role check failed
#   - legacy_query    : connection authed via deprecated ?token= query param
#                       (transitional; will be removed once miniprogram
#                       rollout completes)
ws_auth_handshake_total = Counter(
    "ws_auth_handshake_total",
    "WebSocket auth-handshake outcomes (first-frame token rollout)",
    ["channel", "result"],
)
