"""
mock-sms-stub — Staging environment Aliyun SMS mock.

Endpoints
---------
Business (mimics dysmsapi.aliyuncs.com response shape):
* POST /sms/send   {phone, code, template_id?}

Test-control:
* POST /__inject   {success, delay_ms, error_code, repeat}
* POST /__reset
* GET  /sms/__sent  历史发送日志，e2e 用
* GET  /health

Convention: the OTP code passed in is preserved in the log; staging
backend keeps the dev-style 万能码 `000000` so e2e tests can log in
without parsing the log.
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Any, Deque

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

app = FastAPI(title="mock-sms-stub", version="0.1.0")


class Inject(BaseModel):
    success: bool = True
    delay_ms: int = 50
    error_code: str | None = None
    repeat: int = 1


_inject_queue: Deque[Inject] = deque()
_default = Inject()
_sent: list[dict[str, Any]] = []


def _next_inject() -> Inject:
    if _inject_queue:
        head = _inject_queue[0]
        head.repeat -= 1
        if head.repeat <= 0:
            _inject_queue.popleft()
        return head
    return _default


@app.post("/__inject")
async def inject(body: Inject):
    _inject_queue.append(body)
    return {"queued": len(_inject_queue)}


@app.post("/__reset")
async def reset():
    _inject_queue.clear()
    _sent.clear()
    return {"ok": True}


@app.get("/sms/__sent")
async def get_sent():
    return {"count": len(_sent), "items": _sent[-200:]}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "mock-sms-stub"}


@app.post("/sms/send")
async def send(req: Request):
    try:
        body = await req.json()
    except Exception:
        body = {}

    decision = _next_inject()
    if decision.delay_ms:
        await asyncio.sleep(decision.delay_ms / 1000.0)

    record = {
        "ts": time.time(),
        "phone": body.get("phone"),
        "code": body.get("code"),
        "template_id": body.get("template_id"),
        "ok": decision.success,
        "error_code": decision.error_code if not decision.success else None,
    }
    _sent.append(record)
    if len(_sent) > 1000:
        del _sent[:500]

    if not decision.success:
        return JSONResponse(
            status_code=400,
            content={
                "Code": decision.error_code or "isv.BUSINESS_LIMIT_CONTROL",
                "Message": "mock-injected sms failure",
                "RequestId": "mock",
            },
        )
    return {
        "Code": "OK",
        "Message": "OK",
        "BizId": "mock-biz-id",
        "RequestId": "mock-req-id",
    }
