from fastapi import APIRouter, Query

from app.dependencies import CurrentUser, DBSession
from app.schemas.order import PaymentResponse
from app.services.wallet import WalletService

router = APIRouter(prefix="/wallet", tags=["wallet"])


@router.get("", summary="获取钱包概览", description="获取当前用户的钱包余额和收支概览信息。")
async def get_wallet_summary(
    current_user: CurrentUser,
    session: DBSession,
):
    service = WalletService(session)
    return await service.get_summary(current_user)


@router.get("/transactions", summary="获取交易记录", description="分页查询当前用户的钱包交易流水记录。")
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
