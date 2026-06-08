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

# S3-DEV-001 / ADR-0046 §3.3: Contract storage put errors (non-EEXIST OSError).
# errno labels: EACCES / EROFS / ENOSPC / OTHER. EEXIST 不计 (是 normal already_exists 路径)。
contract_storage_put_error_total = Counter(
    "contract_storage_put_error_total",
    "ContractStorage put errors (non-EEXIST OSError)",
    ["errno"],  # "EACCES" | "EROFS" | "ENOSPC" | "OTHER"
)

# S3-DEV-001-CONTRACT-SERVICE-CORE / ADR-0046 r5 §3 amend:
# ContractService method outcome counters.
contract_service_request_generation_total = Counter(
    "contract_service_request_generation_total",
    "ContractService.request_generation outcomes",
    ["outcome"],  # "created" | "already_exists" | "error"
)
contract_service_generate_now_total = Counter(
    "contract_service_generate_now_total",
    "ContractService.generate_now outcomes",
    ["outcome"],  # "success" | "failed" | "already_active" | "invalid_state"
)
contract_service_retry_failed_total = Counter(
    "contract_service_retry_failed_total",
    "ContractService.retry_failed outcomes (WORM-COMPENSATION cron)",
    ["outcome"],  # "requeued" | "permanently_failed" | "skipped" | "success"
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
