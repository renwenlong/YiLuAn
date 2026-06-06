"""Contract input resolver (S3-DEV-001-CONTRACT-DOMAIN / AC#6).

# Why a separate resolver module

CONTRACT-HASH module is **pure functions** (no DB). CONTRACT-DOMAIN owns
the orchestration: resolve runtime IDs / strings from DB rows → pass into
``generate_contract_hash_at_commit_time``.

AC#6 拍 service_package_id 解析路径 = ``Order.service_type`` (ServiceType
enum code, P0 immutable) → SELECT ``ServicePackage`` WHERE code=service_type
→ ``ServicePackage.id`` (UUID).

# Rationale (魈 08:25 拍 Option A, 不用 service_name_snapshot)

| 选项 | 评 |
|------|----|
| service_name_snapshot 字符串 | ❌ PM 可改包名 → 改名后旧 contract 重算 hash 破 |
| 加 Order.service_package_id 列 + backfill | ❌ 跨 task scope + Order schema 改 |
| **Order.service_type → ServicePackage.code → .id** | ✅ 现有 pattern + code immutable + 软删保护 |

# Fail-fast (刻晴 08:12 加 — 防 silent None 入 hash)

``ServicePackage`` row 真删 (非软删 is_active=False) → query 返 None →
我们 **raise** :class:`ContractServicePackageNotFoundError`, 让 caller
(ContractService) 走 ``status=generation_failed`` 状态 → retry cron →
3 次失败 → ``generation_permanently_failed`` + admin alert.

软删 (``is_active=False``) **不影响** id query — 我们读 .id 不读 .is_active,
历史 contract 重算 hash 仍稳定。这是 ServicePackage 软删的设计本意 (避免
历史 Order 引用断裂)。
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Order
from app.models.service_package import ServicePackage
from app.services.contract_hash import (
    ContractHashResult,
    generate_contract_hash_at_commit_time,
)
from app.services.contract_state_machine import normalize_patient_name

logger = logging.getLogger(__name__)


class ContractServicePackageNotFoundError(LookupError):
    """Raised when Order.service_type has no matching ServicePackage row.

    Caller surface (ContractService) translates this to ``status=
    generation_failed`` (ADR-0046 §3.4 retry path).
    """


# Sync protocol for static type-checking — allows both DB-backed callers
# and test fakes (e.g. stub that returns a fixed UUID).
class _ServicePackageLookup(Protocol):
    def by_code(self, code: str) -> uuid.UUID | None: ...


async def resolve_service_package_id(order: Order, session: AsyncSession) -> uuid.UUID:
    """Resolve ``Order.service_type`` (enum code str) → ``ServicePackage.id``.

    Args:
        order: Order row (must have ``service_type`` populated; enforced by
            DB NOT NULL since the column has been required since
            ``f7a8b9c0d1e2_add_service_packages``).
        session: AsyncSession bound to the same Unit-of-Work as the
            ContractService caller — so the read is in the same TX as
            the eventual ``service_contracts`` INSERT.

    Returns:
        ServicePackage.id (UUID); never None.

    Raises:
        ContractServicePackageNotFoundError: code → no row (real delete,
            not soft-delete). Caller routes contract to generation_failed.
    """
    # Order.service_type is an Enum column whose `.value` is the string code
    # (e.g. "full_accompany"). ServicePackage.code stores the same string.
    code = (
        order.service_type.value
        if hasattr(order.service_type, "value")
        else str(order.service_type)
    )
    stmt = select(ServicePackage.id).where(ServicePackage.code == code)
    result = await session.execute(stmt)
    package_id = result.scalar_one_or_none()
    if package_id is None:
        logger.error(
            "contract_resolver.service_package_not_found",
            extra={
                "order_id": str(order.id),
                "service_type_code": code,
            },
        )
        raise ContractServicePackageNotFoundError(
            f"ServicePackage with code={code!r} not found "
            f"(order_id={order.id}); cannot generate contract hash"
        )
    return package_id


__all__ = [
    "ContractServicePackageNotFoundError",
    "build_contract_hash_for_order",
    "resolve_service_package_id",
]


# ---------------------------------------------------------------------------
# AC#7 乘车入口: enforce NFKC + strip on patient_name before hash
# ---------------------------------------------------------------------------


async def build_contract_hash_for_order(
    *,
    order: Order,
    session: AsyncSession,
    amount_cny: int,
    scheduled_at: datetime | date | str,
    patient_name_raw: str,
    patient_id_card_last4: str,
    companion_id: str,
    template_version: str,
) -> ContractHashResult:
    """One-call convenience: resolve service_package_id + NFKC patient_name + hash.

    This is the **enforced entry point** for AC#7 — callers should use
    this rather than calling :func:`generate_contract_hash_at_commit_time`
    directly, because this wrapper guarantees the NFKC + .strip()
    normalization step (AC#7) and the resolver (AC#6) are both applied.

    Args mirror :func:`generate_contract_hash_at_commit_time` *except*:
        - ``service_package_id`` is **resolved** from ``order.service_type``
          via :func:`resolve_service_package_id` (AC#6 Option A path).
        - ``patient_name_raw`` is **normalized** via
          :func:`normalize_patient_name` (AC#7 — NFKC + strip) before
          being passed into the hash computation.
        - ``order_id`` is derived from ``order.id``.

    Raises:
        ContractServicePackageNotFoundError: AC#6 — ServicePackage row
            for ``order.service_type`` was real-deleted (not soft-delete).
        ValueError: AC#7 — ``patient_name_raw`` is None or whitespace-only
            after NFKC + strip.
        ContractHashGenerationError: any downstream field-validation
            failure (caller routes to ``status=generation_failed``).
    """
    service_package_id = await resolve_service_package_id(order, session)
    patient_name_normalized = normalize_patient_name(patient_name_raw)
    return generate_contract_hash_at_commit_time(
        order_id=str(order.id),
        amount_cny=amount_cny,
        service_package_id=str(service_package_id),
        scheduled_at=scheduled_at,
        patient_name=patient_name_normalized,
        patient_id_card_last4=patient_id_card_last4,
        companion_id=companion_id,
        template_version=template_version,
    )
