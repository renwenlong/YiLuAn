"""
mock-pay-stub — Staging environment WeChat Pay v3 mock.

Endpoints
---------
Business (mimics api.mch.weixin.qq.com response shapes):
* POST /v3/pay/transactions/jsapi    统一下单
* POST /v3/refund/domestic/refunds   退款

Test-control:
* POST /__inject              {success, delay_ms, error_code, repeat}
* POST /__reset
* GET  /__sent                 历史调用日志
* POST /__trigger-callback    {order_number, success}
                              主动 POST 到 backend 的支付回调端点

Default behaviour: success=True, delay_ms=100, no error injection.
"""
from __future__ import annotations

import asyncio
import os
import time
import uuid
from collections import deque
from typing import Any, Deque

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import httpx
from pydantic import BaseModel, Field

app = FastAPI(title="mock-pay-stub", version="0.1.0")

BACKEND_URL = os.getenv("BACKEND_URL", "http://backend-staging:8000")
PAY_CALLBACK_PATH = os.getenv(
    "PAY_CALLBACK_PATH", "/api/v1/payments/wechat/callback"
)


class Inject(BaseModel):
    success: bool = True
    delay_ms: int = 100
    error_code: str | None = None
    repeat: int = 1


class TriggerCallback(BaseModel):
    order_number: str
    transaction_id: str | None = None
    success: bool = True


_inject_queue: Deque[Inject] = deque()
_default = Inject()
_history: list[dict[str, Any]] = []


def _next_inject() -> Inject:
    if _inject_queue:
        head = _inject_queue[0]
        head.repeat -= 1
        if head.repeat <= 0:
            _inject_queue.popleft()
        return head
    return _default


def _record(kind: str, payload: dict[str, Any]) -> None:
    _history.append(
        {"kind": kind, "ts": time.time(), "payload": payload}
    )
    # Bound history to avoid unbounded growth in long-running staging.
    if len(_history) > 1000:
        del _history[:500]


@app.post("/__inject")
async def inject(body: Inject):
    _inject_queue.append(body)
    return {"queued": len(_inject_queue)}


@app.post("/__reset")
async def reset():
    _inject_queue.clear()
    _history.clear()
    return {"ok": True}


@app.get("/__sent")
async def sent():
    return {"count": len(_history), "items": _history[-100:]}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "mock-pay-stub"}


@app.post("/v3/pay/transactions/jsapi")
async def jsapi(req: Request):
    raw = await req.body()
    try:
        body = await req.json()
    except Exception:
        body = {}
    decision = _next_inject()
    if decision.delay_ms:
        await asyncio.sleep(decision.delay_ms / 1000.0)

    _record("jsapi", {"req": body})

    if not decision.success:
        return JSONResponse(
            status_code=400,
            content={
                "code": decision.error_code or "PARAM_ERROR",
                "message": "mock-injected failure",
            },
        )

    out_trade_no = body.get("out_trade_no") or f"MOCK_{uuid.uuid4().hex[:12].upper()}"
    return {
        "prepay_id": f"mock_prepay_{out_trade_no}",
        "out_trade_no": out_trade_no,
    }


@app.post("/v3/refund/domestic/refunds")
async def refund(req: Request):
    try:
        body = await req.json()
    except Exception:
        body = {}
    decision = _next_inject()
    if decision.delay_ms:
        await asyncio.sleep(decision.delay_ms / 1000.0)

    _record("refund", {"req": body})

    if not decision.success:
        return JSONResponse(
            status_code=400,
            content={
                "code": decision.error_code or "REFUND_ERROR",
                "message": "mock-injected refund failure",
            },
        )

    return {
        "refund_id": f"mock_refund_{uuid.uuid4().hex[:16]}",
        "out_refund_no": body.get("out_refund_no", ""),
        "out_trade_no": body.get("out_trade_no", ""),
        "transaction_id": body.get("transaction_id", ""),
        "channel": "ORIGINAL",
        "status": "SUCCESS",
        "amount": body.get("amount", {}),
    }


@app.post("/__trigger-callback")
async def trigger_callback(body: TriggerCallback):
    """Synthesize a wechatpay-shaped callback and POST it to the backend.

    The MockPaymentProvider.verify_callback in backend simply parses the
    JSON body and reports verified=True, so we emit a plain JSON shape
    with the fields routed by `payment_callback.py`.
    """
    transaction_id = body.transaction_id or f"MOCK_TX_{uuid.uuid4().hex[:12].upper()}"
    payload = {
        "resource": {
            "out_trade_no": body.order_number,
            "transaction_id": transaction_id,
            "trade_state": "SUCCESS" if body.success else "FAIL",
        }
    }

    _record("trigger-callback", payload)

    url = f"{BACKEND_URL}{PAY_CALLBACK_PATH}"
    try:
        async with httpx.AsyncClient(timeout=5.0) as c:
            r = await c.post(url, json=payload)
        return {
            "ok": True,
            "url": url,
            "status_code": r.status_code,
            "response": r.text[:500],
        }
    except Exception as e:  # noqa: BLE001
        return JSONResponse(
            status_code=502,
            content={
                "ok": False,
                "url": url,
                "error": f"{type(e).__name__}: {e}",
            },
        )
