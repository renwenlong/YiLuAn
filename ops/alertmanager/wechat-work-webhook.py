"""WeChat Work (企业微信) webhook adapter for Alertmanager.

Receives Alertmanager webhook payloads on POST /alert, formats them as
WeChat Work group-bot markdown messages, and forwards them to the
WECHAT_WORK_WEBHOOK_URL. If the env var is unset, runs in dry-run mode
(messages are logged but not sent).

Rate limiting: at most 3 messages per alertname per 60 seconds.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import defaultdict, deque
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request

logger = logging.getLogger("wechat-work-webhook")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

WECHAT_WORK_WEBHOOK_URL = os.environ.get("WECHAT_WORK_WEBHOOK_URL", "").strip()
RATE_LIMIT_MAX = int(os.environ.get("WECHAT_RATE_LIMIT_MAX", "3"))
RATE_LIMIT_WINDOW_SEC = int(os.environ.get("WECHAT_RATE_LIMIT_WINDOW_SEC", "60"))

app = FastAPI(title="wechat-work-webhook", version="0.1.0")

# In-memory rate limiter: alertname -> deque of timestamps within the window.
_rate_state: dict[str, deque[float]] = defaultdict(deque)
_rate_lock = asyncio.Lock()


def _is_dry_run() -> bool:
    return not WECHAT_WORK_WEBHOOK_URL


def format_alert_markdown(payload: dict[str, Any]) -> str:
    """Convert an Alertmanager webhook payload into a WeChat Work markdown body.

    Pure function — no I/O — to make it trivial to unit-test.
    """
    status = payload.get("status", "firing")
    group_labels = payload.get("groupLabels") or {}
    common_labels = payload.get("commonLabels") or {}
    alerts = payload.get("alerts") or []
    external_url = payload.get("externalURL", "")

    alertname = group_labels.get("alertname") or common_labels.get("alertname") or "unknown"
    severity = common_labels.get("severity", "warning")
    service = common_labels.get("service", "-")
    instance = common_labels.get("instance", "-")

    title_emoji = "🔥" if status == "firing" else "✅"
    status_label = "告警触发" if status == "firing" else "告警恢复"

    lines: list[str] = []
    lines.append(f"## {title_emoji} {status_label}: {alertname}")
    lines.append("")
    lines.append(f"- **级别:** {severity}")
    lines.append(f"- **服务:** {service}")
    lines.append(f"- **实例:** {instance}")

    starts_at = ""
    ends_at = ""
    if alerts:
        starts_at = alerts[0].get("startsAt", "")
        ends_at = alerts[0].get("endsAt", "")
    if starts_at:
        lines.append(f"- **起始:** {starts_at}")
    if status == "resolved" and ends_at:
        lines.append(f"- **结束:** {ends_at}")
    lines.append("")

    for alert in alerts[:5]:  # cap to keep messages WeChat-friendly
        ann = alert.get("annotations") or {}
        labels = alert.get("labels") or {}
        summary = ann.get("summary") or labels.get("alertname") or "(no summary)"
        lines.append(f"> {summary}")
        if ann.get("description"):
            lines.append(f"> {ann['description']}")
    if len(alerts) > 5:
        lines.append(f"> _… 共 {len(alerts)} 条，仅显示前 5 条_")

    if external_url:
        lines.append("")
        lines.append(f"[查看 Alertmanager]({external_url}/#/alerts)")

    return "\n".join(lines)


def to_wechat_work_payload(markdown_text: str) -> dict[str, Any]:
    """Wrap a markdown string in the WeChat Work group-bot envelope."""
    return {
        "msgtype": "markdown",
        "markdown": {"content": markdown_text},
    }


async def _check_rate_limit(alertname: str, now: float | None = None) -> bool:
    """Return True if the message is allowed, False if rate-limited."""
    now = now if now is not None else time.monotonic()
    async with _rate_lock:
        bucket = _rate_state[alertname]
        # Drop timestamps outside the window.
        cutoff = now - RATE_LIMIT_WINDOW_SEC
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= RATE_LIMIT_MAX:
            return False
        bucket.append(now)
        return True


@app.get("/healthz")
async def healthz() -> dict[str, Any]:
    return {
        "ok": True,
        "dry_run": _is_dry_run(),
        "rate_limit": {"max": RATE_LIMIT_MAX, "window_sec": RATE_LIMIT_WINDOW_SEC},
    }


@app.post("/alert")
async def receive_alert(request: Request) -> dict[str, Any]:
    try:
        payload = await request.json()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"invalid json: {exc}")

    group_labels = payload.get("groupLabels") or {}
    alertname = group_labels.get("alertname") or "unknown"

    if not await _check_rate_limit(alertname):
        logger.warning("rate limit hit for alertname=%s; dropping message", alertname)
        return {"status": "rate_limited", "alertname": alertname}

    markdown = format_alert_markdown(payload)
    wechat_payload = to_wechat_work_payload(markdown)

    if _is_dry_run():
        logger.info("[DRY-RUN] would POST to wechat-work: %s", markdown)
        return {"status": "dry_run", "alertname": alertname, "preview": markdown}

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(WECHAT_WORK_WEBHOOK_URL, json=wechat_payload)
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        logger.error("failed to POST to wechat-work: %s", exc)
        raise HTTPException(status_code=502, detail=f"upstream error: {exc}")

    return {"status": "sent", "alertname": alertname}
