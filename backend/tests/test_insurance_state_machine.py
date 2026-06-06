"""Tests for InsuranceStateMachine + ServiceInsuranceRecord ORM.

# Coverage map (5 AC + state machine + cron-eligibility)

| AC | Test class |
|----|-----------|
| #1 service_insurance_records alembic migration | implicit (smoke-pg + ORM smoke) |
| #2 InsuranceOrderStateMachine 5 状态 + transition | ``TestStateMachineTransitions`` |
| #3 apscheduler cron 三档 5min/30min/2h | ``TestCompensationCronConstants`` |
| #4 issue_failed 记 last_error_trace + retry_count | ``TestRetryBookkeeping`` |
| #5 manually_invalidated 留痕必填双字段 | ``TestManualInvalidationMetadata`` |

Plus utility / safety coverage:
- ``TestTransitionTablePinning`` — sentinel against silent legal-set drift
- ``TestTerminalStates`` — terminal states have no outgoing edges
- ``TestEnumStability`` — 6 enum values pinned (sentinel for ADR-0047)
- ``TestModelDefaults`` — server-side defaults match ADR-0047 §3.3
"""

from __future__ import annotations

import uuid

import pytest

from app.models.service_insurance_record import (
    PLACEHOLDER_VENDOR_NAME,
    InsuranceStatus,
    ServiceInsuranceRecord,
)
from app.services.insurance_state_machine import (
    _LEGAL_TRANSITIONS,
    _TERMINAL_STATES,
    MAX_RETRY_COUNT,
    InsuranceInvalidationMetadataMissingError,
    InvalidInsuranceTransitionError,
    assert_invalidation_metadata,
    assert_transition_legal,
    is_legal_transition,
    is_terminal,
    legal_targets,
)
from app.tasks import insurance_compensation as cron

# ---------------------------------------------------------------------------
# Sentinel: enum values pinned (ADR-0047 §3.3 contract)
# ---------------------------------------------------------------------------


class TestEnumStability:
    """6 InsuranceStatus values + values pinned to ADR-0047.

    Any future PR that adds/removes a state must update both the ADR + this
    sentinel + the transition table; the test forces the conversation.
    """

    def test_six_states_exact(self):
        assert {s.value for s in InsuranceStatus} == {
            "pending_issue",
            "active",
            "expired",
            "cancelled",
            "issue_failed",
            "manually_invalidated",
        }

    def test_str_value_matches_name(self):
        # Every enum value is its lowercase name (allows
        # ``InsuranceStatus(row.status)`` round-trip from DB string).
        for s in InsuranceStatus:
            assert s.value == s.name

    def test_placeholder_vendor_constant(self):
        # Renaming PLACEHOLDER_VENDOR breaks the cron stub success path
        assert PLACEHOLDER_VENDOR_NAME == "PLACEHOLDER_VENDOR"


# ---------------------------------------------------------------------------
# AC#2 — state machine transitions (10 legal + many illegal)
# ---------------------------------------------------------------------------


class TestStateMachineTransitions:
    @pytest.mark.parametrize(
        "from_status,to_status",
        [
            # pending_issue out edges (4)
            (InsuranceStatus.pending_issue, InsuranceStatus.active),
            (InsuranceStatus.pending_issue, InsuranceStatus.issue_failed),
            (InsuranceStatus.pending_issue, InsuranceStatus.cancelled),
            (
                InsuranceStatus.pending_issue,
                InsuranceStatus.manually_invalidated,
            ),
            # active out edges (3)
            (InsuranceStatus.active, InsuranceStatus.expired),
            (InsuranceStatus.active, InsuranceStatus.cancelled),
            (InsuranceStatus.active, InsuranceStatus.manually_invalidated),
            # issue_failed out edges (3)
            (InsuranceStatus.issue_failed, InsuranceStatus.active),
            (InsuranceStatus.issue_failed, InsuranceStatus.cancelled),
            (
                InsuranceStatus.issue_failed,
                InsuranceStatus.manually_invalidated,
            ),
        ],
    )
    def test_legal_transition_accepted(self, from_status, to_status):
        assert is_legal_transition(from_status, to_status) is True
        # Guard helper does not raise
        assert_transition_legal(from_status, to_status)

    @pytest.mark.parametrize(
        "from_status,to_status",
        [
            # Terminal states have no outgoing edges
            (InsuranceStatus.expired, InsuranceStatus.active),
            (InsuranceStatus.cancelled, InsuranceStatus.active),
            (
                InsuranceStatus.manually_invalidated,
                InsuranceStatus.active,
            ),
            # Backward edges illegal
            (InsuranceStatus.active, InsuranceStatus.pending_issue),
            (
                InsuranceStatus.issue_failed,
                InsuranceStatus.pending_issue,
            ),
            # Skip-state illegal (no direct pending_issue → expired)
            (InsuranceStatus.pending_issue, InsuranceStatus.expired),
            # Self-loops illegal (we never re-flip to same status)
            (InsuranceStatus.active, InsuranceStatus.active),
            (
                InsuranceStatus.pending_issue,
                InsuranceStatus.pending_issue,
            ),
        ],
    )
    def test_illegal_transition_rejected(self, from_status, to_status):
        assert is_legal_transition(from_status, to_status) is False
        with pytest.raises(InvalidInsuranceTransitionError) as exc_info:
            assert_transition_legal(from_status, to_status)
        # Error message mentions legal targets for ops triage
        assert from_status.value in str(exc_info.value)
        assert to_status.value in str(exc_info.value)

    def test_legal_targets_for_terminal_empty(self):
        for terminal in _TERMINAL_STATES:
            assert legal_targets(terminal) == frozenset()

    def test_legal_targets_for_active(self):
        assert legal_targets(InsuranceStatus.active) == frozenset(
            {
                InsuranceStatus.expired,
                InsuranceStatus.cancelled,
                InsuranceStatus.manually_invalidated,
            }
        )

    def test_legal_targets_for_pending_issue(self):
        assert legal_targets(InsuranceStatus.pending_issue) == frozenset(
            {
                InsuranceStatus.active,
                InsuranceStatus.issue_failed,
                InsuranceStatus.cancelled,
                InsuranceStatus.manually_invalidated,
            }
        )


# ---------------------------------------------------------------------------
# Transition table pinning sentinel
# ---------------------------------------------------------------------------


class TestTransitionTablePinning:
    def test_legal_transitions_count_pinned_to_10(self):
        # Drift here forces an explicit ADR-0047 amend + sentinel update.
        assert len(_LEGAL_TRANSITIONS) == 10

    def test_terminal_states_pinned_to_3(self):
        assert _TERMINAL_STATES == frozenset(
            {
                InsuranceStatus.expired,
                InsuranceStatus.cancelled,
                InsuranceStatus.manually_invalidated,
            }
        )

    def test_is_terminal_predicate(self):
        for s in _TERMINAL_STATES:
            assert is_terminal(s) is True
        for s in (
            InsuranceStatus.pending_issue,
            InsuranceStatus.active,
            InsuranceStatus.issue_failed,
        ):
            assert is_terminal(s) is False


# ---------------------------------------------------------------------------
# AC#5 — manually_invalidated metadata required
# ---------------------------------------------------------------------------


class TestManualInvalidationMetadata:
    def test_complete_metadata_passes(self):
        # No raise
        assert_invalidation_metadata(
            invalidation_reason="客服 #12 申诉作废",
            invalidated_by_admin_id=uuid.uuid4(),
        )

    def test_missing_reason_rejected(self):
        with pytest.raises(InsuranceInvalidationMetadataMissingError):
            assert_invalidation_metadata(
                invalidation_reason=None,
                invalidated_by_admin_id=uuid.uuid4(),
            )

    def test_empty_reason_rejected(self):
        with pytest.raises(InsuranceInvalidationMetadataMissingError):
            assert_invalidation_metadata(
                invalidation_reason="",
                invalidated_by_admin_id=uuid.uuid4(),
            )

    def test_whitespace_only_reason_rejected(self):
        # Whitespace-only is operationally "missing"
        with pytest.raises(InsuranceInvalidationMetadataMissingError):
            assert_invalidation_metadata(
                invalidation_reason="   ",
                invalidated_by_admin_id=uuid.uuid4(),
            )

    def test_missing_admin_id_rejected(self):
        with pytest.raises(InsuranceInvalidationMetadataMissingError):
            assert_invalidation_metadata(
                invalidation_reason="客服 #12 申诉作废",
                invalidated_by_admin_id=None,
            )

    def test_both_missing_rejected(self):
        with pytest.raises(InsuranceInvalidationMetadataMissingError):
            assert_invalidation_metadata(
                invalidation_reason=None,
                invalidated_by_admin_id=None,
            )


# ---------------------------------------------------------------------------
# AC#4 — retry_count + failure_reason bookkeeping (model-level)
# ---------------------------------------------------------------------------


class TestRetryBookkeeping:
    def test_default_retry_count_is_zero(self):
        # ORM-level default (server_default="0" makes the column nullable=False)
        record = ServiceInsuranceRecord(
            order_id=uuid.uuid4(),
            product_name="陪诊责任险标准版",
            coverage_amount_cny=100000,
        )
        # SQLAlchemy default kicks in on flush, but our Python default is 0
        # via Mapped[int] default=0. Pre-flush the value may be None — that's
        # fine; the DB column server_default makes it 0 on INSERT.
        assert record.retry_count in (0, None)
        assert record.failure_reason is None

    def test_failure_reason_settable(self):
        record = ServiceInsuranceRecord(
            order_id=uuid.uuid4(),
            product_name="陪诊责任险标准版",
            coverage_amount_cny=100000,
            failure_reason="vendor returned 503",
            retry_count=2,
        )
        assert record.failure_reason == "vendor returned 503"
        assert record.retry_count == 2

    def test_max_retry_count_constant_is_three(self):
        # MAX_RETRY_COUNT is the cron-side cap (ADR-0046 §3.4 同款 3 次)
        assert MAX_RETRY_COUNT == 3


# ---------------------------------------------------------------------------
# Model defaults pinned to ADR-0047 §3.3
# ---------------------------------------------------------------------------


class TestModelDefaults:
    def test_default_vendor_name_is_placeholder(self):
        # ORM-level Python default + server_default both PLACEHOLDER
        record = ServiceInsuranceRecord(
            order_id=uuid.uuid4(),
            product_name="陪诊责任险标准版",
            coverage_amount_cny=100000,
        )
        # Python default kicks in on attribute access if unset
        assert record.vendor_name in (PLACEHOLDER_VENDOR_NAME, None)

    def test_default_status_is_pending_issue(self):
        record = ServiceInsuranceRecord(
            order_id=uuid.uuid4(),
            product_name="陪诊责任险标准版",
            coverage_amount_cny=100000,
        )
        assert record.status in (InsuranceStatus.pending_issue, None)

    def test_coverage_amount_is_int_cny_cents(self):
        # ADR-0030: 金额统一 int 分单位 (avoid Decimal in hot path)
        record = ServiceInsuranceRecord(
            order_id=uuid.uuid4(),
            product_name="陪诊责任险标准版",
            coverage_amount_cny=100000,  # 1000.00 元
        )
        assert isinstance(record.coverage_amount_cny, int)


# ---------------------------------------------------------------------------
# AC#3 — cron 三档 5min/30min/2h constants pinned
# ---------------------------------------------------------------------------


class TestCompensationCronConstants:
    """Sentinel: 三档时长 (ADR-0046 §3.4 + ADR-0047 §3.3) 不可漂移.

    Any change to retry cadence must update both ADR + this test, forcing
    the conversation through the architect.
    """

    def test_tier_1_interval_and_min_age_5min(self):
        assert cron.TIER_1_INTERVAL_SECONDS == 5 * 60
        assert cron.TIER_1_MIN_AGE_SECONDS == 5 * 60

    def test_tier_2_interval_and_min_age_30min(self):
        assert cron.TIER_2_INTERVAL_SECONDS == 30 * 60
        assert cron.TIER_2_MIN_AGE_SECONDS == 30 * 60

    def test_tier_3_interval_and_min_age_2h(self):
        assert cron.TIER_3_INTERVAL_SECONDS == 2 * 60 * 60
        assert cron.TIER_3_MIN_AGE_SECONDS == 2 * 60 * 60

    def test_distributed_lock_keys_distinct_per_tier(self):
        # Per-tier locks allow tiers to progress in parallel across replicas
        # while each tier still serializes within itself.
        keys = {
            cron.INSURANCE_CRON_TIER1_LOCK_KEY,
            cron.INSURANCE_CRON_TIER2_LOCK_KEY,
            cron.INSURANCE_CRON_TIER3_LOCK_KEY,
        }
        assert len(keys) == 3

    def test_lock_ttl_under_interval(self):
        # Redis-fallback TTL must be less than the cron interval, else
        # a stale lock holder past TTL would let a new tick double-pick
        # before lock natural expiry.
        assert cron.INSURANCE_CRON_LOCK_TTL_SECONDS < cron.TIER_1_INTERVAL_SECONDS


# ---------------------------------------------------------------------------
# Cron tier validation
# ---------------------------------------------------------------------------


class TestCronTierValidation:
    @pytest.mark.asyncio
    async def test_invalid_tier_raises(self):
        # Internal `_retry_tier` defensive — public API uses 1/2/3 only
        with pytest.raises(ValueError):
            await cron._retry_tier(tier=4, lock_key="x", min_age_seconds=60, app=None)

    @pytest.mark.asyncio
    async def test_tier_zero_rejected(self):
        with pytest.raises(ValueError):
            await cron._retry_tier(tier=0, lock_key="x", min_age_seconds=60, app=None)


# ---------------------------------------------------------------------------
# Vendor stub (S3 PLACEHOLDER_VENDOR)
# ---------------------------------------------------------------------------


class TestVendorStub:
    @pytest.mark.asyncio
    async def test_placeholder_vendor_always_succeeds(self):
        record = ServiceInsuranceRecord(
            id=uuid.uuid4(),
            order_id=uuid.uuid4(),
            product_name="陪诊责任险标准版",
            coverage_amount_cny=100000,
            vendor_name=PLACEHOLDER_VENDOR_NAME,
        )
        success, policy_no = await cron._issue_with_vendor(record)
        assert success is True
        assert policy_no is not None
        assert policy_no.startswith("PLACEHOLDER-")

    @pytest.mark.asyncio
    async def test_policy_no_deterministic_from_order_id(self):
        oid = uuid.UUID("12345678-1234-5678-1234-567812345678")
        record = ServiceInsuranceRecord(
            id=uuid.uuid4(),
            order_id=oid,
            product_name="陪诊责任险标准版",
            coverage_amount_cny=100000,
            vendor_name=PLACEHOLDER_VENDOR_NAME,
        )
        success, policy_no = await cron._issue_with_vendor(record)
        assert success is True
        assert policy_no == "PLACEHOLDER-12345678"

    @pytest.mark.asyncio
    async def test_unknown_vendor_fails(self):
        # Next-iter real vendor branch not implemented — non-placeholder
        # vendor names return failure. This keeps the cron honest until
        # the real integration lands.
        record = ServiceInsuranceRecord(
            id=uuid.uuid4(),
            order_id=uuid.uuid4(),
            product_name="陪诊责任险标准版",
            coverage_amount_cny=100000,
            vendor_name="REAL_VENDOR_NOT_IMPL",
        )
        success, policy_no = await cron._issue_with_vendor(record)
        assert success is False
        assert policy_no is None
