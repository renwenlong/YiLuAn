"""Service contract ORM model (S3-DEV-001-CONTRACT-DOMAIN / ADR-0047 §3.1).

# Domain context

S3 阶段陪诊订单生效时生成"陪诊服务合同 PDF"。本表是合同的**唯一权威**:
- 一单一合同 (UNIQUE order_id, 不允许重复生成)
- contract_hash UNIQUE (防双写竞争)
- hash_inputs JSONB NOT NULL (一次性冻结 hash 原材料, ADR-0046 §3.2)
- 8 immutable 字段 + DB trigger guard (ADR-0046 §3.3 第 3 层 WORM 防御)
- 6 状态 ContractStateMachine (含失败补偿 + 灰度作废)

# Layered WORM defense (ADR-0046 §3.3)

| Layer | Defense |
|-------|---------|
| 1. Storage | Azure immutable policy Locked 7y (CONTRACT-STORAGE 落地) |
| 2. App     | put_if_absent + already_exists 幂等 (CONTRACT-STORAGE 落地) |
| 3. **DB**  | **immutable_fields trigger 拒 8 字段 UPDATE** (本 task) |
| 4. API     | No PUT /admin/contracts/{id}; admin GET only (CONTRACT-API task) |

本模块负责 Layer 3 (DB trigger) + ORM 表示 + 状态机字段。
合同实际写入流程见 ContractStateMachine + ContractService (CONTRACT-API task).

# Immutable vs mutable 字段 (ADR-0047 §3.1 + 魈 08:25 AC#2)

| Field | Mutable? | Reason |
|-------|----------|--------|
| id                       | NO  | PK |
| order_id                 | NO  | 合同与订单 1:1 绑定不可改 |
| template_version         | NO  | 历史合同模板版本冻结 |
| contract_hash            | NO  | 合同防篡改核心 |
| hash_inputs              | NO  | hash 验证原材料必须冻结 |
| storage_blob_path        | NO  | WORM blob path 不可换 |
| generated_at             | NO  | 生成时间冻结 (审计) |
| created_at               | NO  | 行创建时间冻结 |
| is_immutable             | NO  | WORM 标记本身不可关 |
| status                   | YES | 状态机推进 / 灰度作废 |
| retry_count              | YES | 补偿 cron 维护 |
| last_error_trace         | YES | 补偿 cron 维护 |
| invalidation_reason      | YES | manually_invalidated 留痕 |
| invalidated_by_admin_id  | YES | manually_invalidated 留痕 |
| invalidated_at           | YES | manually_invalidated 留痕 |
| updated_at               | YES | 自动维护 |
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ContractStatus(str, enum.Enum):
    """Contract lifecycle states (ADR-0047 §3.1, 6 states ground truth)."""

    pending_generation = "pending_generation"
    """初始: 支付成功后未开始生成 (apscheduler cron 待 pickup)."""

    generating = "generating"
    """apscheduler cron job 持锁中, 正在调 ContractStorage.put_contract()."""

    active = "active"
    """成功生成 + WORM 已存; 用户/陪诊师/admin 可读签名 URL."""

    generation_failed = "generation_failed"
    """单次生成失败 (vendor API 错 / IO 错), 可重试; retry_count 维护."""

    generation_permanently_failed = "generation_permanently_failed"
    """3 次重试全失败, 不可再重试; admin alert 触发 (alertmanager)."""

    manually_invalidated = "manually_invalidated"
    """灰度回滚 / 客服手动作废 (合同 blob 不删, 仅状态变更);
    必填 invalidation_reason + invalidated_by_admin_id."""


# admin_users.id is BigInteger in PG / Integer in SQLite (see app.models.admin_user._ID_TYPE).
_ADMIN_ID_TYPE = BigInteger().with_variant(Integer(), "sqlite")


# PostgreSQL JSONB type with SQLite JSON fallback (for default test fixtures).
_JsonbType = JSONB().with_variant(JSON(), "sqlite")


class ServiceContract(Base):
    """Service contract record (一单一合同, ADR-0047 §3.1).

    Lifecycle owned by :class:`ContractStateMachine`. Direct ORM
    mutation of 8 immutable fields is blocked at the DB layer by
    ``immutable_fields_guard`` trigger (created in Alembic
    ``d5e6f7a8b9c1`` migration); 7 mutable fields can be UPDATEd
    freely.
    """

    __tablename__ = "service_contracts"

    # ----- Composite partial index (compensation cron scan) -----
    #
    # Mirrors raw DDL in alembic d5e6f7a8b9c1 migration:
    #   CREATE INDEX idx_service_contracts_compensation
    #     ON service_contracts(status, retry_count, updated_at)
    #     WHERE status IN ('pending_generation', 'generation_failed')
    #
    # Declared here so ``alembic check`` does not detect drift. SQLite
    # fallback (no partial index) handled by migration body branch.
    __table_args__ = (
        Index(
            "idx_service_contracts_compensation",
            "status",
            "retry_count",
            "updated_at",
            postgresql_where=text(
                "status IN ('pending_generation', 'generation_failed')"
            ),
        ),
    )

    # ----- Immutable fields (DB trigger guards UPDATE) -----

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)

    order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("orders.id"),
        nullable=False,
        unique=True,
        index=True,
        comment="一单一合同 UNIQUE (ADR-0047 §3.1, immutable)",
    )

    template_version: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="合同模板 semver, 如 'v1.0.0'; 入 hash_inputs (immutable)",
    )

    contract_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
        comment="SHA-256 hex 64-char, ADR-0046 §3.2 公式; UNIQUE 防双写 (immutable)",
    )

    hash_inputs: Mapped[dict] = mapped_column(
        _JsonbType,
        nullable=False,
        comment="ADR-0046 §3.2 hash 原材料 snapshot, 一次性冻结 (immutable)",
    )

    storage_blob_path: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
        comment="contracts/{YYYY}/{MM}/{order_id}_{hash}.pdf; pending 时 NULL (immutable 一旦写入)",
    )

    generated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="status=active 时设; 后续 immutable (审计)",
    )

    is_immutable: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        comment="WORM 标记本身不可关 (ADR-0046 §3.3 第 3 层)",
    )

    # ----- Mutable fields (state machine maintains) -----

    status: Mapped[ContractStatus] = mapped_column(
        Enum(ContractStatus, name="contract_status"),
        nullable=False,
        default=ContractStatus.pending_generation,
        server_default=ContractStatus.pending_generation.value,
        index=True,
        comment="ContractStateMachine 维护; 6 状态; 直接 UPDATE 禁",
    )

    retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="补偿 cron retry 次数 (5min/30min/2h 三档, 上限 3 → permanently_failed)",
    )

    last_error_trace: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="最近一次失败的 error trace; 补偿 cron 写入",
    )

    invalidation_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="作废原因; status=manually_invalidated 时**必填**",
    )

    invalidated_by_admin_id: Mapped[int | None] = mapped_column(
        _ADMIN_ID_TYPE,
        ForeignKey("admin_users.id"),
        nullable=True,
        comment=(
            "作废人 admin_user_id (BigInt PG / Int SQLite); "
            "status=manually_invalidated 时**必填**"
        ),
    )

    invalidated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="作废时间",
    )

    # ----- Audit timestamps -----

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        comment="行创建时间; immutable",
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
        comment="行更新时间; 自动维护",
    )


# Immutable field names — single source of truth for both the Python-side
# guard helper (used by ContractStateMachine) and the SQL trigger body.
#
# AC#2 字面 (魈 08:25): 8 immutable 字段 — order_id / template_version /
# contract_hash / hash_inputs / storage_blob_path / created_at /
# generated_at / is_immutable。 (``id`` 不在列里 — PK 由 DB 物理 immutable
# 兜底，不在应用层 trigger 重复 guard。)
#
# AC#2 字面 "5 mutable" 是数错 — 实际列了 6 个 mutable 加 updated_at = 7 个。
# 按 list 内容走 (status / retry_count / last_error_trace /
# invalidation_reason / invalidated_by_admin_id / invalidated_at /
# updated_at)。
IMMUTABLE_FIELDS: frozenset[str] = frozenset(
    {
        "order_id",
        "template_version",
        "contract_hash",
        "hash_inputs",
        "storage_blob_path",
        "generated_at",
        "is_immutable",
        "created_at",
    }
)

MUTABLE_FIELDS: frozenset[str] = frozenset(
    {
        "status",
        "retry_count",
        "last_error_trace",
        "invalidation_reason",
        "invalidated_by_admin_id",
        "invalidated_at",
        "updated_at",
    }
)


__all__ = [
    "IMMUTABLE_FIELDS",
    "MUTABLE_FIELDS",
    "ContractStatus",
    "ServiceContract",
]
