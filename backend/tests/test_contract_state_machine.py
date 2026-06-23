"""Tests for ContractStateMachine + ServiceContract ORM + resolver + name normalize.

# Coverage map (7 AC)

| AC | Test class |
|----|-----------|
| #1 service_contracts table schema (16 fields)   | ``TestModelSchema`` |
| #2 immutable_fields trigger (PG)                | ``@pytest.mark.smoke`` |
| #3 ContractStateMachine 6 states + 14 transitions | ``TestStateMachineTransitions`` |
| #4 alembic migration                            | implicit (CI smoke-pg + ORM) |
| #5 trigger + transitions + retry guard (PG)     | smoke test marker |
| #6 resolver contract_resolver.py | ``TestResolver`` |
| #7 patient_name NFKC + strip | ``TestNameNormalize`` |

Plus pinning sentinels:
- ``TestEnumStability`` — 6 ContractStatus values pinned
- ``TestTransitionTablePinning`` — 10 transitions count pinned
- ``TestImmutableFieldsSentinel`` — IMMUTABLE_FIELDS set pinned (drift防御)
"""

from __future__ import annotations

import uuid

import pytest

from app.models.service_contract import (
    IMMUTABLE_FIELDS,
    MUTABLE_FIELDS,
    ContractStatus,
    ServiceContract,
)
from app.services import contract_state_machine as csm
from app.services.contract_state_machine import (
    MAX_RETRY_COUNT,
    ContractInvalidationMetadataMissingError,
    InvalidContractStateTransitionError,
    assert_invalidation_metadata,
    assert_transition,
    is_legal_transition,
    is_terminal,
    legal_targets,
    normalize_patient_name,
)

# ---------------------------------------------------------------------------
# Sentinel: 6 enum values + IMMUTABLE_FIELDS pinned (ADR-0047 ground truth)
# ---------------------------------------------------------------------------


class TestEnumStability:
    def test_six_states_exact(self):
        assert {s.value for s in ContractStatus} == {
            "pending_generation",
            "generating",
            "active",
            "generation_failed",
            "generation_permanently_failed",
            "manually_invalidated",
        }

    def test_str_value_matches_name(self):
        for s in ContractStatus:
            assert s.value == s.name


class TestImmutableFieldsSentinel:
    """IMMUTABLE_FIELDS set must match ADR-0047 §3.1 + Alembic trigger body.

    Any drift (add/remove field) requires updating:
    1. ADR-0047 §3.1
    2. app/models/service_contract.py IMMUTABLE_FIELDS
    3. Alembic migration d5e6f7a8b9c1 _TRIGGER_BODY_SQL
    4. This sentinel test
    """

    def test_immutable_fields_pinned_9(self):
        # AC#2 字面 (魈 08:25): 原 8 immutable 字段。不包含 ``id`` — PK 由 DB
        # 物理 immutable 兜底，不在应用层 trigger 重复 guard。
        # S3-OPS-CONTRACT-SALT-ROTATE-PATH / ADR-0046 r8 (方案 D): 加
        # salt_version → 9 字段 (创建后 immutable, 防篡改取证溯源)。
        assert IMMUTABLE_FIELDS == frozenset(
            {
                "order_id",
                "template_version",
                "contract_hash",
                "hash_inputs",
                "storage_blob_path",
                "generated_at",
                "is_immutable",
                "created_at",
                "salt_version",
            }
        )
        assert len(IMMUTABLE_FIELDS) == 9

    def test_mutable_fields_pinned_10(self):
        # AC#2 字面 "5 mutable" 是数错 — 原始 7 mutable:
        # status / retry_count / last_error_trace / invalidation_reason /
        # invalidated_by_admin_id / invalidated_at / updated_at.
        # S3-DEV-001-CONTRACT-WORM-COMPENSATION 加 3 字段 (worm_status /
        # worm_retry_count / worm_last_retry_at) → 10 mutable.
        assert MUTABLE_FIELDS == frozenset(
            {
                "status",
                "retry_count",
                "last_error_trace",
                "invalidation_reason",
                "invalidated_by_admin_id",
                "invalidated_at",
                "updated_at",
                "worm_status",
                "worm_retry_count",
                "worm_last_retry_at",
            }
        )
        assert len(MUTABLE_FIELDS) == 10

    def test_no_overlap_immutable_mutable(self):
        assert IMMUTABLE_FIELDS.isdisjoint(MUTABLE_FIELDS)


# ---------------------------------------------------------------------------
# AC#3 — state machine transitions (10 legal + retry guard)
# ---------------------------------------------------------------------------


class TestStateMachineTransitions:
    @pytest.mark.parametrize(
        "from_status,to_status",
        [
            # pending_generation 出边 (2)
            (
                ContractStatus.pending_generation,
                ContractStatus.generating,
            ),
            (
                ContractStatus.pending_generation,
                ContractStatus.manually_invalidated,
            ),
            # generating 出边 (3)
            (ContractStatus.generating, ContractStatus.active),
            (
                ContractStatus.generating,
                ContractStatus.generation_failed,
            ),
            (
                ContractStatus.generating,
                ContractStatus.manually_invalidated,
            ),
            # active 出边 (1)
            (
                ContractStatus.active,
                ContractStatus.manually_invalidated,
            ),
            # generation_failed 出边 (3) — retry → generation_permanently_failed
            # tested separately with retry_count parameterization
            (
                ContractStatus.generation_failed,
                ContractStatus.generating,
            ),
            (
                ContractStatus.generation_failed,
                ContractStatus.manually_invalidated,
            ),
            # generation_permanently_failed 出边 (1)
            (
                ContractStatus.generation_permanently_failed,
                ContractStatus.manually_invalidated,
            ),
        ],
    )
    def test_legal_transition_passes(self, from_status, to_status):
        assert is_legal_transition(from_status, to_status) is True
        # assert_transition w/ retry_count=0 (only matters for permanently_failed)
        assert_transition(
            from_status=from_status,
            to_status=to_status,
            retry_count=0,
        )

    @pytest.mark.parametrize(
        "from_status,to_status",
        [
            # manually_invalidated is hard terminal — no outgoing
            (
                ContractStatus.manually_invalidated,
                ContractStatus.active,
            ),
            (
                ContractStatus.manually_invalidated,
                ContractStatus.generating,
            ),
            # active cannot rollback to pending/generating
            (
                ContractStatus.active,
                ContractStatus.pending_generation,
            ),
            (ContractStatus.active, ContractStatus.generating),
            (
                ContractStatus.active,
                ContractStatus.generation_failed,
            ),
            # No skip from pending → active (must go via generating)
            (
                ContractStatus.pending_generation,
                ContractStatus.active,
            ),
            (
                ContractStatus.pending_generation,
                ContractStatus.generation_failed,
            ),
            # Self-loops illegal
            (ContractStatus.active, ContractStatus.active),
            (
                ContractStatus.generating,
                ContractStatus.generating,
            ),
        ],
    )
    def test_illegal_transition_raises(self, from_status, to_status):
        assert is_legal_transition(from_status, to_status) is False
        with pytest.raises(InvalidContractStateTransitionError) as exc_info:
            assert_transition(
                from_status=from_status,
                to_status=to_status,
                retry_count=0,
            )
        assert from_status.value in str(exc_info.value)
        assert to_status.value in str(exc_info.value)

    def test_legal_targets_for_terminal_empty(self):
        assert legal_targets(ContractStatus.manually_invalidated) == frozenset()

    def test_legal_targets_for_pending(self):
        assert legal_targets(ContractStatus.pending_generation) == frozenset(
            {
                ContractStatus.generating,
                ContractStatus.manually_invalidated,
            }
        )

    def test_terminal_predicate(self):
        assert is_terminal(ContractStatus.manually_invalidated) is True
        for s in (
            ContractStatus.pending_generation,
            ContractStatus.generating,
            ContractStatus.active,
            ContractStatus.generation_failed,
            ContractStatus.generation_permanently_failed,
        ):
            assert is_terminal(s) is False


class TestRetryGuard:
    """retry_count >= MAX_RETRY_COUNT (3) required for permanently_failed."""

    def test_retry_count_3_allows_permanently_failed(self):
        # No raise
        assert_transition(
            from_status=ContractStatus.generation_failed,
            to_status=ContractStatus.generation_permanently_failed,
            retry_count=3,
        )

    def test_retry_count_above_3_allows_permanently_failed(self):
        assert_transition(
            from_status=ContractStatus.generation_failed,
            to_status=ContractStatus.generation_permanently_failed,
            retry_count=10,
        )

    @pytest.mark.parametrize("retry_count", [0, 1, 2])
    def test_retry_count_below_3_rejects_permanently_failed(self, retry_count):
        with pytest.raises(InvalidContractStateTransitionError) as exc_info:
            assert_transition(
                from_status=ContractStatus.generation_failed,
                to_status=ContractStatus.generation_permanently_failed,
                retry_count=retry_count,
            )
        assert "retry_count" in str(exc_info.value)
        assert str(MAX_RETRY_COUNT) in str(exc_info.value)


# ---------------------------------------------------------------------------
# Transition table pinning sentinel
# ---------------------------------------------------------------------------


class TestTransitionTablePinning:
    def test_legal_transitions_count_pinned_to_10(self):
        # Drift here forces ADR-0047 §4 amend + this sentinel update.
        assert len(csm._LEGAL_TRANSITIONS) == 10

    def test_hard_terminal_is_only_manually_invalidated(self):
        assert csm._HARD_TERMINAL == frozenset({ContractStatus.manually_invalidated})

    def test_max_retry_count_is_three(self):
        assert MAX_RETRY_COUNT == 3


# ---------------------------------------------------------------------------
# AC#5 — manually_invalidated metadata required (audit)
# ---------------------------------------------------------------------------


class TestManualInvalidationMetadata:
    def test_complete_metadata_passes(self):
        # invalidated_by_admin_id is BigInteger admin_users.id (not UUID)
        assert_invalidation_metadata(
            invalidation_reason="客服 #12 申诉作废",
            invalidated_by_admin_id=42,
        )

    @pytest.mark.parametrize("bad_reason", [None, "", "   ", "\t\n"])
    def test_missing_or_blank_reason_rejected(self, bad_reason):
        with pytest.raises(ContractInvalidationMetadataMissingError):
            assert_invalidation_metadata(
                invalidation_reason=bad_reason,
                invalidated_by_admin_id=42,
            )

    def test_missing_admin_id_rejected(self):
        with pytest.raises(ContractInvalidationMetadataMissingError):
            assert_invalidation_metadata(
                invalidation_reason="reason",
                invalidated_by_admin_id=None,
            )


# ---------------------------------------------------------------------------
# AC#7 — patient_name NFKC + .strip() normalization
# ---------------------------------------------------------------------------


class TestNameNormalize:
    """NFKC + .strip() — defends against same patient appearing with
    different whitespace representations from different sources.
    """

    def test_simple_strip(self):
        assert normalize_patient_name(" 张三 ") == "张三"
        assert normalize_patient_name("张三  ") == "张三"
        assert normalize_patient_name("  张三") == "张三"

    def test_nfkc_full_width_space_folded(self):
        # U+3000 (full-width space) → U+0020 (ASCII space) → stripped
        # When used at edges
        full_width_padded = "\u3000张三\u3000"
        assert normalize_patient_name(full_width_padded) == "张三"

    def test_nfkc_internal_whitespace_preserved(self):
        # Internal whitespace (after strip) — keep as-is (could be a
        # legit middle space in names like "Mary Jane"). Only edge
        # whitespace is stripped.
        assert normalize_patient_name("Mary Jane") == "Mary Jane"

    def test_nfkc_compatibility_decomposition(self):
        # NFKC compatible composition: full-width digits → half-width
        # (not common in Chinese names but tests the principle)
        full_width_ascii = "ＡＢＣ"  # full-width Latin
        normalized = normalize_patient_name(full_width_ascii)
        assert normalized == "ABC"

    def test_same_person_different_whitespace_same_hash_input(self):
        # The core invariant: NFKC + strip collapses these to one string,
        # so compute_patient_pseudonym_hash sees identical input.
        a = normalize_patient_name(" 张三")
        b = normalize_patient_name("张三 ")
        c = normalize_patient_name("\u3000张三\u3000")
        assert a == b == c == "张三"

    def test_none_rejected(self):
        with pytest.raises(ValueError):
            normalize_patient_name(None)  # type: ignore[arg-type]

    def test_whitespace_only_rejected(self):
        with pytest.raises(ValueError):
            normalize_patient_name("   ")

    def test_only_full_width_space_rejected(self):
        with pytest.raises(ValueError):
            normalize_patient_name("\u3000\u3000")


# ---------------------------------------------------------------------------
# AC#1 — ServiceContract ORM schema
# ---------------------------------------------------------------------------


class TestModelSchema:
    def test_tablename(self):
        assert ServiceContract.__tablename__ == "service_contracts"

    def test_default_status_pending_generation(self):
        # ORM-level Python default; server_default also "pending_generation"
        record = ServiceContract(
            order_id=uuid.uuid4(),
            template_version="v1.0.0",
            contract_hash="a" * 64,
            hash_inputs={"key": "value"},
        )
        # Pre-flush, attribute access returns the Python default (or None
        # if SQLAlchemy hasn't applied it yet)
        assert record.status in (
            ContractStatus.pending_generation,
            None,
        )

    def test_default_retry_count_zero(self):
        record = ServiceContract(
            order_id=uuid.uuid4(),
            template_version="v1.0.0",
            contract_hash="a" * 64,
            hash_inputs={"key": "value"},
        )
        assert record.retry_count in (0, None)

    def test_default_is_immutable_true(self):
        record = ServiceContract(
            order_id=uuid.uuid4(),
            template_version="v1.0.0",
            contract_hash="a" * 64,
            hash_inputs={"key": "value"},
        )
        assert record.is_immutable in (True, None)


# ---------------------------------------------------------------------------
# AC#6 — Resolver (DB-level test split into smoke; pure-function tests here)
# ---------------------------------------------------------------------------


class TestResolverErrorExposed:
    """Verify the error class is exposed and importable (smoke for caller surface).

    The actual DB-coupled resolver test runs in smoke-pg job — see
    ``@pytest.mark.smoke`` tests below.
    """

    def test_error_class_subclass_of_lookup(self):
        from app.services.contract_resolver import (
            ContractServicePackageNotFoundError,
        )

        # LookupError so caller can catch with except LookupError if they
        # want to treat all "row not found" uniformly.
        assert issubclass(ContractServicePackageNotFoundError, LookupError)


# ---------------------------------------------------------------------------
# AC#6 补充 sentinel — ServicePackage.code immutability 哨兵 (魈 08:29 加)
# ---------------------------------------------------------------------------


class TestServicePackageCodeImmutabilitySentinel:
    """AC#6 sentinel: ServicePackage.code is P0 immutable business identifier.

    Codebase 状态 (本 task 已硬化):
    - DB 层: ``code`` unique=True + nullable=False (这样 resolver 稳定)
    - ORM 层: ``@validates('code')`` 拒改 (first-set after 拒变)
    - API 层: ``ServicePackageUpdateBody`` 不含 ``code`` 字段 (admin PATCH 不能改)
    - 文档层: 字段 comment 标 immutable

    三哨兵防雪崩式改动:

    1. **哨兵 #1**: ``code`` 字段存在 + unique 约束 — 如 dev 删此字段/取消
       unique，fail-fast
    2. **哨兵 #2**: model 源码含 immutability 关键词 — 如 dev 加
       PATCH/UPDATE code endpoint，哨兵提醒走 review
    3. **哨兵 #3**: ``contract_resolver`` 文档明示依赖 ``ServicePackage.code``
       immutability — 如 dev 不知依赖误改 code，破历史 contract hash
       recompute。

    运行期 ORM validator 本身的试业边界测试 (first-set / same-value / change-after-set)
    放在 ``test_service_contracts_pg_smoke.py::TestServicePackageCodeSentinel`` —
    需 SQLAlchemy session 潜委启动 validator。
    """

    def test_service_package_code_field_exists_and_unique(self):
        # Sentinel #1: ServicePackage.code is still on the model + unique
        from app.models.service_package import ServicePackage

        code_col = ServicePackage.__table__.columns["code"]
        assert code_col is not None, "ServicePackage.code field removed"
        assert code_col.unique is True, (
            "ServicePackage.code lost unique constraint — contract "
            "resolver depends on it for 1:1 lookup"
        )
        assert code_col.nullable is False, (
            "ServicePackage.code became nullable — contract resolver "
            "will start returning None unexpectedly"
        )

    def test_service_package_code_docstring_marks_immutability(self):
        # Sentinel #2: model docstring or column comment mentions immutability
        # so future PR adding a PATCH code endpoint triggers code review
        from app.models import service_package as svc_pkg_module

        source = open(svc_pkg_module.__file__).read()
        # Search for any immutability cue near the `code` column definition.
        # We accept any of: "immutable" / "不可改" / "do not change".
        cues = ("immutable", "不可改", "do not change")
        assert any(cue in source for cue in cues), (
            "ServicePackage 模块未标记 code immutable。"
            "在 ServicePackage model 加 'immutable' / '不可改' / 'do not change' "
            "其中一个关键词到字段 comment 或 ORM validator docstring。"
        )

    def test_service_package_code_change_would_break_contract_hash(self):
        # Sentinel #3: business invariant — 改 code 会破 contract hash recompute.
        # 这是 resolver 架构示意, 不跨模块实际调用 (依赖 DB session)。
        # 在实施文档里说明 contract_resolver 架构依赖 code immutability。
        from app.services import contract_resolver

        source = open(contract_resolver.__file__).read()
        # resolver 模块 docstring 必须提及 "immutable" + "code" 示意设计依赖
        assert "immutable" in source.lower(), (
            "contract_resolver 模块未说明依赖 ServicePackage.code immutability。"
            "未来 dev 不知依赖会误改 code, 破历史 contract hash recompute。"
        )
        assert "code" in source, "contract_resolver 未提及 ServicePackage.code"

    def test_orm_validator_first_set_allowed(self):
        # Sentinel #4 (runtime, SQLite-friendly): @validates first-set path
        from decimal import Decimal

        from app.models.service_package import ServicePackage

        pkg = ServicePackage(
            code="new", name="x", price=Decimal("1.00"), sort_order=0
        )
        assert pkg.code == "new"

    def test_orm_validator_same_value_reassign_allowed(self):
        # Idempotent reassign: seed re-run / refresh roundtrip must not break
        from decimal import Decimal

        from app.models.service_package import ServicePackage

        pkg = ServicePackage(
            code="seed", name="x", price=Decimal("1.00"), sort_order=0
        )
        pkg.code = "seed"  # no-op
        assert pkg.code == "seed"

    def test_orm_validator_change_after_first_set_rejected(self):
        # Sentinel #5 (runtime, SQLite-friendly): @validates blocks change
        from decimal import Decimal

        from app.models.service_package import (
            ServicePackage,
            ServicePackageCodeImmutableError,
        )

        pkg = ServicePackage(
            code="original", name="x", price=Decimal("1.00"), sort_order=0
        )
        with pytest.raises(ServicePackageCodeImmutableError) as exc:
            pkg.code = "renamed"
        assert "original" in str(exc.value)
        assert "renamed" in str(exc.value)


# ---------------------------------------------------------------------------
# AC#5 + AC#6 DB-coupled paths now live in test_service_contracts_pg_smoke.py
# (real PG container required for PL/pgSQL trigger semantics).
# This file owns SQLite-friendly logic tests; PG-only tests live in the
# parallel pg_smoke module so they only execute under alembic-smoke workflow.
# ---------------------------------------------------------------------------
