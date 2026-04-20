"""Abstract base class + DTOs for payment providers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class OrderDTO:
    """Lightweight order view passed to a provider.

    Decoupled from ORM ``Order`` so providers don't depend on DB models.
    """

    order_number: str
    amount_yuan: float
    description: str = "医路安陪诊服务"
    openid: str | None = None


@dataclass
class RefundDTO:
    """Refund request data."""

    trade_no: str
    refund_id: str
    total_yuan: float
    refund_yuan: float


class PaymentProvider:
    """
    Abstract base for payment providers.

    New high-level API (preferred for new code):

      * ``create_order(order)`` — request a prepay/transaction at the PSP
      * ``verify_callback(headers, body)`` — verify + decrypt incoming notify
      * ``refund(refund)`` — submit a refund
      * ``query(order)`` — query the latest transaction status

    Legacy API (kept for current ``PaymentService`` & tests):

      * ``create_prepay(order_number, amount_yuan, description, openid)``
      * ``create_refund(trade_no, refund_id, total_yuan, refund_yuan)``

    Subclasses should override the new high-level methods. The legacy
    methods on the base class delegate to those.
    """

    # ---- new high-level API -------------------------------------------------

    async def create_order(self, order: OrderDTO) -> dict[str, Any]:
        raise NotImplementedError

    async def verify_callback(
        self, headers: dict, body: bytes
    ) -> dict[str, Any]:
        raise NotImplementedError

    async def refund(self, refund: RefundDTO) -> dict[str, Any]:
        raise NotImplementedError

    async def query(self, order: OrderDTO) -> dict[str, Any]:
        raise NotImplementedError

    async def close_order(self, out_trade_no: str) -> dict[str, Any]:
        """Close a prepay order at the PSP so it can no longer be paid."""
        raise NotImplementedError

    # ---- legacy API (delegates) --------------------------------------------

    async def create_prepay(
        self,
        order_number: str,
        amount_yuan: float,
        description: str,
        openid: str | None = None,
    ) -> dict[str, Any]:
        return await self.create_order(
            OrderDTO(
                order_number=order_number,
                amount_yuan=amount_yuan,
                description=description,
                openid=openid,
            )
        )

    async def create_refund(
        self,
        trade_no: str,
        refund_id: str,
        total_yuan: float,
        refund_yuan: float,
    ) -> dict[str, Any]:
        return await self.refund(
            RefundDTO(
                trade_no=trade_no,
                refund_id=refund_id,
                total_yuan=total_yuan,
                refund_yuan=refund_yuan,
            )
        )
