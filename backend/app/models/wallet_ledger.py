"""[ADR-0032 / TD-MONEY-01 M1] 钱包追加式账本（wallet_ledger）。

把钱包从「派生型」（从 orders 即时聚合）升级为「追加式账本」：
- 余额 = SUM(amount * sign(direction))
- 由 ``provider_txn_id, direction`` 唯一索引保证幂等
- 由支付/退款成功事件单向驱动写入，永不就地修改
"""
import enum
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class WalletLedgerDirection(str, enum.Enum):
    """资金方向：in = 入账（收入 / 退款返还）, out = 出账（支出 / 提现）。"""

    in_ = "in"
    out = "out"


class WalletLedgerReason(str, enum.Enum):
    """记账原因，与 provider 事件类型对齐。"""

    pay = "pay"
    refund = "refund"
    adjust = "adjust"


class WalletLedger(Base):
    __tablename__ = "wallet_ledger"
    __table_args__ = (
        UniqueConstraint(
            "provider_txn_id",
            "direction",
            name="uq_wallet_ledger_provider_txn_direction",
        ),
        Index("ix_wallet_ledger_user_id", "user_id"),
        Index("ix_wallet_ledger_order_id", "order_id"),
        Index("ix_wallet_ledger_occurred_at", "occurred_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    order_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )
    provider_txn_id: Mapped[str] = mapped_column(String(128), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    direction: Mapped[WalletLedgerDirection] = mapped_column(
        Enum(
            WalletLedgerDirection,
            name="wallet_ledger_direction",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    reason: Mapped[WalletLedgerReason] = mapped_column(
        Enum(
            WalletLedgerReason,
            name="wallet_ledger_reason",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
