"""ADR-0053 §AC#6 — Read-only flag real T-7 cron gate.

每日 02:00 UTC 跑, query prometheus 3 metric 7 天 rolling + 从 weekly
manual POST 接口拿 customer_complaint_rate, 4 条数字全过 = GO, 任一 fail
= NOGO + alert 哨兵 1 红 + 阻 real 全量推广.

任务: ``S2-OPS-A-READONLY-REAL-GATE-CRON`` (P1, 9 AC).

References:
  - ADR-0053 §AC#6 (real T-7 gate)
  - `docs/design/S2-OPS-A-readonly-metric-dashboard.md` §6 r1 amend (cron signature hint)
  - `docs/design/S2-OPS-A-readonly-metric-dashboard.md` §5.2 (real T+7 query 模板)
  - `docs/design/S2-OPS-A-readonly-metric-dashboard.md` §5.3 (客诉率 manual 注入)
  - 凝光 PM + keqing review 双推 (keqing PR #248 Q4)

调度时区: **02:00 UTC** (与 `reconcile_money` GMT+8 02:00 不一致, design §6
明示选 UTC 因 prometheus 数据 UTC, retention window 计算一致).

哨兵 1 alert: NOGO 触发 prometheus Counter `readonly_real_gate_nogo_total`
+1 → alertmanager rule 监听该 counter rate → 通知 PM+keqing+architect.

依赖:
  - prometheus HTTP API (`/api/v1/query_range`)
  - redis (客诉率 7 天 sliding window 存储 by `POST /admin/readonly/complaint-rate`)
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from app.config import settings
from app.observability.readonly_real_gate_metrics import (
    READONLY_REAL_GATE_NOGO_TOTAL,
    READONLY_REAL_GATE_RUN_TOTAL,
)
from app.services.readonly_complaint_rate_store import (
    get_complaint_rate_store,
)

logger = logging.getLogger(__name__)

# ============================================================================
# AC#3: 4 件事 thresholds — design §5.2 + §5.3
# ============================================================================

# 7 天 rolling window. design §5.2 用 [7d] PromQL.
WINDOW_DAYS = 7

# AC#3 #1: 3 metric 都查得到数据 (≥ 7 天数据存在)
# user_token_revoke_total 7d > 0 = data exists.
MIN_TOKEN_REVOKE_7D = 0  # 严格 > 0 (即 ≥ 1)

# AC#3 #2: relogin SLA ≥ 99% (design §5.2)
RELOGIN_SLA_THRESHOLD_PCT = 99.0

# AC#3 #3: session drop rate < 0.5% (design §5.2)
SESSION_DROP_RATE_THRESHOLD_PCT = 0.5

# AC#3 #4: customer complaint rate < 0.1% (design §5.3)
COMPLAINT_RATE_THRESHOLD_PCT = 0.1


# ============================================================================
# PromQL queries — design §5.2 直接 copy
# ============================================================================

PROMQL_TOKEN_REVOKE_7D = 'sum(increase(user_token_revoke_total{source="real"}[7d]))'
PROMQL_RELOGIN_SLA_7D = (
    'sum(rate(user_relogin_success_total{source="real", trigger="post_revoke"}[7d])) '
    "/ "
    "clamp_min(sum(rate(user_token_revoke_total"
    '{source="real", reason!~"credential_leak|compliance_report"}[7d])), 1e-9) '
    "* 100"
)
PROMQL_SESSION_DROP_RATE_7D = (
    'sum(rate(user_session_dropped_total{source="real", cause!="client_close"}[7d])) '
    "/ "
    'clamp_min(sum(rate(user_token_revoke_total{source="real"}[7d]) '
    '+ rate(user_relogin_success_total{source="real", trigger="passive"}[7d])), 1e-9) '
    "* 100"
)


# ============================================================================
# Result dataclass
# ============================================================================


@dataclass
class GateResult:
    """T-7 cron gate 结果. AC#6 单测 4 场景断言用."""

    go_no_go: str  # "GO" | "NOGO"
    token_revoke_7d: float | None
    relogin_sla_pct: float | None
    session_drop_rate_pct: float | None
    customer_complaint_rate_pct: float | None
    metric_deployed: dict[str, bool]
    reason: str  # NOGO 时填具体 fail 原因, GO 时为空
    ran_at: str  # ISO timestamp

    def to_dict(self) -> dict[str, Any]:
        return {
            "go_no_go": self.go_no_go,
            "token_revoke_7d": self.token_revoke_7d,
            "relogin_sla_pct": self.relogin_sla_pct,
            "session_drop_rate_pct": self.session_drop_rate_pct,
            "customer_complaint_rate_pct": self.customer_complaint_rate_pct,
            "metric_deployed": self.metric_deployed,
            "reason": self.reason,
            "ran_at": self.ran_at,
        }


# ============================================================================
# Prometheus HTTP client (minimal — 只跑 instant query)
# ============================================================================


async def _query_prometheus_instant(
    prometheus_url: str,
    query: str,
    *,
    timeout: float = 10.0,
    http_client_factory: Callable[..., httpx.AsyncClient] | None = None,
) -> float | None:
    """Run a PromQL instant query, return scalar value or None on miss/error.

    Returns None if:
      - Prometheus unreachable
      - Query returns no data ('vector' result is empty)
      - Result value not parseable as float

    Args:
        prometheus_url: e.g. "http://prometheus:9090"
        query: PromQL expression
        timeout: HTTP timeout seconds
        http_client_factory: optional injection for testing (returns AsyncClient)
    """
    url = f"{prometheus_url.rstrip('/')}/api/v1/query"
    factory = http_client_factory or (
        lambda **kw: httpx.AsyncClient(timeout=kw.get("timeout", timeout))
    )
    try:
        async with factory(timeout=timeout) as client:
            resp = await client.get(url, params={"query": query})
            resp.raise_for_status()
            payload = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning(
            "prometheus query failed: url=%s query=%s err=%s",
            url,
            query,
            exc,
        )
        return None

    if payload.get("status") != "success":
        logger.warning("prometheus non-success: %s", payload)
        return None

    result = payload.get("data", {}).get("result", [])
    if not result:
        return None

    # instant vector: result[0]['value'] = [timestamp, "value_str"]
    try:
        value_str = result[0]["value"][1]
        return float(value_str)
    except (KeyError, IndexError, ValueError, TypeError) as exc:
        logger.warning("prometheus value parse fail: %s err=%s", result, exc)
        return None


# ============================================================================
# AC#1: main cron entry
# ============================================================================


async def check_readonly_flag_real_gate(
    *,
    prometheus_url: str | None = None,
    now_fn: Callable[[], datetime] | None = None,
    http_client_factory: Callable[..., httpx.AsyncClient] | None = None,
    complaint_rate_store=None,
) -> dict[str, Any]:
    """ADR-0053 §AC#6 real T-7 cron gate 入口.

    每日 02:00 UTC 调度, 4 件事 verify:
      1. user_token_revoke_total 7d > 0 (数据存在)
      2. relogin SLA ≥ 99%
      3. session drop rate < 0.5%
      4. customer_complaint_rate < 0.1%

    全过 = GO. 任一 fail = NOGO + 哨兵 1 alert.

    Args:
        prometheus_url: override settings.prometheus_url (test inject)
        now_fn: clock injection
        http_client_factory: httpx.AsyncClient factory (test inject)
        complaint_rate_store: ComplaintRateStore (test inject; None = redis 实)

    Returns: dict (GateResult.to_dict()), 也 emit prometheus counter.
    """
    now = (now_fn or (lambda: datetime.now(timezone.utc)))()
    ran_at_iso = now.isoformat()
    prom_url = prometheus_url or settings.prometheus_url

    # === 1) prometheus 3 metric instant query ===
    token_revoke_7d = await _query_prometheus_instant(
        prom_url,
        PROMQL_TOKEN_REVOKE_7D,
        http_client_factory=http_client_factory,
    )
    relogin_sla = await _query_prometheus_instant(
        prom_url,
        PROMQL_RELOGIN_SLA_7D,
        http_client_factory=http_client_factory,
    )
    session_drop = await _query_prometheus_instant(
        prom_url,
        PROMQL_SESSION_DROP_RATE_7D,
        http_client_factory=http_client_factory,
    )

    metric_deployed = {
        "user_token_revoke_total": token_revoke_7d is not None,
        "user_relogin_sla": relogin_sla is not None,
        "user_session_dropped_total": session_drop is not None,
    }

    # === 2) customer complaint rate (manual 注入, redis 滑动 7d) ===
    store = complaint_rate_store or get_complaint_rate_store()
    complaint_rate = await store.get_rolling_average(window_days=WINDOW_DAYS)

    # === 3) AC#6 4 场景判 GO/NOGO ===
    reasons: list[str] = []

    # case 1: metric 缺失
    missing = [k for k, v in metric_deployed.items() if not v]
    if missing:
        reasons.append(f"metric_missing:{','.join(missing)}")

    # case 2: token_revoke 数据存在
    if token_revoke_7d is not None and token_revoke_7d <= MIN_TOKEN_REVOKE_7D:
        reasons.append(f"token_revoke_7d_no_data:{token_revoke_7d}<={MIN_TOKEN_REVOKE_7D}")

    # case 3: relogin SLA breach
    if relogin_sla is not None and relogin_sla < RELOGIN_SLA_THRESHOLD_PCT:
        reasons.append(f"relogin_sla_breach:{relogin_sla:.2f}<{RELOGIN_SLA_THRESHOLD_PCT}")

    # case 4: session drop breach
    if session_drop is not None and session_drop >= SESSION_DROP_RATE_THRESHOLD_PCT:
        reasons.append(f"session_drop_breach:{session_drop:.4f}>={SESSION_DROP_RATE_THRESHOLD_PCT}")

    # case 5: customer complaint breach (None = manual 未注入, 不阻 — design §5.3 接受)
    if complaint_rate is not None and complaint_rate >= COMPLAINT_RATE_THRESHOLD_PCT:
        reasons.append(
            f"complaint_rate_breach:{complaint_rate:.4f}>={COMPLAINT_RATE_THRESHOLD_PCT}"
        )

    # complaint_rate None 视 warning 不 fail — design §5.3 manual 注入 grace
    if complaint_rate is None:
        logger.info(
            "complaint_rate_not_injected: PM weekly POST /admin/readonly/complaint-rate "
            "未触发, 本轮 cron gate 视 complaint metric 为 grace (None != breach)"
        )

    go_no_go = "GO" if not reasons else "NOGO"
    reason_str = "" if not reasons else "; ".join(reasons)

    result = GateResult(
        go_no_go=go_no_go,
        token_revoke_7d=token_revoke_7d,
        relogin_sla_pct=relogin_sla,
        session_drop_rate_pct=session_drop,
        customer_complaint_rate_pct=complaint_rate,
        metric_deployed=metric_deployed,
        reason=reason_str,
        ran_at=ran_at_iso,
    )

    # === 4) AC#5: NOGO 哨兵 1 alert (prom counter, alertmanager rule 监) ===
    READONLY_REAL_GATE_RUN_TOTAL.labels(result=go_no_go).inc()
    if go_no_go == "NOGO":
        for reason in reasons:
            # 拆 reason: 'token_revoke_7d_no_data:0.0<=0' → 取 'token_revoke_7d_no_data'
            reason_key = reason.split(":", 1)[0]
            READONLY_REAL_GATE_NOGO_TOTAL.labels(reason=reason_key).inc()
        logger.warning(
            "readonly_real_gate=NOGO ran_at=%s reasons=%s details=%s",
            ran_at_iso,
            reason_str,
            result.to_dict(),
        )
    else:
        logger.info(
            "readonly_real_gate=GO ran_at=%s details=%s",
            ran_at_iso,
            result.to_dict(),
        )

    return result.to_dict()


# ============================================================================
# Convenience: 7 天窗口起算 helper (供单测 / 文档)
# ============================================================================


def window_start(now: datetime, window_days: int = WINDOW_DAYS) -> datetime:
    """Return start of the rolling window (now - window_days)."""
    return now - timedelta(days=window_days)
