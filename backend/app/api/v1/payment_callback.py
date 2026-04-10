"""
Payment callback endpoints.

These endpoints are called by WeChat Pay servers (not by authenticated users),
so they do NOT require JWT auth.  Signature verification is handled inside
PaymentService / WechatPaymentProvider.
"""

import json
import logging

from fastapi import APIRouter, Request, Response

from app.dependencies import DBSession
from app.services.payment_service import PaymentService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["payment-callbacks"])


@router.post("/wechat/callback")
async def wechat_pay_callback(
    request: Request,
    session: DBSession,
):
    """
    WeChat Pay notification endpoint.

    WeChat sends POST with signed JSON body containing:
    {
      "id": "...",
      "event_type": "TRANSACTION.SUCCESS",
      "resource": { "ciphertext": "...", "nonce": "...", ... }
    }

    In mock/no-credential mode, we parse the body directly.
    """
    body = await request.body()
    headers = dict(request.headers)

    svc = PaymentService(session)

    try:
        # Verify signature and decrypt payload
        data = await svc.provider.verify_callback(headers, body)

        # Extract payment result
        # Real WeChat: resource.ciphertext decrypted contains trade info
        # Mock: body is the raw JSON
        resource = data.get("resource", data)

        trade_no = (
            resource.get("out_trade_no")
            or resource.get("trade_no")
            or ""
        )
        order_number = resource.get("out_trade_no", "")
        trade_state = resource.get("trade_state", "SUCCESS")
        success = trade_state == "SUCCESS"

        if trade_no:
            payment = await svc.handle_pay_callback(
                trade_no=trade_no,
                order_number=order_number,
                success=success,
            )
            if payment:
                # Store raw callback for audit
                payment.callback_raw = body.decode(errors="replace")[:4000]
                await session.flush()

            logger.info(
                "Pay callback processed: trade_no=%s success=%s",
                trade_no,
                success,
            )
        else:
            logger.warning("Pay callback missing trade_no: %s", data)

    except Exception as e:
        logger.error("Pay callback error: %s", e, exc_info=True)
        # Still return 200 to prevent WeChat from retrying
        return Response(
            content=json.dumps({"code": "FAIL", "message": str(e)[:200]}),
            status_code=200,
            media_type="application/json",
        )

    return Response(
        content=json.dumps({"code": "SUCCESS", "message": "OK"}),
        status_code=200,
        media_type="application/json",
    )


@router.post("/wechat/refund-callback")
async def wechat_refund_callback(
    request: Request,
    session: DBSession,
):
    """
    WeChat Pay refund notification endpoint.

    Similar structure to pay callback but event_type is REFUND.SUCCESS/REFUND.ABNORMAL.
    """
    body = await request.body()
    headers = dict(request.headers)

    svc = PaymentService(session)

    try:
        data = await svc.provider.verify_callback(headers, body)

        resource = data.get("resource", data)
        refund_id = resource.get("out_refund_no", "")
        refund_status = resource.get("refund_status", "SUCCESS")

        if refund_id:
            logger.info(
                "Refund callback: refund_id=%s status=%s",
                refund_id,
                refund_status,
            )
            # TODO: update refund Payment record status based on refund_status
        else:
            logger.warning("Refund callback missing refund_id: %s", data)

    except Exception as e:
        logger.error("Refund callback error: %s", e, exc_info=True)
        return Response(
            content=json.dumps({"code": "FAIL", "message": str(e)[:200]}),
            status_code=200,
            media_type="application/json",
        )

    return Response(
        content=json.dumps({"code": "SUCCESS", "message": "OK"}),
        status_code=200,
        media_type="application/json",
    )
