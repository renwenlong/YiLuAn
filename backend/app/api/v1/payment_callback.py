"""
Payment callback endpoints.

These endpoints are called by WeChat Pay servers (not by authenticated
users), so they do NOT require JWT auth. Signature verification is
delegated to the configured ``PaymentProvider`` (see
``app.services.providers.payment``).

Idempotency
-----------
Both endpoints write a row to ``payment_callback_log`` keyed by
``(provider, transaction_id)`` *before* mutating any business state.
A duplicate delivery (WeChat retries up to 8 times over 24h) hits the
unique constraint, the insert is rolled back via SAVEPOINT, and the
endpoint returns SUCCESS without re-applying state.
"""

import json
import logging

from fastapi import APIRouter, Request, Response

from app.dependencies import DBSession
from app.exceptions import BadRequestException
from app.models.order import OrderStatus
from app.repositories.order import OrderRepository
from app.services.payment_service import (
    MockPaymentProvider,
    PaymentService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["payment-callbacks"])


def _success_response() -> Response:
    return Response(
        content=json.dumps({"code": "SUCCESS", "message": "OK"}),
        status_code=200,
        media_type="application/json",
    )


def _fail_response(msg: str) -> Response:
    # Note: still status 200 — WeChat treats non-200 as "please retry";
    # for genuinely-bad callbacks (signature errors etc.) we want to
    # acknowledge so they stop, but log the failure loudly.
    return Response(
        content=json.dumps({"code": "FAIL", "message": msg[:200]}),
        status_code=200,
        media_type="application/json",
    )


@router.post("/wechat/callback")
async def wechat_pay_callback(
    request: Request,
    session: DBSession,
):
    """WeChat Pay (or mock) payment notification endpoint."""
    body = await request.body()
    headers = dict(request.headers)

    svc = PaymentService(session)
    provider_name = "mock" if isinstance(svc.provider, MockPaymentProvider) else "wechat"

    try:
        # 1) Verify signature + decrypt payload (provider-specific).
        try:
            data = await svc.provider.verify_callback(headers, body)
        except BadRequestException as e:
            # Bad signature / expired timestamp / etc. — reject explicitly.
            logger.warning(
                "Pay callback verification rejected: %s",
                e.detail if hasattr(e, "detail") else e,
            )
            return _fail_response(
                str(e.detail) if hasattr(e, "detail") else str(e)
            )

        # 2) Extract identifiers used for routing & idempotency.
        resource = data.get("resource", data)
        trade_no = (
            resource.get("transaction_id")
            or resource.get("trade_no")
            or resource.get("out_trade_no")
            or ""
        )
        out_trade_no = resource.get("out_trade_no", "") or trade_no
        trade_state = resource.get("trade_state", "SUCCESS")
        success = trade_state == "SUCCESS"

        if not trade_no:
            logger.warning("Pay callback missing trade_no: %s", data)
            return _success_response()

        # 3) Idempotency gate — drop duplicates with SUCCESS.
        is_new = await svc.record_callback_or_skip(
            provider=provider_name,
            transaction_id=trade_no,
            callback_type="pay",
            out_trade_no=out_trade_no,
            raw_body=body,
        )
        if not is_new:
            logger.info(
                "Duplicate pay callback ignored: trade_no=%s", trade_no
            )
            return _success_response()

        # 4) Apply business mutation.
        payment = await svc.handle_pay_callback(
            trade_no=trade_no,
            order_number=out_trade_no,
            success=success,
        )
        if payment:
            payment.callback_raw = body.decode(errors="replace")[:4000]
            await session.flush()

        # 5) Defensive auto-refund: if payment succeeded but the order is
        #    already EXPIRED or CANCELLED, refund immediately instead of
        #    letting funds sit unclaimed.
        if payment and payment.status == "success" and success:
            _terminal = {
                OrderStatus.expired,
                OrderStatus.cancelled_by_patient,
                OrderStatus.cancelled_by_companion,
                OrderStatus.rejected_by_companion,
            }
            order_repo = OrderRepository(session)
            order = await order_repo.get_by_id(payment.order_id)
            if order and order.status in _terminal:
                logger.warning(
                    "late_callback_after_expire: order=%s status=%s "
                    "trade_no=%s — triggering auto-refund",
                    order.id,
                    order.status.value,
                    trade_no,
                )
                try:
                    await svc.create_refund(
                        order_id=order.id,
                        user_id=payment.user_id,
                        original_amount=order.price,
                        refund_amount=order.price,
                    )
                    logger.info(
                        "Auto-refund issued for late callback: order=%s",
                        order.id,
                    )
                except BadRequestException as refund_err:
                    # Already refunded or payment not in success — log but ack
                    logger.error(
                        "Auto-refund failed for late callback: order=%s err=%s",
                        order.id,
                        refund_err.detail,
                    )
                except Exception as refund_err:
                    logger.error(
                        "Auto-refund unexpected error: order=%s err=%s",
                        order.id,
                        refund_err,
                        exc_info=True,
                    )

        logger.info(
            "Pay callback processed: trade_no=%s success=%s",
            trade_no,
            success,
        )

    except Exception as e:  # noqa: BLE001
        logger.error("Pay callback error: %s", e, exc_info=True)
        return _fail_response(str(e))

    return _success_response()


@router.post("/wechat/refund-callback")
async def wechat_refund_callback(
    request: Request,
    session: DBSession,
):
    """WeChat Pay refund notification endpoint."""
    body = await request.body()
    headers = dict(request.headers)

    svc = PaymentService(session)
    provider_name = "mock" if isinstance(svc.provider, MockPaymentProvider) else "wechat"

    try:
        try:
            data = await svc.provider.verify_callback(headers, body)
        except BadRequestException as e:
            logger.warning(
                "Refund callback verification rejected: %s",
                e.detail if hasattr(e, "detail") else e,
            )
            return _fail_response(
                str(e.detail) if hasattr(e, "detail") else str(e)
            )

        resource = data.get("resource", data)
        refund_id = (
            resource.get("out_refund_no")
            or resource.get("refund_id")
            or ""
        )
        out_trade_no = resource.get("out_trade_no", "")
        refund_status = resource.get("refund_status", "SUCCESS")

        if not refund_id:
            logger.warning("Refund callback missing refund_id: %s", data)
            return _success_response()

        is_new = await svc.record_callback_or_skip(
            provider=provider_name,
            transaction_id=refund_id,
            callback_type="refund",
            out_trade_no=out_trade_no or None,
            raw_body=body,
        )
        if not is_new:
            logger.info(
                "Duplicate refund callback ignored: refund_id=%s",
                refund_id,
            )
            return _success_response()

        logger.info(
            "Refund callback: refund_id=%s status=%s",
            refund_id,
            refund_status,
        )

        payment = await svc.handle_refund_callback(
            refund_id=refund_id,
            refund_status=refund_status,
            raw_body=body.decode(errors="replace"),
        )

    except Exception as e:  # noqa: BLE001
        logger.error("Refund callback error: %s", e, exc_info=True)
        return _fail_response(str(e))

    return _success_response()
