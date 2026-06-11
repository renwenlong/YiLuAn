"""OrderPrecheckAggregator — S3-DEV-003 c2 evaluate + cache implementation.

History:
* S3-DEV-005-CACHE-INVALIDATE (PR #250) shipped the **stub edition** —
  the public ``invalidate_and_recompute`` orchestrator + ``_redis_del``
  real, with ``evaluate`` / ``_redis_set`` / ``_ws_broadcast`` raising
  :class:`NotImplementedError`. The admin ``POST /cache/invalidate``
  endpoint caught the ``NotImplementedError`` and surfaced 501.
* S3-DEV-003-PRECHECK-BACKEND c2 (this commit) implements
  ``evaluate`` + ``_redis_set`` so the orchestrator returns a real
  summary + writes the cache. The endpoint catch-block is removed in
  the same commit (canary test rewrite).
* ``_ws_broadcast`` is **still a stub** in c2 — it returns ``False``
  (instead of raising) so the orchestrator can complete without
  ``NotImplementedError``. S3-DEV-003 c4 (WS infra) replaces the body
  with the real broadcast call. Until then ``broadcast=False`` is
  the canonical signal to clients (and tests assert against it).

Design source: ``docs/design/S3-trust-precheck-ui.md`` §3.2 / §5.3 +
ADR-0047 §3.1 (ContractStatus) / §3.3 (InsuranceStatus). Per 14:10Z
魈 ack, design doc abstract names map to codebase actual models:

* ``ContractStateMachine`` →
  :class:`app.models.service_contract.ServiceContract`
* ``InsuranceOrderStateMachine`` →
  :class:`app.models.service_insurance_record.ServiceInsuranceRecord`
* ``companion_cert_verifications 表`` →
  :class:`app.models.companion_profile.CompanionProfile`

ABAC Layer 3 (this layer) enforces **explicit SELECT column projection**:
each ``_load_*`` helper SELECTs only positive-list fields the View
schema (c1) defines. Negative-list columns (contract_hash, hash_inputs,
storage_blob_path, raw_llm_output, actual_premium, etc.) are never
fetched into Python — defense in depth on top of Pydantic schema's
``extra='forbid'`` (Layer 1).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Final, Sequence, TypedDict
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from fastapi import FastAPI

from app.models.companion_profile import CompanionProfile, VerificationStatus
from app.models.order import Order
from app.models.preparation_package import PreparationPackage, PrepStatus
from app.models.service_contract import ContractStatus, ServiceContract
from app.models.service_insurance_record import (
    InsuranceStatus,
    ServiceInsuranceRecord,
)
from app.schemas.order_precheck import (
    CompanionCertStatusView,
    ContractStatusView,
    InsuranceStatusView,
    OrderPrecheckSummaryView,
    PreparationStatusView,
)
from app.services.certification_image import sign_certification_image_url
from app.services.contract_storage import ViewerRole, get_contract_signed_url

logger = logging.getLogger(__name__)

# Cache key format per design S3-trust-precheck-ui.md line 224.
# Single key packs all 4 cards (魈 Q4 #4 — do NOT use per-card keys).
_CACHE_KEY_TEMPLATE: Final[str] = "precheck:order:{order_id}"
_CACHE_TTL_SECONDS: Final[int] = 5 * 60  # 5 min per design §5.3

# Blocked reason short codes (design §3.3 文案 lint set). Front-end
# renders these directly — keep stable strings, do not localise here.
_BLOCKED_REASON_CONTRACT_GEN_FAILED: Final[str] = "合同生成中遇到问题，请稍候再试"
_BLOCKED_REASON_CONTRACT_PERM_FAILED: Final[str] = "合同生成失败，请联系客服"
_BLOCKED_REASON_CONTRACT_INVALIDATED: Final[str] = "合同已作废，请联系客服"
_BLOCKED_REASON_CONTRACT_PENDING: Final[str] = "合同生成中"
_BLOCKED_REASON_INSURANCE_FAILED: Final[str] = "保险出单失败，请联系客服"
_BLOCKED_REASON_INSURANCE_INVALIDATED: Final[str] = "保险已作废，请联系客服"
_BLOCKED_REASON_INSURANCE_PENDING: Final[str] = "保险出单中"
_BLOCKED_REASON_PREP_FAILED: Final[str] = "AI 准备包生成失败，请刷新或稍候再试"
_BLOCKED_REASON_PREP_PENDING: Final[str] = "AI 准备包生成中"
_BLOCKED_REASON_COMPANION_NOT_VERIFIED: Final[str] = "陪诊师资质待审核"
_BLOCKED_REASON_COMPANION_REJECTED: Final[str] = "陪诊师资质审核未通过，请联系客服"
_BLOCKED_REASON_NO_COMPANION: Final[str] = "尚未指派陪诊师"


class InvalidateRecomputeResult(TypedDict):
    """Return type for :meth:`OrderPrecheckAggregator.invalidate_and_recompute`.

    c6 dedup: ``summary`` field added so hook helpers / WS broadcast
    can reuse the recomputed summary without re-calling :meth:`evaluate`.
    Old callers reading ``invalidated_keys`` / ``broadcast`` keep
    working (additive change).
    """

    invalidated_keys: list[str]
    broadcast: bool
    summary: dict[str, Any]


def _build_cache_key(order_id: UUID) -> str:
    """Compose the canonical precheck cache key.

    Returns a deterministic string the endpoint can include in the
    audit row + 200 response ``invalidated_keys`` field.
    """
    return _CACHE_KEY_TEMPLATE.format(order_id=str(order_id))


def _mask_policy_no(raw: str | None) -> str | None:
    """Mask insurance policy number to head4+****+tail4.

    ABAC defense: vendor_policy_no may carry vendor-internal structure;
    only ends are user-relevant for reference / dispute. Example:
    ``BX2026123456781234`` → ``BX20****1234``.
    """
    if not raw:
        return None
    if len(raw) <= 8:
        return raw  # 太短不脱敏 (e.g. placeholder)
    return f"{raw[:4]}****{raw[-4:]}"


class OrderPrecheckAggregator:
    """Aggregator for 4 信任卡 precheck status — c2 real evaluate edition.

    Lifecycle:

    1. Endpoint (admin cache invalidate or user precheck-status GET)
       constructs an instance with a DB session + Redis client.
    2. For invalidate: :meth:`invalidate_and_recompute` runs DEL →
       evaluate → SET → broadcast and returns 200 body.
    3. For GET (c3 endpoint, future commit): :meth:`evaluate` directly
       returns the View; the GET endpoint optionally reads cache first.

    Concurrency: each instance is **per-request** (Depends() scope in
    FastAPI), not shared across requests. Redis + session are injected.
    """

    def __init__(
        self,
        redis: Redis,
        session: AsyncSession | None = None,
        app: "FastAPI | None" = None,
    ) -> None:
        self._redis = redis
        self._session = session
        # S3-DEV-003 c5: optional FastAPI app for WS broadcast. When
        # provided, :meth:`_ws_broadcast` pushes the recomputed summary
        # via the precheck broadcast facade. When ``None`` (e.g. unit
        # tests, background tasks without app handle), broadcast is a
        # no-op returning ``False`` — caller (admin endpoint) treats
        # ``broadcast=False`` as normal per c2 contract.
        self._app = app

    # ------------------------------------------------------------------
    # Public orchestrator
    # ------------------------------------------------------------------

    async def invalidate_and_recompute(
        self,
        order_id: UUID,
        cards: Sequence[str] | None = None,
    ) -> InvalidateRecomputeResult:
        """Public orchestrator — DEL → evaluate → SET → broadcast.

        Returns :class:`InvalidateRecomputeResult` with:
        - ``invalidated_keys``: cache keys deleted (admin endpoint 200 body)
        - ``broadcast``: WS publish success boolean (admin endpoint 200 body)
        - ``summary``: recomputed 4-card summary dict (c6 dedup —
          hook helpers consume this instead of re-calling
          :meth:`evaluate`)

        c6 dedup
        --------
        The recomputed ``summary`` is now included in the return dict
        AND passed explicitly to :meth:`_ws_broadcast` so the broadcast
        path does NOT re-call :meth:`evaluate`. Hook helpers
        (``precheck_recompute_hook``) consume ``result["summary"]``
        for secondary events (``all_ready`` / ``blocked``) without
        another evaluate. End result: 1 hook trigger = 1 evaluate
        (was 3 before c6).

        Backward compat: old callers reading ``result["invalidated_keys"]``
        or ``result["broadcast"]`` keep working — new ``summary`` key
        is additive.
        """
        # Step 1: defensive DEL (always real).
        key = _build_cache_key(order_id)
        await self._redis_del(key)

        # Step 2: evaluate — read 4 cards + compute summary.
        summary = await self.evaluate(order_id)

        # Step 3: SET — overwrite cache with fresh summary (TTL 5min).
        await self._redis_set(order_id, summary)

        # Step 4: WS broadcast — c6 dedup: pass summary so
        # _ws_broadcast does NOT re-call evaluate (was evaluate #2
        # pre-c6). Without summary= the broadcast would fallback to
        # evaluate for unit test / background callers.
        broadcast_ok = await self._ws_broadcast(
            order_id,
            tuple(cards) if cards else None,
            summary=summary,
        )

        return {
            "invalidated_keys": [key],
            "broadcast": broadcast_ok,
            "summary": summary,
        }

    # ------------------------------------------------------------------
    # Cache primitives
    # ------------------------------------------------------------------

    async def _redis_del(self, key: str) -> int:
        """Defensive pre-invalidation. Returns deleted key count (0 if cold)."""
        return int(await self._redis.delete(key))

    async def _redis_set(self, order_id: UUID, summary: dict[str, Any]) -> None:
        """Overwrite cache with fresh summary, TTL 5 min per design §5.3.

        SET overwrite (NOT GET-OR-COMPUTE merge) per design line 224 +
        胡桃 r3 amend: cache is purely a read-through optimisation
        with TTL fallback. Inconsistent ABAC fields cannot leak across
        TTL boundaries because Layer 1 schema enforcement runs on
        every serialize.
        """
        key = _build_cache_key(order_id)
        payload = json.dumps(summary, default=_json_default, ensure_ascii=False)
        await self._redis.set(key, payload, ex=_CACHE_TTL_SECONDS)

    async def _ws_broadcast(
        self,
        order_id: UUID,
        cards_changed: tuple[str, ...] | None,
        summary: dict[str, Any] | None = None,
    ) -> bool:
        """WS broadcast — c5 facade impl, c6 dedup signature.

        Resolves the precheck broker from ``self._app`` (injected via
        :func:`app.api.v1.deps_precheck.get_precheck_aggregator` or
        admin cache invalidate endpoint). When app is not available
        (unit test / background context), returns ``False`` so the
        admin endpoint contract (``broadcast`` boolean in 200 body)
        is preserved without rewrapping the orchestrator.

        Pushes a fresh ``precheck.status.updated`` event with the
        recomputed summary so connected clients (user app via WS)
        receive the new card states without an extra GET round-trip.

        c6 dedup
        --------
        ``summary`` is now an optional parameter. When provided
        (normal path — orchestrator step 4 passes the step-2 summary),
        :meth:`evaluate` is NOT re-called. When omitted (direct
        ``_ws_broadcast`` callers, unit tests, background tasks), the
        method falls back to :meth:`evaluate` to preserve the c5
        contract.
        """
        if self._app is None:
            return False

        # c6 dedup: prefer caller-supplied summary; fallback to
        # evaluate only when caller did not pass one (test / direct
        # broadcast caller path).
        if summary is None:
            try:
                summary = await self.evaluate(order_id)
            except Exception:  # pragma: no cover — defensive
                logger.exception(
                    "_ws_broadcast.evaluate_failed",
                    extra={"order_id": str(order_id)},
                )
                return False

        # Pick the first changed card for the broadcast envelope, or
        # a sentinel ``"summary"`` when callers do not scope.
        card = (cards_changed[0] if cards_changed else "summary")

        try:
            from app.services.precheck_broadcast import broadcast_status_updated

            await broadcast_status_updated(
                self._app,
                order_id,
                card=card,
                status=summary,
                all_ready=bool(summary.get("all_ready", False)),
            )
            return True
        except Exception:  # pragma: no cover — defensive
            logger.exception(
                "_ws_broadcast.publish_failed",
                extra={"order_id": str(order_id), "card": card},
            )
            return False

    # ------------------------------------------------------------------
    # Evaluate: load 4 cards + aggregate
    # ------------------------------------------------------------------

    async def evaluate(self, order_id: UUID) -> dict[str, Any]:
        """Read 4 cards + return :class:`OrderPrecheckSummaryView` as dict.

        Returns
        -------
        dict
            Serialised View ready for SET / JSON response.

        Raises
        ------
        ValueError
            If session is not injected (caller invariant).
        """
        if self._session is None:
            raise ValueError(
                "OrderPrecheckAggregator.evaluate requires a session; "
                "construct with OrderPrecheckAggregator(redis, session)."
            )

        order = await self._load_order(order_id)

        contract_view = await self._load_contract_view(order_id)
        insurance_view = await self._load_insurance_view(order_id)
        preparation_view = await self._load_preparation_view(order_id)
        companion_cert_view = await self._load_companion_cert_view(
            order.companion_id if order else None
        )

        all_ready = (
            contract_view.ready
            and insurance_view.ready
            and preparation_view.ready
            and companion_cert_view.ready
        )
        blocked_reason = self._first_blocked_reason(
            contract_view,
            insurance_view,
            preparation_view,
            companion_cert_view,
            has_companion=order is not None and order.companion_id is not None,
        )

        signed_url_expires_at = self._earliest_signed_url_expiry(contract_view, companion_cert_view)

        summary = OrderPrecheckSummaryView(
            order_id=str(order_id),
            contract_status=contract_view,
            insurance_status=insurance_view,
            preparation_status=preparation_view,
            companion_cert_status=companion_cert_view,
            all_ready=all_ready,
            payment_enabled=all_ready,  # c2: no PM-side override yet (future task)
            blocked_reason=blocked_reason,
            signed_url_expires_at=signed_url_expires_at,
        )
        return summary.model_dump(mode="json")

    # ------------------------------------------------------------------
    # Per-card loaders (ABAC Layer 3: explicit column SELECT)
    # ------------------------------------------------------------------

    async def _load_order(self, order_id: UUID) -> Order | None:
        """Load the Order row (only the fields we need: companion_id).

        Returns None if not found — caller treats as "no companion
        assigned" downstream.
        """
        assert self._session is not None
        result = await self._session.execute(select(Order.companion_id).where(Order.id == order_id))
        row = result.first()
        if row is None:
            return None
        # Wrap to keep .companion_id access uniform with full model
        # (we only need this field).
        return Order(id=order_id, companion_id=row[0])  # type: ignore[call-arg]

    async def _load_contract_view(self, order_id: UUID) -> ContractStatusView:
        """ABAC Layer 3: SELECT only positive-list contract columns.

        Skipped: contract_hash, hash_inputs, storage_blob_path,
        template_key (not in model anyway), retry_count,
        last_error_trace, invalidation_reason, invalidated_by_admin_id,
        worm_*, is_immutable. Only id / template_version / status /
        generated_at / storage_blob_path needed (blob_path only for
        sign URL, never returned).
        """
        assert self._session is not None
        result = await self._session.execute(
            select(
                ServiceContract.id,
                ServiceContract.template_version,
                ServiceContract.status,
                ServiceContract.generated_at,
                ServiceContract.storage_blob_path,
            )
            .where(ServiceContract.order_id == order_id)
            .order_by(ServiceContract.updated_at.desc())
            .limit(1)
        )
        row = result.first()
        if row is None:
            return ContractStatusView(ready=False)

        contract_id, template_version, status, generated_at, blob_path = row
        ready = status == ContractStatus.active
        signed_url: str | None = None
        if ready and blob_path:
            try:
                signed = get_contract_signed_url(blob_path, ViewerRole.USER)
                signed_url = signed.url
            except Exception:  # noqa: BLE001 — never fail summary on URL sign error
                logger.warning(
                    "contract signed URL gen failed; serving ready=True without url",
                    extra={"order_id": str(order_id)},
                )
                signed_url = None
        return ContractStatusView(
            ready=ready,
            contract_id=str(contract_id),
            contract_template_version=template_version,
            contract_pdf_url=signed_url,
            generated_at=generated_at,
        )

    async def _load_insurance_view(self, order_id: UUID) -> InsuranceStatusView:
        """ABAC Layer 3: SELECT only positive-list insurance columns.

        Skipped: carrier_internal_id / actual_premium / underwriter_meta
        (not in model anyway), retry_count, failure_reason,
        invalidation_*. Only id / vendor_policy_no / status / issued_at.
        Vendor name not surfaced (commercial reason: 凝光 review).
        """
        assert self._session is not None
        result = await self._session.execute(
            select(
                ServiceInsuranceRecord.id,
                ServiceInsuranceRecord.vendor_policy_no,
                ServiceInsuranceRecord.status,
                ServiceInsuranceRecord.issued_at,
            )
            .where(ServiceInsuranceRecord.order_id == order_id)
            .order_by(ServiceInsuranceRecord.updated_at.desc())
            .limit(1)
        )
        row = result.first()
        if row is None:
            return InsuranceStatusView(ready=False)

        ins_id, vendor_policy_no, status, issued_at = row
        ready = status == InsuranceStatus.active
        return InsuranceStatusView(
            ready=ready,
            insurance_order_id=str(ins_id),
            insurance_policy_no_masked=_mask_policy_no(vendor_policy_no),
            insurance_policy_pdf_url=None,  # S3: no vendor PDF, c3+ when real
            insurance_effective_from=(issued_at.date() if ready and issued_at else None),
        )

    async def _load_preparation_view(self, order_id: UUID) -> PreparationStatusView:
        """ABAC Layer 3: SELECT only positive-list prep columns.

        Skipped: prompt_version_id / model / actual_cost_yuan /
        estimated_cost_yuan / generation_time_ms / trace_id /
        fallback_reason / pre_visit_notes (admin-only review). Only
        id / status / carry_items / possible_questions /
        companion_focus_points / created_at.
        ``prep_summary`` synthesises 1-line from carry+questions counts.
        """
        assert self._session is not None
        result = await self._session.execute(
            select(
                PreparationPackage.id,
                PreparationPackage.status,
                PreparationPackage.carry_items,
                PreparationPackage.possible_questions,
                PreparationPackage.companion_focus_points,
                PreparationPackage.created_at,
            )
            .where(PreparationPackage.order_id == order_id)
            .order_by(PreparationPackage.created_at.desc())
            .limit(1)
        )
        row = result.first()
        if row is None:
            return PreparationStatusView(ready=False)

        prep_id, status, carry_items, possible_questions, focus_points, created_at = row
        ready = status in (PrepStatus.active, PrepStatus.active_fallback_template)
        sections_count = sum(1 for x in (carry_items, possible_questions, focus_points) if x)
        prep_summary: str | None = None
        if ready and sections_count > 0:
            prep_summary = f"已生成 {sections_count} 个准备段落: " f"携带物品 / 可能咨询 / 关注要点"
        return PreparationStatusView(
            ready=ready,
            preparation_id=str(prep_id),
            prep_summary=prep_summary,
            sections_count=sections_count if ready else None,
            generated_at=created_at,
        )

    async def _load_companion_cert_view(
        self, companion_user_id: UUID | None
    ) -> CompanionCertStatusView:
        """ABAC Layer 3: SELECT only positive-list companion cert columns.

        Skipped: real_name / id_number / certification_no (admin-only).
        Only id / verification_status / certification_type /
        certification_image_url / certified_at /
        verification_completed_at (c1 added) / certifications /
        display_name (pseudonym fallback).

        Pseudonym: prefer display_name on User; falls back to
        certifications first item if display_name missing — never returns
        real_name.
        """
        if companion_user_id is None:
            return CompanionCertStatusView(ready=False)
        assert self._session is not None
        result = await self._session.execute(
            select(
                CompanionProfile.id,
                CompanionProfile.verification_status,
                CompanionProfile.certification_type,
                CompanionProfile.certification_image_url,
                CompanionProfile.certified_at,
                CompanionProfile.verification_completed_at,
                CompanionProfile.certifications,
            )
            .where(CompanionProfile.user_id == companion_user_id)
            .order_by(CompanionProfile.updated_at.desc())
            .limit(1)
        )
        row = result.first()
        if row is None:
            return CompanionCertStatusView(ready=False)

        (
            prof_id,
            status,
            cert_type,
            cert_image_url,
            certified_at,
            verification_completed_at,
            certifications_text,
        ) = row
        ready = status == VerificationStatus.verified
        qualifications: list[str] | None = None
        if certifications_text:
            qualifications = [
                t.strip() for t in str(certifications_text).split(",") if t.strip()
            ] or None
        signed_image_urls: list[str] | None = None
        if ready and cert_image_url:
            try:
                signed = sign_certification_image_url(cert_image_url)
                signed_image_urls = [signed] if signed else None
            except Exception:  # noqa: BLE001
                logger.warning(
                    "companion cert image URL sign failed",
                    extra={"companion_profile_id": str(prof_id)},
                )
                signed_image_urls = None
        # PRD §F4 fallback: verification_completed_at NULL → certified_at
        effective_verified_at = verification_completed_at or certified_at
        return CompanionCertStatusView(
            ready=ready,
            companion_cert_pseudonym_name=f"陪诊师 #{str(prof_id)[:8]}",
            companion_cert_work_id=cert_type,
            companion_cert_qualifications=qualifications,
            companion_cert_proof_image_urls=signed_image_urls,
            companion_cert_verified_at=effective_verified_at,
        )

    # ------------------------------------------------------------------
    # Aggregation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _first_blocked_reason(
        contract: ContractStatusView,
        insurance: InsuranceStatusView,
        preparation: PreparationStatusView,
        companion: CompanionCertStatusView,
        *,
        has_companion: bool,
    ) -> str | None:
        """Pick the first user-readable reason in 4-card priority order.

        Priority (design §3.3): contract > insurance > preparation >
        companion. Caller knows ``all_ready=True`` short-circuits to
        ``None``; this helper is only invoked when at least one is
        ``ready=False``.
        """
        if contract.ready and insurance.ready and preparation.ready and companion.ready:
            return None
        if not contract.ready:
            # Without underlying status string we can only emit the
            # generic "pending" string. c3 endpoint enriches via the
            # underlying ContractStatus enum when available.
            return _BLOCKED_REASON_CONTRACT_PENDING
        if not insurance.ready:
            return _BLOCKED_REASON_INSURANCE_PENDING
        if not preparation.ready:
            return _BLOCKED_REASON_PREP_PENDING
        if not has_companion:
            return _BLOCKED_REASON_NO_COMPANION
        if not companion.ready:
            return _BLOCKED_REASON_COMPANION_NOT_VERIFIED
        return None

    @staticmethod
    def _earliest_signed_url_expiry(
        contract: ContractStatusView,
        companion: CompanionCertStatusView,
    ) -> datetime | None:
        """Compute earliest expiry timestamp of any signed URL in the view.

        c2 returns ``None`` because :func:`get_contract_signed_url` /
        :func:`sign_certification_image_url` do not propagate explicit
        expiry timestamps — the URL itself carries the expiry. c3
        endpoint enriches this when calling Aggregator (passes ``now``
        + TTL constants in for deterministic propagation). For SET
        cache during the c2 window the field is acceptable as None.
        """
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _json_default(obj: Any) -> Any:
    """JSON serializer for ``datetime`` + ``UUID`` (Redis SET payload)."""
    if isinstance(obj, datetime):
        # Normalise to UTC ISO-8601 with Z suffix.
        if obj.tzinfo is None:
            obj = obj.replace(tzinfo=timezone.utc)
        return obj.isoformat().replace("+00:00", "Z")
    if isinstance(obj, UUID):
        return str(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


__all__ = [
    "OrderPrecheckAggregator",
    "_build_cache_key",
    "_mask_policy_no",
]
