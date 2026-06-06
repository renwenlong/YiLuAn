"""ServicePackage model (S2-REQ-003-P1 / ADR-0043 §2.1)

陪诊服务档位 — 后台可配的服务类型+价格表。
替代 backend/app/models/order.py 硬编码的 ServiceType Enum + SERVICE_PRICES dict。

设计要点:
- code 全局唯一 (业务编码, Order.service_type 弱外键引用本字段)
- price 用 Decimal 遵 ADR-0030 (金额统一 Decimal)
- is_active 软删 (避免历史 Order 引用断裂)
- sort_order 升序排, seed 10/20/30 留间隙便于插档
- audit 字段 created_by/updated_by 留 admin_user_id 追溯
- 不加 FK 约束 Order.service_type → service_packages.code (弱外键避免 cascade 复杂)

acceptance:
- 我 ADR-0043 review 关切 #1: OrderService.create_order 必须从 active 列表校验 code (P3 落实)
- 我 ADR-0043 review 关切 #2: 价格快照写入事务原子 SELECT FOR UPDATE (P3 落实)

S3-DEV-001-CONTRACT-DOMAIN AC#6 sentinel (胡桃 2026-06-06 加):
- `code` 是 P0 immutable 业务编码 (do not change after first set)
- ORM @validates('code') 在代码层拒 mutate
- Order.service_type → ServicePackage.code → .id 是合同 hash 资源解析 path
- 改 code 会破历史 contract.hash_inputs.service_package_id recompute
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.database import Base


class ServicePackageCodeImmutableError(ValueError):
    """Raised when calling code tries to mutate ServicePackage.code after first set.

    AC#6 (S3-DEV-001-CONTRACT-DOMAIN) sentinel: ServicePackage.code is
    P0 immutable business identifier (不可改). Order.service_type 弱外键 →
    ServicePackage.code → .id 是合同 hash 资源解析 path (ADR-0046 §3.2 +
    魈 08:25 Option A 拍板); code 改变 → 历史 contract 重算 hash 破。

    PM 可改 ``name`` / ``price`` / ``is_active`` / ``sort_order`` / ``description`` —
    但不可改 ``code``。Admin PATCH endpoint 已在 API 层堵 (
    ``ServicePackageUpdateBody`` 不含 code 字段)，本 ORM validator
    在代码层多加一层防护 — 如 dev 误写 raw ORM update / seed 脚本
    会被拦下 (do not change after first set)。
    """


class ServicePackage(Base):
    __tablename__ = "service_packages"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    code: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True,
        comment="业务编码 (与历史 Order.service_type 兼容: full_accompany / half_accompany / errand)",  # noqa: E501
    )
    name: Mapped[str] = mapped_column(
        String(100), nullable=False,
        comment="中文显示名 (如 '全程陪诊')",
    )
    price: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False,
        comment="价格 (元, Decimal 遵 ADR-0030)",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False,
        comment="启用状态 (软删: DELETE API 实际是设 False)",
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
        comment="排序权重 (升序, seed 10/20/30 留间隙)",
    )
    description: Mapped[str | None] = mapped_column(
        String(500), nullable=True,
        comment="详情说明 (可选)",
    )

    # audit 字段
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
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True,
        comment="创建者 admin_user_id (审计)",
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True,
        comment="最近修改者 admin_user_id (审计)",
    )

    def __repr__(self) -> str:
        return (
            f"ServicePackage(id={self.id}, code={self.code!r}, name={self.name!r}, "
            f"price={self.price}, is_active={self.is_active}, sort_order={self.sort_order})"
        )

    # ------------------------------------------------------------------
    # AC#6 sentinel: ServicePackage.code is P0 immutable once first-set.
    # ------------------------------------------------------------------
    @validates("code")
    def _guard_code_immutable(self, key: str, new_value: str) -> str:
        """Reject mutation of ``code`` after the first set (immutable / 不可改 / do not change).

        First-set path: ``ServicePackage(code='full_accompany', ...)`` —
        ``self.code`` is ``None`` here, allow.

        Mutation path: ``pkg.code = 'something_else'`` — ``self.code``
        already has the prior string value, raise.

        Same-value no-op (``pkg.code = pkg.code``) is allowed — some
        seed / fixture / reload paths re-assign identical value and
        should not break.
        """
        current = getattr(self, "code", None)
        if current is None or current == new_value:
            return new_value
        raise ServicePackageCodeImmutableError(
            f"ServicePackage.code is immutable (AC#6 S3-DEV-001-CONTRACT-DOMAIN); "
            f"cannot change from {current!r} to {new_value!r}; "
            f"PM may change name/price/is_active/sort_order/description but not code"
        )
