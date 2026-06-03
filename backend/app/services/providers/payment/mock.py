"""Instant-success mock provider for dev / test."""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from typing import Any

import httpx

from app.services.providers.payment.base import (
    OrderDTO,
    PaymentProvider,
    RefundDTO,
)

logger = logging.getLogger(__name__)


class MockPaymentProvider(PaymentProvider):
    """No external calls; pretends every request succeeds immediately.

    Staging 增强 (S2-BUG-W001)：当环境变量 ``MOCK_PAY_BASE_URL`` 被设置
    为 mock-pay-stub URL 时，``create_order`` 在返回后会 fire-and-forget
    调用 mock-pay-stub 的 ``__trigger-callback`` 接口，让 backend 的
    ``/api/v1/payments/wechat/callback`` 路由真的被走一遍。

    为什么 fire-and-forget 而不阅 callback 结果：
      · ``PaymentService.create_prepay`` 在 is_mock 下已在本事务里 inline
        把 ``payment.status`` 标为 ``success`` + 写 ledger，API 响应立即能返
        回 mock_success=True。
      · 紧接着的 ``record_callback_or_skip`` 有幂等保护（`payment.status` 已为
        success 的话 handle_pay_callback short-circuit 返回），重写安全。
      · 如果 trigger 失败 / 超时，业务不应被拖垮——这只是 staging 的 咨询验证。

    单测 / e2e 不受影响：``MOCK_PAY_BASE_URL`` 未设置时，不发 trigger。
    """

    name = "mock"

    async def create_order(self, order: OrderDTO) -> dict[str, Any]:
        fake_trade = f"MOCK_{uuid.uuid4().hex[:16].upper()}"
        # Staging 增强：fire-and-forget 触发 mock-pay-stub 调真的 callback 路由
        self._maybe_trigger_staging_callback(
            order_number=order.order_number,
            transaction_id=fake_trade,
        )
        return {
            "trade_no": fake_trade,
            "prepay_id": f"mock_prepay_{fake_trade}",
            "status": "success",
        }

    def _maybe_trigger_staging_callback(
        self, *, order_number: str, transaction_id: str
    ) -> None:
        """在背景任务中调用 mock-pay-stub /__trigger-callback。

        仅当 ``MOCK_PAY_BASE_URL`` 环境变量被设置时生效。
        """
        base_url = os.getenv("MOCK_PAY_BASE_URL", "").strip().rstrip("/")
        if not base_url:
            return

        async def _trigger() -> None:
            url = f"{base_url}/__trigger-callback"
            payload = {
                "order_number": order_number,
                "transaction_id": transaction_id,
                "success": True,
            }
            try:
                async with httpx.AsyncClient(timeout=3.0) as client:
                    resp = await client.post(url, json=payload)
                    if resp.status_code >= 300:
                        logger.warning(
                            "mock-pay-stub trigger non-2xx: status=%s body=%s",
                            resp.status_code,
                            resp.text[:200],
                        )
                    else:
                        logger.info(
                            "mock-pay-stub callback triggered: order=%s trade=%s",
                            order_number,
                            transaction_id,
                        )
            except Exception as e:  # noqa: BLE001 - never raise back into business path
                logger.warning(
                    "mock-pay-stub trigger failed (non-fatal): %s", e
                )

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_trigger())
        except RuntimeError:
            # 不在 event loop 上下文（如单测同步调用）——静默跳过
            logger.debug("mock-pay-stub trigger skipped: no running loop")

    async def refund(self, refund: RefundDTO) -> dict[str, Any]:
        return {
            "refund_id": refund.refund_id,
            "status": "success",
        }

    async def verify_callback(
        self, headers: dict, body: bytes
    ) -> dict[str, Any]:
        # Try to parse the body so the endpoint can route on the embedded
        # trade_no / out_trade_no, but always advertise verified=True so
        # callers in dev/test see a stable shape.
        import json as _json

        parsed: dict[str, Any] = {}
        try:
            decoded = _json.loads(body) if body else {}
            if isinstance(decoded, dict):
                parsed = decoded
        except Exception:
            parsed = {}
        parsed.setdefault("verified", True)
        return parsed

    async def query(self, order: OrderDTO) -> dict[str, Any]:
        return {
            "out_trade_no": order.order_number,
            "trade_state": "SUCCESS",
        }

    async def close_order(self, out_trade_no: str) -> dict[str, Any]:
        return {"status": "success"}
