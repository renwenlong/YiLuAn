"""S3-DEV-003-PRECHECK-BACKEND c2 — OrderPrecheckAggregator.evaluate tests.

Covers:
* ``evaluate`` reads 4 cards (contract / insurance / preparation /
  companion cert) from real DB rows seeded in tests.
* ``all_ready`` is True iff all 4 cards ``ready=True``.
* ``blocked_reason`` is picked by 4-card priority order
  (contract > insurance > preparation > companion).
* ``_redis_set`` writes a SET with TTL 5 min.
* ABAC Layer 3: each ``_load_*`` SELECTs only positive-list columns —
  asserted by **not** finding negative-list fields in the dumped dict.
* Edge cases: order without companion → ``has_companion=False`` blocked
  reason; missing cards return ``ready=False`` (not crash).

Design source: ``docs/design/S3-trust-precheck-ui.md`` §3.2 / §5.3.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import pytest

from app.models.companion_profile import CompanionProfile, VerificationStatus
from app.models.order import Order, OrderStatus, PaymentState, ServiceType
from app.models.preparation_package import PreparationPackage, PrepStatus
from app.models.service_contract import (
    ContractStatus,
    ContractWormStatus,
    ServiceContract,
)
from app.models.service_insurance_record import (
    InsuranceStatus,
    ServiceInsuranceRecord,
)
from app.services.order_precheck_aggregator import (
    OrderPrecheckAggregator,
    _build_cache_key,
    _mask_policy_no,
)
from tests.conftest import test_session_factory as _session_factory

# ---------------------------------------------------------------------------
# Fixtures: 4-card seed helpers
# ---------------------------------------------------------------------------


async def _seed_order(*, companion_id: Any | None) -> Any:
    """Insert an Order with the given companion_id and return id."""
    from decimal import Decimal

    async with _session_factory() as session:
        order = Order(
            order_number=f"OD{uuid4().hex[:12].upper()}",
            patient_id=uuid4(),
            companion_id=companion_id,
            hospital_id=uuid4(),
            service_type=ServiceType.full_accompany,
            status=OrderStatus.created,
            payment_state=PaymentState.none,
            appointment_date="2026-06-15",
            appointment_time="09:00",
            price=Decimal("100.00"),
        )
        session.add(order)
        await session.commit()
        await session.refresh(order)
        return order.id


async def _seed_contract(order_id: Any, *, status: ContractStatus) -> None:
    async with _session_factory() as session:
        contract = ServiceContract(
            order_id=order_id,
            template_version="v1.0.0",
            contract_hash="a" * 64,
            hash_inputs={"order_id": str(order_id)},
            storage_blob_path=(
                f"contracts/2026/06/{order_id}_test.pdf"
                if status == ContractStatus.active
                else None
            ),
            generated_at=(datetime.now(timezone.utc) if status == ContractStatus.active else None),
            status=status,
            worm_status=ContractWormStatus.applied,
        )
        session.add(contract)
        await session.commit()


async def _seed_insurance(
    order_id: Any, *, status: InsuranceStatus, policy_no: str | None = None
) -> None:
    async with _session_factory() as session:
        ins = ServiceInsuranceRecord(
            order_id=order_id,
            product_name="陪诊保",
            coverage_amount_cny=50000,
            vendor_name="PLACEHOLDER",
            vendor_policy_no=policy_no,
            status=status,
            issued_at=(datetime.now(timezone.utc) if status == InsuranceStatus.active else None),
        )
        session.add(ins)
        await session.commit()


async def _seed_prep(order_id: Any, *, status: PrepStatus) -> None:
    async with _session_factory() as session:
        prep = PreparationPackage(
            order_id=order_id,
            status=status,
            carry_items=(
                ["身份证", "病历", "医保卡"]
                if status in (PrepStatus.active, PrepStatus.active_fallback_template)
                else None
            ),
            possible_questions=(
                ["最近是否有不适？"]
                if status in (PrepStatus.active, PrepStatus.active_fallback_template)
                else None
            ),
            companion_focus_points=(
                ["核对身份"]
                if status in (PrepStatus.active, PrepStatus.active_fallback_template)
                else None
            ),
        )
        session.add(prep)
        await session.commit()


async def _seed_companion(user_id: Any, *, status: VerificationStatus) -> None:
    async with _session_factory() as session:
        profile = CompanionProfile(
            user_id=user_id,
            real_name="陈测试",
            id_number="11010100000000000X",
            certifications="康复治疗师,健康管理师",
            verification_status=status,
            certification_type="PC0042",
            certification_image_url=(
                "cert-image://2026/06/test_cert.jpg"
                if status == VerificationStatus.verified
                else None
            ),
            certified_at=(
                datetime.now(timezone.utc) if status == VerificationStatus.verified else None
            ),
            verification_completed_at=(
                datetime.now(timezone.utc) if status == VerificationStatus.verified else None
            ),
        )
        session.add(profile)
        await session.commit()


class _FakeRedis:
    """Tiny in-memory stand-in for ``redis.asyncio.Redis``."""

    def __init__(self) -> None:
        self._store: dict[str, bytes] = {}
        self._ttl: dict[str, int] = {}

    async def delete(self, *keys: str) -> int:
        n = 0
        for k in keys:
            if k in self._store:
                del self._store[k]
                n += 1
        return n

    async def set(self, key: str, value: Any, *, ex: int | None = None) -> bool:
        self._store[key] = value.encode() if isinstance(value, str) else value
        if ex is not None:
            self._ttl[key] = ex
        return True

    async def get(self, key: str) -> bytes | None:
        return self._store.get(key)

    def ttl_for(self, key: str) -> int | None:
        return self._ttl.get(key)


# ---------------------------------------------------------------------------
# evaluate happy path
# ---------------------------------------------------------------------------


async def test_evaluate_all_ready_returns_summary_with_all_ready_true() -> None:
    """4 cards all ready → ``all_ready=True``, ``blocked_reason=None``."""
    companion_user_id = uuid4()
    order_id = await _seed_order(companion_id=companion_user_id)
    await _seed_contract(order_id, status=ContractStatus.active)
    await _seed_insurance(order_id, status=InsuranceStatus.active, policy_no="BX2026123456781234")
    await _seed_prep(order_id, status=PrepStatus.active)
    await _seed_companion(companion_user_id, status=VerificationStatus.verified)

    async with _session_factory() as session:
        agg = OrderPrecheckAggregator(_FakeRedis(), session=session)
        summary = await agg.evaluate(order_id)

    assert summary["order_id"] == str(order_id)
    assert summary["all_ready"] is True
    assert summary["payment_enabled"] is True
    assert summary["blocked_reason"] is None
    assert summary["contract_status"]["ready"] is True
    assert summary["insurance_status"]["ready"] is True
    assert summary["preparation_status"]["ready"] is True
    assert summary["companion_cert_status"]["ready"] is True


async def test_evaluate_contract_pending_short_circuits_blocked_reason() -> None:
    """contract not ready → blocked_reason 是 contract 文案 (4-card priority)."""
    companion_user_id = uuid4()
    order_id = await _seed_order(companion_id=companion_user_id)
    await _seed_contract(order_id, status=ContractStatus.pending_generation)
    await _seed_insurance(order_id, status=InsuranceStatus.active)
    await _seed_prep(order_id, status=PrepStatus.active)
    await _seed_companion(companion_user_id, status=VerificationStatus.verified)

    async with _session_factory() as session:
        agg = OrderPrecheckAggregator(_FakeRedis(), session=session)
        summary = await agg.evaluate(order_id)

    assert summary["all_ready"] is False
    assert summary["payment_enabled"] is False
    assert summary["contract_status"]["ready"] is False
    assert summary["blocked_reason"] == "合同生成中"


async def test_evaluate_insurance_blocks_when_contract_ready() -> None:
    """contract ready + insurance pending → blocked_reason 是 insurance 文案."""
    companion_user_id = uuid4()
    order_id = await _seed_order(companion_id=companion_user_id)
    await _seed_contract(order_id, status=ContractStatus.active)
    await _seed_insurance(order_id, status=InsuranceStatus.pending_issue)
    await _seed_prep(order_id, status=PrepStatus.active)
    await _seed_companion(companion_user_id, status=VerificationStatus.verified)

    async with _session_factory() as session:
        agg = OrderPrecheckAggregator(_FakeRedis(), session=session)
        summary = await agg.evaluate(order_id)

    assert summary["all_ready"] is False
    assert summary["blocked_reason"] == "保险出单中"


async def test_evaluate_no_companion_assigned_returns_no_companion_reason() -> None:
    """Order without companion_id → companion card ready=False + dedicated reason."""
    order_id = await _seed_order(companion_id=None)
    await _seed_contract(order_id, status=ContractStatus.active)
    await _seed_insurance(order_id, status=InsuranceStatus.active)
    await _seed_prep(order_id, status=PrepStatus.active)

    async with _session_factory() as session:
        agg = OrderPrecheckAggregator(_FakeRedis(), session=session)
        summary = await agg.evaluate(order_id)

    assert summary["all_ready"] is False
    assert summary["companion_cert_status"]["ready"] is False
    assert summary["blocked_reason"] == "尚未指派陪诊师"


async def test_evaluate_companion_not_verified_returns_not_verified_reason() -> None:
    """Companion assigned but verification pending → companion-block reason."""
    companion_user_id = uuid4()
    order_id = await _seed_order(companion_id=companion_user_id)
    await _seed_contract(order_id, status=ContractStatus.active)
    await _seed_insurance(order_id, status=InsuranceStatus.active)
    await _seed_prep(order_id, status=PrepStatus.active)
    await _seed_companion(companion_user_id, status=VerificationStatus.pending)

    async with _session_factory() as session:
        agg = OrderPrecheckAggregator(_FakeRedis(), session=session)
        summary = await agg.evaluate(order_id)

    assert summary["all_ready"] is False
    assert summary["companion_cert_status"]["ready"] is False
    assert summary["blocked_reason"] == "陪诊师资质待审核"


async def test_evaluate_missing_all_cards_returns_all_false_no_crash() -> None:
    """Order with no contract / insurance / prep / companion rows → safe ready=False."""
    order_id = await _seed_order(companion_id=None)

    async with _session_factory() as session:
        agg = OrderPrecheckAggregator(_FakeRedis(), session=session)
        summary = await agg.evaluate(order_id)

    assert summary["contract_status"]["ready"] is False
    assert summary["insurance_status"]["ready"] is False
    assert summary["preparation_status"]["ready"] is False
    assert summary["companion_cert_status"]["ready"] is False
    assert summary["all_ready"] is False
    assert summary["blocked_reason"] == "合同生成中"


async def test_evaluate_active_fallback_template_prep_is_ready() -> None:
    """``PrepStatus.active_fallback_template`` is also a ``ready`` state."""
    companion_user_id = uuid4()
    order_id = await _seed_order(companion_id=companion_user_id)
    await _seed_contract(order_id, status=ContractStatus.active)
    await _seed_insurance(order_id, status=InsuranceStatus.active)
    await _seed_prep(order_id, status=PrepStatus.active_fallback_template)
    await _seed_companion(companion_user_id, status=VerificationStatus.verified)

    async with _session_factory() as session:
        agg = OrderPrecheckAggregator(_FakeRedis(), session=session)
        summary = await agg.evaluate(order_id)

    assert summary["preparation_status"]["ready"] is True
    assert summary["all_ready"] is True


# ---------------------------------------------------------------------------
# ABAC Layer 3: negative-list field absence
# ---------------------------------------------------------------------------


async def test_evaluate_does_not_leak_contract_negative_list_fields() -> None:
    """Contract View must NOT contain negative-list fields.

    Forbidden: ``contract_hash`` / ``hash_inputs`` / ``storage_blob_path`` /
    ``template_key``.
    """
    companion_user_id = uuid4()
    order_id = await _seed_order(companion_id=companion_user_id)
    await _seed_contract(order_id, status=ContractStatus.active)
    await _seed_insurance(order_id, status=InsuranceStatus.active)
    await _seed_prep(order_id, status=PrepStatus.active)
    await _seed_companion(companion_user_id, status=VerificationStatus.verified)

    async with _session_factory() as session:
        agg = OrderPrecheckAggregator(_FakeRedis(), session=session)
        summary = await agg.evaluate(order_id)

    contract = summary["contract_status"]
    for forbidden in (
        "contract_hash",
        "hash_inputs",
        "storage_blob_path",
        "template_key",
    ):
        assert forbidden not in contract, (
            f"Contract View leaked negative-list field {forbidden!r}; "
            f"ABAC Layer 1 schema guard or Layer 3 SELECT regressed."
        )


async def test_evaluate_does_not_leak_companion_negative_list_fields() -> None:
    """Companion View must NOT contain real_name / id_card / phone / user_id."""
    companion_user_id = uuid4()
    order_id = await _seed_order(companion_id=companion_user_id)
    await _seed_contract(order_id, status=ContractStatus.active)
    await _seed_insurance(order_id, status=InsuranceStatus.active)
    await _seed_prep(order_id, status=PrepStatus.active)
    await _seed_companion(companion_user_id, status=VerificationStatus.verified)

    async with _session_factory() as session:
        agg = OrderPrecheckAggregator(_FakeRedis(), session=session)
        summary = await agg.evaluate(order_id)

    companion = summary["companion_cert_status"]
    for forbidden in (
        "companion_real_name",
        "companion_id_card_hash",
        "companion_phone",
        "companion_user_id",
        "real_name",
        "id_number",
    ):
        assert forbidden not in companion, (
            f"Companion View leaked negative-list field {forbidden!r}; "
            f"ABAC Layer 1 schema guard regressed."
        )


async def test_evaluate_does_not_leak_prep_internal_fields() -> None:
    """Prep View must NOT contain prompt_version / model / cost / trace."""
    companion_user_id = uuid4()
    order_id = await _seed_order(companion_id=companion_user_id)
    await _seed_contract(order_id, status=ContractStatus.active)
    await _seed_insurance(order_id, status=InsuranceStatus.active)
    await _seed_prep(order_id, status=PrepStatus.active)
    await _seed_companion(companion_user_id, status=VerificationStatus.verified)

    async with _session_factory() as session:
        agg = OrderPrecheckAggregator(_FakeRedis(), session=session)
        summary = await agg.evaluate(order_id)

    prep = summary["preparation_status"]
    for forbidden in (
        "prompt_version",
        "model_used",
        "raw_llm_output",
        "cost_yuan",
        "actual_cost_yuan",
        "estimated_cost_yuan",
        "trace_id",
        "model",
        "prompt_version_id",
    ):
        assert forbidden not in prep, f"Prep View leaked negative-list field {forbidden!r}."


# ---------------------------------------------------------------------------
# _redis_set + invalidate_and_recompute orchestration
# ---------------------------------------------------------------------------


async def test_invalidate_and_recompute_sets_cache_with_5min_ttl() -> None:
    """Orchestrator writes ``precheck:order:{id}`` with TTL 300s."""
    companion_user_id = uuid4()
    order_id = await _seed_order(companion_id=companion_user_id)
    await _seed_contract(order_id, status=ContractStatus.active)
    await _seed_insurance(order_id, status=InsuranceStatus.active)
    await _seed_prep(order_id, status=PrepStatus.active)
    await _seed_companion(companion_user_id, status=VerificationStatus.verified)

    redis = _FakeRedis()
    async with _session_factory() as session:
        agg = OrderPrecheckAggregator(redis, session=session)
        result = await agg.invalidate_and_recompute(order_id)

    key = _build_cache_key(order_id)
    assert result["invalidated_keys"] == [key]
    assert result["broadcast"] is False  # c2 stub
    assert redis.ttl_for(key) == 300

    payload = await redis.get(key)
    assert payload is not None
    parsed = json.loads(payload)
    assert parsed["order_id"] == str(order_id)
    assert parsed["all_ready"] is True


async def test_invalidate_and_recompute_overwrites_stale_cache() -> None:
    """DEL before SET → final value is the fresh aggregate, not stale."""
    companion_user_id = uuid4()
    order_id = await _seed_order(companion_id=companion_user_id)
    await _seed_contract(order_id, status=ContractStatus.active)
    await _seed_insurance(order_id, status=InsuranceStatus.active)
    await _seed_prep(order_id, status=PrepStatus.active)
    await _seed_companion(companion_user_id, status=VerificationStatus.verified)

    redis = _FakeRedis()
    key = _build_cache_key(order_id)
    await redis.set(key, '{"stale": "summary"}')
    assert await redis.get(key) is not None

    async with _session_factory() as session:
        agg = OrderPrecheckAggregator(redis, session=session)
        await agg.invalidate_and_recompute(order_id)

    fresh = await redis.get(key)
    parsed = json.loads(fresh)
    assert parsed["order_id"] == str(order_id)
    assert "stale" not in parsed


# ---------------------------------------------------------------------------
# _mask_policy_no helper
# ---------------------------------------------------------------------------


def test_mask_policy_no_long_string_returns_head4_stars_tail4() -> None:
    assert _mask_policy_no("BX2026123456781234") == "BX20****1234"


def test_mask_policy_no_short_string_returns_unchanged() -> None:
    # 太短不脱敏 (placeholder).
    assert _mask_policy_no("ABCD1234") == "ABCD1234"


def test_mask_policy_no_none_returns_none() -> None:
    assert _mask_policy_no(None) is None


# ---------------------------------------------------------------------------
# Caller invariant: missing session
# ---------------------------------------------------------------------------


async def test_evaluate_raises_when_session_not_injected() -> None:
    """Constructor allows None session for invalidate-only callers, but
    ``evaluate`` must reject."""
    redis = _FakeRedis()
    agg = OrderPrecheckAggregator(redis)  # no session
    with pytest.raises(ValueError, match="requires a session"):
        await agg.evaluate(uuid4())


# ---------------------------------------------------------------------------
# _ws_broadcast c2 stub: returns False, does not raise
# ---------------------------------------------------------------------------


async def test_ws_broadcast_returns_false_in_c2() -> None:
    """c2 stub: ``_ws_broadcast`` returns False (c4 WS infra flips to True)."""
    redis = _FakeRedis()
    agg = OrderPrecheckAggregator(redis)
    result = await agg._ws_broadcast(uuid4(), ("contract",))
    assert result is False
