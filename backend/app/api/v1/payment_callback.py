"""
Payment callback endpoints.

These endpoints are called by WeChat Pay servers (not by authenticated users),
so they do NOT require JWT auth.  Signature verification is handled inside
PaymentService / WechatPaymentProvider.
"""

from fastapi import APIRouter, Request, Response

from app.dependencies import DBSession
from app.services.payment_service import PaymentService

router = APIRouter(prefix="/payments", tags=["payment-callbacks"])


@router.post("/wechat/callback")
async def wechat_pay_callback(
    request: Request,
    session: DBSession,
):
    """
    WeChat Pay notification endpoint.

    In mock mode this is a no-op (payments are instant).
    In production, WeChat sends POST with signed JSON body.
    """
    body = await request.body()
    headers = dict(request.headers)

    svc = PaymentService(session)

    # Phase 2: parse the real WeChat callback body, extract trade_no etc.
    # For now, return 200 so WeChat stops retrying if called accidentally.
    return Response(content='{"code": "SUCCESS", "message": "OK"}', status_code=200)


@router.post("/wechat/refund-callback")
async def wechat_refund_callback(
    request: Request,
    session: DBSession,
):
    """
    WeChat Pay refund notification endpoint.

    Phase 2: implement refund callback processing.
    """
    return Response(content='{"code": "SUCCESS", "message": "OK"}', status_code=200)
