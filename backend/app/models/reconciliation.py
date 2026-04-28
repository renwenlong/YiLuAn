"""[ADR-0032 / TD-MONEY-01 M1] 资金对账数据模型（3 张表 + 5 个枚举）。

参考 ADR §3.3。本模块只承载 ORM 模型与 Python 端枚举；具体业务逻辑在
``app.services.reconciliation``。
"""
import enum
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


# ---------------------------------------------------------------------------
# Enums (与 PG type 一一对齐)
# ---------------------------------------------------------------------------
class ReconRunKind(str, enum.Enum):
    full_t1 = "full_t1"
    incremental = "incremental"


class ReconRunStatus(str, enum.Enum):
    running = "running"
    success = "success"
    partial = "partial"
    failed = "failed"


class ReconDiffKind(str, enum.Enum):
    missing_payment = "missing_payment"
    orphan_payment = "orphan_payment"
    amount_mismatch = "amount_mismatch"
    status_mismatch = "status_mismatch"


class ReconDiffStatus(str, enum.Enum):
    pending = "pending"
    matched = "matched"
    mismatched = "mismatched"
    compensated = "compensated"
    closed = "closed"


class ReconActionKind(str, enum.Enum):
    auto_replay = "auto_replay"
    manual_close = "manual_close"
    manual_refund = "manual_refund"
    manual_credit = "manual_credit"
    escalate = "escalate"


def _enum(et: type[enum.Enum], name: str) -> Enum:
    return Enum(
        et,
        name=name,
        values_callable=lambda e: [m.value for m in e],
    )


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------
class ReconciliationRun(Base):
    __tablename__ = "reconciliation_runs"
    __table_args__ = (
        Index("ix_recon_runs_window", "window_start", "window_end"),
        Index("ix_recon_runs_status", "status", "started_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    kind: Mapped[ReconRunKind] = mapped_column(
        _enum(ReconRunKind, "recon_run_kind"), nullable=False
    )
    status: Mapped[ReconRunStatus] = mapped_column(
        _enum(ReconRunStatus, "recon_run_status"),
        nullable=False,
        default=ReconRunStatus.running,
    )
    window_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    window_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    orders_scanned: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    diffs_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    diffs_auto_fixed: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    triggered_by: Mapped[str] = mapped_column(String(32), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class ReconciliationDiff(Base):
    __tablename__ = "reconciliation_diffs"
    __table_args__ = (
        Index("ix_recon_diffs_status", "status", "created_at"),
        Index("ix_recon_diffs_provider_txn", "provider", "provider_txn_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("reconciliation_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    order_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_txn_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )
    kind: Mapped[ReconDiffKind] = mapped_column(
        _enum(ReconDiffKind, "recon_diff_kind"), nullable=False
    )
    status: Mapped[ReconDiffStatus] = mapped_column(
        _enum(ReconDiffStatus, "recon_diff_status"),
        nullable=False,
        default=ReconDiffStatus.pending,
    )
    business_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    payment_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    ledger_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    business_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    payment_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ledger_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    auto_retry_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ReconciliationAction(Base):
    __tablename__ = "reconciliation_actions"
    __table_args__ = (
        Index("ix_recon_actions_diff", "diff_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    diff_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("reconciliation_diffs.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[ReconActionKind] = mapped_column(
        _enum(ReconActionKind, "recon_action_kind"), nullable=False
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
