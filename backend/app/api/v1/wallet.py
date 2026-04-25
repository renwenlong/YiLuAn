from fastapi import APIRouter, Query

from app.api.v1.openapi_meta import err
from app.dependencies import CurrentUser, DBSession
from app.schemas.order import PaymentResponse
from app.services.wallet import WalletService

router = APIRouter(prefix="/wallet", tags=["wallet"])


@router.get(
    "",
    summary="获取钱包概览",
    description="返回当前用户的钱包余额、累计收入、累计支出、可提现金额等概览信息。",
    responses={
        200: {
            "description": "钱包概览",
            "content": {
                "application/json": {
                    "example": {
                        "balance": 128.50,
                        "total_income": 980.00,
                        "total_expense": 200.00,
                        "withdrawable": 100.00,
                    }
                }
            },
        },
        **err(401, 500),
    },
)
async def get_wallet_summary(
    current_user: CurrentUser,
    session: DBSession,
):
    service = WalletService(session)
    return await service.get_summary(current_user)


@router.get(
    "/transactions",
    summary="获取钱包交易流水",
    description="分页查询当前用户的钱包流水（含支付、退款、提现等记录）。",
    responses={**err(401, 422, 500)},
)
async def get_transactions(
    current_user: CurrentUser,
    session: DBSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    service = WalletService(session)
    items, total = await service.get_transactions(
        current_user, page=page, page_size=page_size
    )
    return {
        "items": [PaymentResponse.model_validate(p) for p in items],
        "total": total,
    }
