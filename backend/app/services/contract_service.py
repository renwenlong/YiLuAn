"""Contract lifecycle orchestrator (S3-DEV-001-CONTRACT-SERVICE-CORE / ADR-0046 §3.x).

# Why a thin facade class

ContractService 不重复造轮子。它**只 orchestrate** 已有的 4 个模块:

- ``contract_resolver`` — 解 ``Order.service_type → ServicePackage.id`` (UUID)
  via ``resolve_service_package_id(order, session)``.
- ``contract_hash`` — pure-function hash 公式 + snapshot 构建 + pseudonym
  via ``generate_contract_hash_at_commit_time(...)`` / ``amount_cny_from_yuan``.
- ``contract_storage`` — WORM PDF put + signed URL (module pattern,
  详见 contract_storage.py docstring) via ``put_contract(...)``.
- ``contract_state_machine`` — 6-state FSM guard
  via ``assert_transition(...)`` / ``MAX_RETRY_COUNT``.

ContractService **是 contract 写路径的唯一入口** (ADR-0046 §3.x). 三个 method
对应 lifecycle 三个关键节点:

- ``request_generation`` — 调用方 ``order/lifecycle.accept_order`` (EVENT-WIRING
  hook); 动作 INSERT pending_generation 行 (immutable hash 一次性冻结).
- ``generate_now`` — 调用方 ``contract_generate_pickup`` cron (PICKUP-CRON);
  动作 pending_generation → generating → active (PDF put + 翻状态).
- ``retry_failed`` — 调用方 ``contract_compensation`` cron
  (WORM-COMPENSATION, follow-up task); 动作 generation_failed → generating
  → active (重算 retry_count).

# 设计决策 (魈拍板)

- Class vs module 函数集 → **薄 facade 类** (3 method 共享 session 参数
  减重复). 留痕 comment ``6496a8ad``.
- ``request_generation`` eligibility → **不做** (accept_order hook 时
  companion_id 必然非 None — 业务约束). 留痕 comment ``83e3007a``.
- ``request_generation`` 触发点 → **单 accept_order hook** (非 payment hook
  + accept hook 双触发). 留痕 comment ``83e3007a``.
- ``_render_pdf`` → 委托 :mod:`app.services.contract_pdf.render_contract_pdf`
  (S3-DEV-001-CONTRACT-PDF-RENDER uuid ``33ac1174``); reportlab + STSong-Light
  CID font, ``Canvas(invariant=1)`` 保证字节级 idempotent.
- ``id_card_last4`` → ``getattr(patient, 'id_card_last4', None) or '0000'``
  (MVP 占位). ADR-0046 r5 amend.
- ``template_version`` → ``settings.contract_template_version`` (MVP 写死
  v1.0.0). ADR-0046 r5 amend.

# 设计 hold flag (开发者标注, 不阻塞 implement)

**ADR-0041 解耦**: ``OrderStatus`` 和 ``PaymentState`` 是独立状态机。
``_validate_transition`` (lifecycle.py line 136) 验的是 ``OrderStatus``,
不验 ``PaymentState``. 也就是说在 schema 上 "先付后 accept" 完全合法
(``OrderStatus.created`` + ``PaymentState.paid`` → ``OrderStatus.accepted``).

魈拍板的 "单 accept hook" 隐含假设 "accept 时 PaymentState 必为 paid",
这是 **UI 约束** (patient 看不到未 accept 单的 pay button) 而非 **schema
约束**. 未来若业务允许 "先 accept 后 pay" 路径, 当前 hook 会在
PaymentState!=paid 时也 INSERT pending_generation 行 — 这本身**无钱安全风险**
(合同只是 audit trail, 钱流走自己的 PaymentState FSM), 但会产生 "未付款的
pending contract" 行, 若订单后续 expired/cancelled, contract 行需配套
invalidated.

未来真出现该路径时, 加 ``request_generation`` 内部 eligibility check
(``order.payment_state != PaymentState.paid → return None``) +
``payment_service.handle_pay_callback`` hook 即可补防御, 当前不实现.

(本 docstring 给后来 reader 提供 grep anchor, 不是设计 walk-back.)
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.order import Order
from app.models.patient_profile import PatientProfile
from app.models.service_contract import ContractStatus, ServiceContract
from app.services.contract_hash import (
    ContractHashGenerationError,
    amount_cny_from_yuan,
    generate_contract_hash_at_commit_time,
)
from app.services.contract_resolver import (
    ContractServicePackageNotFoundError,
    resolve_service_package_id,
)
from app.services.contract_state_machine import (
    InvalidContractStateTransitionError,
    assert_transition,
    normalize_patient_name,
)
from app.services.contract_storage import (
    ContractContentTypeError,
    ContractHashInputError,
    ContractStoragePutError,
    put_contract,
)
from app.utils.metrics import (
    contract_service_generate_now_total,
    contract_service_request_generation_total,
    contract_service_retry_failed_total,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants (魈 ADR-0046 r5 amend)
# ---------------------------------------------------------------------------

#: MVP 占位 id_card_last4 (D-056 no-id-card constraint).
#: 后续 ADR-XXXX 引入 id_card 收集时, hash_inputs JSONB 允许 amend snapshot +
#: recompute_hash, 防篡改强度即恢复. grep anchor: 改名时一处改动即可.
MVP_ID_CARD_PLACEHOLDER = "0000"

#: 合法最小 PDF (14 字节). 历史上 ``_render_pdf`` 返此 bytes,
#: 现实现已在 PDF-RENDER task (uuid `33ac1174`) 中替换为 reportlab + STSong-Light
#: 渲染 (见 :mod:`app.services.contract_pdf`). 保留此常量作为 fallback /
#: regression sentinel — 若未来底层渲染出问题需心紧回滚, 可手动切回这
#: 个 bytes 佼部署.
_MIN_VALID_PDF_BYTES = b"%PDF-1.4\n%%EOF\n"


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RequestGenerationResult:
    """Outcome of ``ContractService.request_generation``.

    ``contract``: 新建或已存在的 ServiceContract row.
    ``created``: True 当本次调用新建了行 (False 即 idempotent skip).
    """

    contract: ServiceContract
    created: bool


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ContractRequestGenerationError(RuntimeError):
    """Raised when ``request_generation`` cannot proceed beyond eligibility.

    Wraps lower-level errors from ``contract_resolver`` / ``contract_hash``
    so the EVENT-WIRING caller (accept_order) doesn't need to handle every
    sub-exception. Caller catches this + IntegrityError specifically.
    """


class ContractGenerateNowError(RuntimeError):
    """Raised when ``generate_now`` fails to advance the row to ``active``.

    Cron caller catches this, writes ``last_error_trace`` + bumps
    ``retry_count``, schedules ``retry_failed`` next round.
    """


# ---------------------------------------------------------------------------
# Service class
# ---------------------------------------------------------------------------


class ContractService:
    """Contract lifecycle orchestrator (ADR-0046 §3.x).

    All write-path interactions with ``service_contracts`` table flow
    through this class. Three method-level entry points correspond to
    the lifecycle transitions; no other module should INSERT/UPDATE
    ``service_contracts`` directly (existing direct mutations in tests
    grandfathered, new code must route through here).

    The class is intentionally **stateless** beyond ``session``: every
    method does its own ``session.get`` / ``session.execute`` so it's
    safe to instantiate per-request without sharing instances across
    coroutines.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    # -- request_generation (accept_order hook entry) -----------------------

    async def request_generation(self, order_id: uuid.UUID) -> RequestGenerationResult:
        """INSERT a ``pending_generation`` contract row for the given order.

        Called from ``order/lifecycle.accept_order`` immediately after the
        order transitions ``created → accepted`` (EVENT-WIRING task).

        At call time the following are invariants (魈 EVENT-WIRING final design):
          * ``order.companion_id`` is not None (accept_order sets it)
          * ``order`` row exists (accept_order loaded it)

        Returns:
            :class:`RequestGenerationResult` with the newly-created (or
            pre-existing on idempotent path) ServiceContract.

        Raises:
            ContractRequestGenerationError: hash compute / resolver fail.
                Caller should let the order accept transaction roll back —
                contract generation is part of the accept commit.

        Idempotency:
            ``service_contracts.order_id`` is UNIQUE. If a row already
            exists (e.g. caller retried), we catch ``IntegrityError`` and
            return the existing row with ``created=False``.

        Metrics:
            ``contract_service_request_generation_total{outcome=...}``
            with outcomes: ``created`` | ``already_exists`` | ``error``.
        """
        # Idempotency fast path: repeated accept/retry in the same DB
        # transaction should not attempt a second INSERT. The DB UNIQUE
        # constraint below remains the deep-defense path for true races
        # across transactions.
        existing = await self._load_existing_contract(order_id)
        if existing is not None:
            contract_service_request_generation_total.labels(outcome="already_exists").inc()
            logger.info(
                "contract.request_generation.already_exists",
                extra={"order_id": str(order_id), "contract_id": str(existing.id)},
            )
            return RequestGenerationResult(contract=existing, created=False)

        try:
            order = await self._load_order_for_contract(order_id)
            patient_name = await self._resolve_patient_name(order)
            id_card_last4 = await self._resolve_id_card_last4(order)
            service_package_id = await resolve_service_package_id(order, self.session)
            scheduled_at_iso = _build_scheduled_at_iso(order)
            price_yuan = (
                order.service_price_snapshot
                if order.service_price_snapshot is not None
                else order.price
            )
            amount_cny = amount_cny_from_yuan(price_yuan)
            template_version = settings.contract_template_version

            hash_result = generate_contract_hash_at_commit_time(
                order_id=str(order.id),
                amount_cny=amount_cny,
                service_package_id=str(service_package_id),
                scheduled_at=scheduled_at_iso,
                patient_name=normalize_patient_name(patient_name),
                patient_id_card_last4=id_card_last4,
                companion_id=str(order.companion_id),
                template_version=template_version,
            )
        except (
            ContractHashGenerationError,
            ContractServicePackageNotFoundError,
            ValueError,
        ) as exc:
            contract_service_request_generation_total.labels(outcome="error").inc()
            logger.error(
                "contract.request_generation.compute_failed",
                extra={"order_id": str(order_id), "error": str(exc)},
                exc_info=True,
            )
            raise ContractRequestGenerationError(
                f"contract hash compute failed for order {order_id}: {exc}"
            ) from exc

        contract = ServiceContract(
            order_id=order.id,
            template_version=template_version,
            contract_hash=hash_result.contract_hash,
            hash_inputs=hash_result.hash_inputs_snapshot,
            status=ContractStatus.pending_generation,
            retry_count=0,
        )
        self.session.add(contract)
        try:
            await self.session.flush()
        except IntegrityError:
            # UNIQUE(order_id) collision → idempotent skip, return existing.
            await self.session.rollback()
            existing = await self._load_existing_contract(order.id)
            if existing is None:
                # 不应该发生 (IntegrityError 必由 UNIQUE 触发), 防御性 re-raise.
                contract_service_request_generation_total.labels(outcome="error").inc()
                raise
            contract_service_request_generation_total.labels(outcome="already_exists").inc()
            logger.info(
                "contract.request_generation.already_exists",
                extra={"order_id": str(order.id), "contract_id": str(existing.id)},
            )
            return RequestGenerationResult(contract=existing, created=False)

        contract_service_request_generation_total.labels(outcome="created").inc()
        logger.info(
            "contract.request_generation.created",
            extra={
                "order_id": str(order.id),
                "contract_id": str(contract.id),
                "contract_hash": contract.contract_hash,
            },
        )
        return RequestGenerationResult(contract=contract, created=True)

    # -- generate_now (cron pickup entry) -----------------------------------

    async def generate_now(self, contract_id: uuid.UUID) -> ServiceContract:
        """Pickup a ``pending_generation`` row, render PDF, WORM-put, flip to ``active``.

        Called from ``contract_generate_pickup`` cron (PICKUP-CRON task).

        State machine:
          ``pending_generation`` → ``generating`` → ``active`` (success)
          ``pending_generation`` → ``generating`` → ``generation_failed`` (error)

        Returns:
            The mutated ServiceContract row (status=active on success).

        Raises:
            ContractGenerateNowError: render/storage failed; caller (cron)
                catches, writes ``last_error_trace`` + bumps retry_count.
            InvalidContractStateTransitionError: row not in pickup-eligible
                state (e.g. already active or manually_invalidated). Cron
                should log + skip.

        Metrics:
            ``contract_service_generate_now_total{outcome=...}`` with outcomes:
            ``success`` | ``failed`` | ``already_active`` | ``invalid_state``.
        """
        contract = await self.session.get(ServiceContract, contract_id)
        if contract is None:
            contract_service_generate_now_total.labels(outcome="invalid_state").inc()
            raise ContractGenerateNowError(f"contract {contract_id} not found")

        if contract.status == ContractStatus.active:
            contract_service_generate_now_total.labels(outcome="already_active").inc()
            logger.info(
                "contract.generate_now.already_active",
                extra={"contract_id": str(contract.id)},
            )
            return contract

        if contract.status != ContractStatus.pending_generation:
            contract_service_generate_now_total.labels(outcome="invalid_state").inc()
            raise InvalidContractStateTransitionError(
                f"generate_now requires status=pending_generation, "
                f"got {contract.status.value}"
            )

        # pending_generation → generating (guarded by FSM)
        assert_transition(
            from_status=contract.status,
            to_status=ContractStatus.generating,
            retry_count=contract.retry_count,
        )
        contract.status = ContractStatus.generating
        await self.session.flush()

        try:
            order = await self.session.get(Order, contract.order_id)
            if order is None:
                raise ContractGenerateNowError(
                    f"contract {contract_id} references missing order "
                    f"{contract.order_id}"
                )
            pdf_bytes = self._render_pdf(contract, order)
            storage_ref = put_contract(
                order_id=str(contract.order_id),
                contract_hash=contract.contract_hash,
                pdf_bytes=pdf_bytes,
                template_version=contract.template_version,
            )
        except (
            ContractStoragePutError,
            ContractContentTypeError,
            ContractHashInputError,
            NotImplementedError,
        ) as exc:
            # generating → generation_failed (allowed; caller may retry)
            contract.status = ContractStatus.generation_failed
            contract.last_error_trace = f"{type(exc).__name__}: {exc}"[:2000]
            await self.session.flush()
            contract_service_generate_now_total.labels(outcome="failed").inc()
            logger.error(
                "contract.generate_now.failed",
                extra={
                    "contract_id": str(contract.id),
                    "error": str(exc),
                },
                exc_info=True,
            )
            raise ContractGenerateNowError(
                f"generate_now failed for contract {contract_id}: {exc}"
            ) from exc

        # generating → active (PDF stored, blob path immutable)
        from datetime import datetime
        from datetime import timezone as _tz

        contract.storage_blob_path = storage_ref.blob_path
        contract.generated_at = datetime.now(_tz.utc)
        contract.status = ContractStatus.active
        contract.last_error_trace = None
        await self.session.flush()
        contract_service_generate_now_total.labels(outcome="success").inc()
        logger.info(
            "contract.generate_now.success",
            extra={
                "contract_id": str(contract.id),
                "blob_path": storage_ref.blob_path,
                "already_existed_in_storage": storage_ref.already_exists,
                "immutability_applied": storage_ref.immutability_applied,
            },
        )
        return contract

    # -- retry_failed (compensation cron entry, used by WORM-COMPENSATION) --

    async def retry_failed(self, contract_id: uuid.UUID) -> ServiceContract:
        """Retry a ``generation_failed`` contract; promote to ``generating`` again.

        Called from compensation cron (WORM-COMPENSATION task, follow-up).
        Increments ``retry_count``; if exhausted (>= MAX_RETRY_COUNT before
        retry attempt) caller should instead call ``mark_permanently_failed``
        directly (not this method — guard rail).

        Returns:
            The mutated ServiceContract row.

        Raises:
            ContractGenerateNowError: re-raised from inner ``generate_now``.
            InvalidContractStateTransitionError: row not in
                ``generation_failed`` state.

        Metrics:
            ``contract_service_retry_failed_total{outcome=...}`` with outcomes:
            ``requeued`` | ``permanently_failed`` | ``skipped`` | ``success``.
        """
        contract = await self.session.get(ServiceContract, contract_id)
        if contract is None:
            contract_service_retry_failed_total.labels(outcome="skipped").inc()
            raise ContractGenerateNowError(f"contract {contract_id} not found")

        if contract.status != ContractStatus.generation_failed:
            contract_service_retry_failed_total.labels(outcome="skipped").inc()
            raise InvalidContractStateTransitionError(
                f"retry_failed requires status=generation_failed, "
                f"got {contract.status.value}"
            )

        # generation_failed → generating (guarded). retry_count bumped
        # *before* the put attempt so a crash mid-put still counts.
        assert_transition(
            from_status=contract.status,
            to_status=ContractStatus.generating,
            retry_count=contract.retry_count,
        )
        contract.retry_count = contract.retry_count + 1
        contract.status = ContractStatus.generating
        await self.session.flush()

        try:
            order = await self.session.get(Order, contract.order_id)
            if order is None:
                raise ContractGenerateNowError(
                    f"contract {contract_id} references missing order "
                    f"{contract.order_id}"
                )
            pdf_bytes = self._render_pdf(contract, order)
            storage_ref = put_contract(
                order_id=str(contract.order_id),
                contract_hash=contract.contract_hash,
                pdf_bytes=pdf_bytes,
                template_version=contract.template_version,
            )
        except (
            ContractStoragePutError,
            ContractContentTypeError,
            ContractHashInputError,
            NotImplementedError,
        ) as exc:
            contract.status = ContractStatus.generation_failed
            contract.last_error_trace = f"{type(exc).__name__}: {exc}"[:2000]
            await self.session.flush()
            contract_service_retry_failed_total.labels(outcome="requeued").inc()
            logger.warning(
                "contract.retry_failed.requeued",
                extra={
                    "contract_id": str(contract.id),
                    "retry_count": contract.retry_count,
                    "error": str(exc),
                },
            )
            raise ContractGenerateNowError(
                f"retry_failed still failing for contract {contract_id}: {exc}"
            ) from exc

        from datetime import datetime
        from datetime import timezone as _tz

        contract.storage_blob_path = storage_ref.blob_path
        contract.generated_at = datetime.now(_tz.utc)
        contract.status = ContractStatus.active
        contract.last_error_trace = None
        await self.session.flush()
        contract_service_retry_failed_total.labels(outcome="success").inc()
        logger.info(
            "contract.retry_failed.success",
            extra={
                "contract_id": str(contract.id),
                "retry_count": contract.retry_count,
                "blob_path": storage_ref.blob_path,
            },
        )
        return contract

    # -- internals ----------------------------------------------------------

    def _render_pdf(self, contract: ServiceContract, order: Order) -> bytes:
        """Render the contract PDF bytes (魈 PDF-RENDER design gap 拍 (a)).

        Delegates to :func:`app.services.contract_pdf.render_contract_pdf`,
        which is a pure module-level function (easier to unit test;
        renderer swap doesn't touch lifecycle code).

        Args:
            contract: the :class:`ServiceContract` row carrying the
                immutable ``hash_inputs`` snapshot + ``contract_hash``.
            order: the eager-loaded :class:`Order` row carrying snapshot
                fields (``patient_name`` / ``companion_name`` /
                ``hospital_name`` / ``service_name_snapshot`` /
                ``service_price_snapshot`` / ``appointment_date`` /
                ``appointment_time`` / ``family_member_name`` /
                ``family_member_relation`` / ``order_number``).

        Why pass ``order`` instead of re-querying inside the renderer:
        ``ContractService.generate_now`` (and ``retry_failed``) already
        load the Order to validate state; passing it through avoids a
        second round-trip and keeps the pure-function shape of
        :func:`render_contract_pdf`.

        Why no ``selectinload(Order.companion, Order.patient)`` (魈 design
        draft suggested this): ``Order`` carries all PDF-visible fields
        as snapshot columns (``companion_name``, ``patient_name``,
        ``hospital_name``, ``service_name_snapshot``,
        ``service_price_snapshot``) frozen at create_order time. The
        contract is an audit trail of "what the parties agreed to at
        booking", so we deliberately do not consult live profile state.
        """
        from app.services.contract_pdf import render_contract_pdf

        return render_contract_pdf(
            order=order,
            hash_inputs=contract.hash_inputs,
            contract_hash=contract.contract_hash,
            template_version=contract.template_version,
        )

    async def _load_order_for_contract(self, order_id: uuid.UUID) -> Order:
        order = await self.session.get(Order, order_id)
        if order is None:
            raise ContractRequestGenerationError(f"order {order_id} not found")
        if order.companion_id is None:
            # Guard rail. EVENT-WIRING calls this from accept_order, where
            # companion_id was just set; if we somehow get here without it,
            # the contract hash cannot be computed.
            raise ContractRequestGenerationError(
                f"order {order_id} has no companion_id; "
                "request_generation must be called from accept_order hook"
            )
        return order

    async def _resolve_patient_name(self, order: Order) -> str:
        """Resolve patient_name with precedence: family_member > order snapshot.

        Order F-05 supports 代他人下单: ``family_member_name`` carries the
        actual recipient's display name; otherwise ``patient_name`` snapshot
        is the booking patient (self).

        Both fields are denormalized snapshots written at create_order time,
        so we never hit User / PatientProfile here for the name — that lets
        ContractService stay in the same TX as the order accept commit
        without extra reads.
        """
        if order.family_member_name and order.family_member_name.strip():
            return order.family_member_name.strip()
        if order.patient_name and order.patient_name.strip():
            return order.patient_name.strip()
        # Should not happen for a valid order (create_order requires user.display_name
        # or user.phone fallback) but guard rail for hash compute.
        raise ContractRequestGenerationError(
            f"order {order.id} has empty patient_name; cannot compute hash"
        )

    async def _resolve_id_card_last4(self, order: Order) -> str:
        """Resolve patient id_card_last4 — currently MVP placeholder.

        Precedence (future-proof for ADR-XXXX id-card collection):
          1. ``family_member.id_card_last4`` (if family member booking)
          2. ``patient_profile.id_card_last4`` (if self booking)
          3. ``MVP_ID_CARD_PLACEHOLDER`` ("0000") fallback (current MVP)

        Uses ``getattr`` so when columns are added later this code keeps
        working without a separate refactor PR. ADR-0046 r5 §3 amend.
        """
        # Family member path (F-05): preferred if booking on behalf.
        family_id_card = None
        if order.family_member_id:
            # Inline import to avoid cycle (model imports service occasionally).
            from app.models.family_member import FamilyMember

            family_member = await self.session.get(FamilyMember, order.family_member_id)
            if family_member is not None:
                family_id_card = getattr(family_member, "id_card_last4", None)

        if family_id_card:
            return str(family_id_card)[-4:].zfill(4)

        # Patient profile path (self booking).
        stmt = select(PatientProfile).where(PatientProfile.user_id == order.patient_id)
        result = await self.session.execute(stmt)
        profile = result.scalar_one_or_none()
        profile_id_card = getattr(profile, "id_card_last4", None) if profile else None
        if profile_id_card:
            return str(profile_id_card)[-4:].zfill(4)

        return MVP_ID_CARD_PLACEHOLDER

    async def _load_existing_contract(self, order_id: uuid.UUID) -> ServiceContract | None:
        stmt = select(ServiceContract).where(ServiceContract.order_id == order_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Helpers (module-level)
# ---------------------------------------------------------------------------


def _build_scheduled_at_iso(order: Order) -> str:
    """Combine ``appointment_date`` + ``appointment_time`` into ISO-8601 with +08:00.

    Order schema stores these as plain strings (``YYYY-MM-DD`` + ``HH:MM``)
    in Asia/Shanghai wall-clock time. Hash input wants stable ISO including tz,
    so we attach ``+08:00`` explicitly. ``_to_iso8601_utc`` in contract_hash
    will normalize to UTC, but receiving a tz-aware string is non-negotiable
    (else naive datetime → ambiguous parse).
    """
    from datetime import datetime, timedelta, timezone

    date_str = order.appointment_date or ""
    time_str = order.appointment_time or "00:00"
    cst = timezone(timedelta(hours=8))
    try:
        dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M").replace(tzinfo=cst)
    except ValueError as exc:
        raise ContractRequestGenerationError(
            f"order {order.id} has invalid appointment_date/time "
            f"({date_str!r} / {time_str!r}): {exc}"
        ) from exc
    return dt.isoformat()


__all__ = [
    "ContractService",
    "ContractRequestGenerationError",
    "ContractGenerateNowError",
    "RequestGenerationResult",
    "MVP_ID_CARD_PLACEHOLDER",
]
