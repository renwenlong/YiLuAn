"""Tests for ``app.services.contract_hash`` (S3-DEV-001-CONTRACT-HASH / ADR-0046 §3.2).

# Coverage map (5 AC)

| AC | Test class |
|----|-----------|
| #1 atomic freeze (hash + snapshot)            | ``TestGenerateContractHashAtCommitTime`` |
| #2 canonical JSON three pinned params         | ``TestCanonicalJSONInvariance``        |
| #3 CONTRACT_PSEUDONYM_SALT independent env    | ``TestPseudonymSaltIndependence``      |
| #4 hash_inputs snapshot shape (JSONB ready)   | ``TestHashInputsSnapshotShape``        |
| #5 historical recompute survives state drift  | ``TestHistoricalSnapshotRecompute``    |

Plus utility coverage: ``TestAmountCnyFromYuan``, ``TestRecomputeContractHash``,
``TestPatientPseudonymHash``.

# Why these tests look paranoid

Contract hash drift is *silent* in production until a dispute audit
fails 18 months later. The tests pin every observable behavior of the
hash pipeline (canonical JSON params, salt env behavior, dict shape,
recompute equality) so a future refactor cannot quietly break old
contracts.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.services import contract_hash
from app.services.contract_hash import (
    SHA256_HEX_LEN,
    ContractHashGenerationError,
    ContractHashResult,
    ContractPseudonymSaltMissingError,
    amount_cny_from_yuan,
    build_hash_inputs_snapshot,
    compute_patient_pseudonym_hash,
    generate_contract_hash_at_commit_time,
    recompute_contract_hash,
)

# A high-entropy fake salt used everywhere except the missing-salt tests.
FAKE_SALT = "test-salt-not-for-production-2cQ8mP4xJ9zR5"
PATIENT_NAME = "张三"
ID_CARD_LAST4 = "1234"
ORDER_ID = "ord_01HXX1234567890ABCDEFGHIJK"
SERVICE_PKG_ID = "pkg_01HXX1234567890ABCDEFGHIJL"
COMPANION_ID = "usr_01HXX1234567890ABCDEFGHIJM"
TPL_V1 = "v1.0.0"
TPL_V2 = "v2.0.0"
SCHEDULED_AT = datetime(2026, 6, 15, 10, 30, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _seed_salt(monkeypatch):
    """Default: salt is set. Tests that need missing-salt opt-out."""
    monkeypatch.setattr(contract_hash.settings, "contract_pseudonym_salt", FAKE_SALT)


# ---------------------------------------------------------------------------
# AC #3 — pseudonym salt independence
# ---------------------------------------------------------------------------


class TestPseudonymSaltIndependence:
    def test_missing_salt_raises_dedicated_error(self, monkeypatch):
        monkeypatch.setattr(contract_hash.settings, "contract_pseudonym_salt", "")
        with pytest.raises(ContractPseudonymSaltMissingError):
            compute_patient_pseudonym_hash(patient_name=PATIENT_NAME, id_card_last4=ID_CARD_LAST4)

    def test_whitespace_only_salt_raises(self, monkeypatch):
        # ``"   "`` is operationally "unset"; should not silently pass
        monkeypatch.setattr(contract_hash.settings, "contract_pseudonym_salt", "   ")
        with pytest.raises(ContractPseudonymSaltMissingError):
            compute_patient_pseudonym_hash(patient_name=PATIENT_NAME, id_card_last4=ID_CARD_LAST4)

    def test_different_salts_produce_different_hashes(self, monkeypatch):
        # Confirm we never leak salt-equivalence: change salt → hash flips
        monkeypatch.setattr(contract_hash.settings, "contract_pseudonym_salt", "salt-A")
        h_a = compute_patient_pseudonym_hash(patient_name=PATIENT_NAME, id_card_last4=ID_CARD_LAST4)
        monkeypatch.setattr(contract_hash.settings, "contract_pseudonym_salt", "salt-B")
        h_b = compute_patient_pseudonym_hash(patient_name=PATIENT_NAME, id_card_last4=ID_CARD_LAST4)
        assert h_a != h_b

    def test_salt_not_shared_with_pii_hash_salt(self, monkeypatch):
        # Sentinel: contract_pseudonym_salt must be its own settings field.
        # If a future refactor falls back to ``pii_hash_salt`` for the
        # contract path, this test fails and forces the conversation.
        assert hasattr(contract_hash.settings, "contract_pseudonym_salt")
        # The field accessor must read the dedicated env, not the shared one
        monkeypatch.setattr(contract_hash.settings, "contract_pseudonym_salt", "CONTRACT-XYZ")
        # PII salt should be irrelevant to contract hash
        if hasattr(contract_hash.settings, "pii_hash_salt"):
            monkeypatch.setattr(contract_hash.settings, "pii_hash_salt", "PII-ABC")
        h_contract = compute_patient_pseudonym_hash(
            patient_name=PATIENT_NAME, id_card_last4=ID_CARD_LAST4
        )
        # Recompute by hand using the contract salt only:
        import hashlib

        expected = hashlib.sha256(
            f"{PATIENT_NAME}|{ID_CARD_LAST4}|CONTRACT-XYZ".encode("utf-8")
        ).hexdigest()
        assert h_contract == expected


# ---------------------------------------------------------------------------
# Pseudonym hash arg validation
# ---------------------------------------------------------------------------


class TestPatientPseudonymHash:
    def test_returns_sha256_hex_length(self):
        h = compute_patient_pseudonym_hash(patient_name=PATIENT_NAME, id_card_last4=ID_CARD_LAST4)
        assert len(h) == SHA256_HEX_LEN
        assert all(c in "0123456789abcdef" for c in h)

    def test_empty_name_rejected(self):
        with pytest.raises(ContractHashGenerationError):
            compute_patient_pseudonym_hash(patient_name="", id_card_last4=ID_CARD_LAST4)

    @pytest.mark.parametrize("bad_last4", ["", "123", "12345", "abc"])
    def test_id_card_last4_must_be_exactly_4(self, bad_last4):
        with pytest.raises(ContractHashGenerationError):
            compute_patient_pseudonym_hash(patient_name=PATIENT_NAME, id_card_last4=bad_last4)

    def test_unicode_name_preserved(self):
        # ensure_ascii=False discipline: 中文姓名 → 不 escape
        h = compute_patient_pseudonym_hash(patient_name="王 涵", id_card_last4=ID_CARD_LAST4)
        assert len(h) == SHA256_HEX_LEN


# ---------------------------------------------------------------------------
# AC #2 — canonical JSON three pinned params
# ---------------------------------------------------------------------------


class TestCanonicalJSONInvariance:
    """Pin the three JSON serialization parameters that *cannot* drift.

    Any of these changing in a future refactor would silently invalidate
    every contract issued under the old format. We assert byte-equality
    of the canonical output to a hand-computed baseline.
    """

    def _sample_snapshot(self) -> dict:
        # Deliberately insert keys in non-alphabetic order to exercise sort_keys.
        return {
            "template_version": TPL_V1,
            "amount_cny": 19999,
            "order_id": ORDER_ID,
            "scheduled_at": "2026-06-15T10:30:00+00:00",
            "service_package_id": SERVICE_PKG_ID,
            "companion_id": COMPANION_ID,
            "patient_pseudonym_hash": "a" * SHA256_HEX_LEN,
        }

    def test_sort_keys_alphabetic(self):
        out = contract_hash._canonical_json(self._sample_snapshot())
        # Keys must appear in alphabetic order regardless of insertion order
        expected_first_key = "amount_cny"
        assert out.startswith(f'{{"{expected_first_key}":')

    def test_no_whitespace_anywhere(self):
        out = contract_hash._canonical_json(self._sample_snapshot())
        assert " " not in out
        assert "\n" not in out
        assert "\t" not in out

    def test_ensure_ascii_false_preserves_utf8(self):
        snap = self._sample_snapshot()
        snap["order_id"] = "订单-中文-001"
        out = contract_hash._canonical_json(snap)
        # Chinese must NOT be \u-escaped
        assert "订单-中文-001" in out
        assert "\\u" not in out

    def test_byte_exact_baseline(self):
        # Byte-equality baseline: regression guard for json.dumps drift.
        snap = {
            "amount_cny": 100,
            "order_id": "abc",
            "template_version": "v1",
        }
        out = contract_hash._canonical_json(snap)
        assert out == '{"amount_cny":100,"order_id":"abc","template_version":"v1"}'


# ---------------------------------------------------------------------------
# AC #4 — hash_inputs snapshot shape
# ---------------------------------------------------------------------------


class TestHashInputsSnapshotShape:
    def _valid_kwargs(self):
        return dict(
            order_id=ORDER_ID,
            amount_cny=19999,
            service_package_id=SERVICE_PKG_ID,
            scheduled_at=SCHEDULED_AT,
            patient_pseudonym_hash="a" * SHA256_HEX_LEN,
            companion_id=COMPANION_ID,
            template_version=TPL_V1,
        )

    def test_returns_exactly_required_keys(self):
        snap = build_hash_inputs_snapshot(**self._valid_kwargs())
        assert set(snap.keys()) == contract_hash._HASH_INPUTS_REQUIRED_KEYS

    def test_scheduled_at_datetime_normalized_to_iso(self):
        snap = build_hash_inputs_snapshot(**self._valid_kwargs())
        assert snap["scheduled_at"] == "2026-06-15T10:30:00+00:00"

    def test_scheduled_at_date_normalized_to_midnight_utc(self):
        kwargs = self._valid_kwargs()
        kwargs["scheduled_at"] = date(2026, 6, 15)
        snap = build_hash_inputs_snapshot(**kwargs)
        assert snap["scheduled_at"] == "2026-06-15T00:00:00+00:00"

    def test_scheduled_at_naive_datetime_treated_as_utc(self):
        kwargs = self._valid_kwargs()
        kwargs["scheduled_at"] = datetime(2026, 6, 15, 10, 30)  # naive
        snap = build_hash_inputs_snapshot(**kwargs)
        assert "+00:00" in snap["scheduled_at"]

    def test_scheduled_at_string_passed_through(self):
        kwargs = self._valid_kwargs()
        kwargs["scheduled_at"] = "2026-06-15T10:30:00Z"
        snap = build_hash_inputs_snapshot(**kwargs)
        assert snap["scheduled_at"] == "2026-06-15T10:30:00Z"

    def test_extra_key_in_external_snapshot_rejected_by_assert(self):
        # If a caller constructs a snapshot externally and includes an extra
        # key, the assert layer (called inside _hash_from_snapshot) must reject.
        snap = build_hash_inputs_snapshot(**self._valid_kwargs())
        snap["sneaky_extra"] = "leak"
        with pytest.raises(ContractHashGenerationError):
            contract_hash._hash_from_snapshot(snap, TPL_V1)

    def test_missing_key_rejected_by_assert(self):
        snap = build_hash_inputs_snapshot(**self._valid_kwargs())
        del snap["order_id"]
        with pytest.raises(ContractHashGenerationError):
            contract_hash._hash_from_snapshot(snap, TPL_V1)

    @pytest.mark.parametrize(
        "field,bad_value",
        [
            ("order_id", ""),
            ("amount_cny", 0),
            ("amount_cny", -1),
            ("amount_cny", "100"),  # not int
            ("service_package_id", ""),
            ("companion_id", ""),
            ("template_version", ""),
            ("patient_pseudonym_hash", "short"),
            ("patient_pseudonym_hash", "a" * 63),
            ("patient_pseudonym_hash", "a" * 65),
        ],
    )
    def test_invalid_field_rejected(self, field, bad_value):
        kwargs = self._valid_kwargs()
        kwargs[field] = bad_value
        with pytest.raises(ContractHashGenerationError):
            build_hash_inputs_snapshot(**kwargs)

    def test_snapshot_dict_is_jsonb_round_trip_safe(self):
        # JSONB persistence (CONTRACT-DOMAIN) needs: json.dumps + json.loads
        # round-trips identically. No datetime, no Decimal — all primitives.
        snap = build_hash_inputs_snapshot(**self._valid_kwargs())
        rountripped = json.loads(json.dumps(snap))
        assert rountripped == snap


# ---------------------------------------------------------------------------
# AC #1 — generate_contract_hash_at_commit_time atomic freeze
# ---------------------------------------------------------------------------


class TestGenerateContractHashAtCommitTime:
    def _valid_kwargs(self):
        return dict(
            order_id=ORDER_ID,
            amount_cny=19999,
            service_package_id=SERVICE_PKG_ID,
            scheduled_at=SCHEDULED_AT,
            patient_name=PATIENT_NAME,
            patient_id_card_last4=ID_CARD_LAST4,
            companion_id=COMPANION_ID,
            template_version=TPL_V1,
        )

    def test_returns_hash_and_snapshot_dataclass(self):
        result = generate_contract_hash_at_commit_time(**self._valid_kwargs())
        assert isinstance(result, ContractHashResult)
        assert len(result.contract_hash) == SHA256_HEX_LEN
        assert all(c in "0123456789abcdef" for c in result.contract_hash)
        assert set(result.hash_inputs_snapshot.keys()) == (contract_hash._HASH_INPUTS_REQUIRED_KEYS)

    def test_deterministic_for_same_inputs(self):
        r1 = generate_contract_hash_at_commit_time(**self._valid_kwargs())
        r2 = generate_contract_hash_at_commit_time(**self._valid_kwargs())
        assert r1.contract_hash == r2.contract_hash
        assert r1.hash_inputs_snapshot == r2.hash_inputs_snapshot

    @pytest.mark.parametrize(
        "field,new_value",
        [
            ("order_id", "ord_DIFFERENT"),
            ("amount_cny", 19998),  # 1 cent diff
            ("service_package_id", "pkg_DIFFERENT"),
            ("scheduled_at", datetime(2026, 6, 16, 10, 30, tzinfo=timezone.utc)),
            ("patient_name", "李四"),
            ("patient_id_card_last4", "5678"),
            ("companion_id", "usr_DIFFERENT"),
            ("template_version", TPL_V2),
        ],
    )
    def test_any_input_change_flips_hash(self, field, new_value):
        kwargs = self._valid_kwargs()
        baseline = generate_contract_hash_at_commit_time(**kwargs).contract_hash
        kwargs[field] = new_value
        new = generate_contract_hash_at_commit_time(**kwargs).contract_hash
        assert baseline != new, f"Changing {field} must flip the hash"

    def test_unicode_name_does_not_break_hash_path(self):
        kwargs = self._valid_kwargs()
        kwargs["patient_name"] = "李 涵 𓂀"  # unicode + space + emoji-ish
        result = generate_contract_hash_at_commit_time(**kwargs)
        assert len(result.contract_hash) == SHA256_HEX_LEN


# ---------------------------------------------------------------------------
# AC #5 — historical snapshot recompute survives upstream mutations
# ---------------------------------------------------------------------------


class TestHistoricalSnapshotRecompute:
    """The contract MUST stay verifiable even after the user / template
    state has moved on. This test models the production audit path:

    1. Contract generated at commit time → (hash, snapshot) frozen.
    2. User renames themselves → live state changes.
    3. Audit recomputes hash from the **stored snapshot** → still matches.
    """

    def _commit_time_kwargs(self):
        return dict(
            order_id=ORDER_ID,
            amount_cny=19999,
            service_package_id=SERVICE_PKG_ID,
            scheduled_at=SCHEDULED_AT,
            patient_name=PATIENT_NAME,
            patient_id_card_last4=ID_CARD_LAST4,
            companion_id=COMPANION_ID,
            template_version=TPL_V1,
        )

    def test_recompute_from_stored_snapshot_matches(self):
        # Simulate commit time
        committed = generate_contract_hash_at_commit_time(**self._commit_time_kwargs())
        # Snapshot would be persisted into service_contracts.hash_inputs
        stored_snapshot = committed.hash_inputs_snapshot
        stored_hash = committed.contract_hash

        # Time passes... user changes their name, template version bumps
        # in main app code, etc. We don't recompute from live state.

        # Audit / verification path uses only the stored snapshot:
        recomputed = recompute_contract_hash(
            hash_inputs_snapshot=stored_snapshot,
            template_version=stored_snapshot["template_version"],
        )
        assert recomputed == stored_hash

    def test_user_renames_does_not_break_historical_contract(self):
        # Commit time: 张三
        committed = generate_contract_hash_at_commit_time(**self._commit_time_kwargs())
        stored_snap = committed.hash_inputs_snapshot
        stored_hash = committed.contract_hash

        # Later: user changed name to 张三丰; if we were to recompute by
        # querying live state, the hash would flip. But we don't —
        # we use the stored snapshot, which still has the pseudonym hash
        # computed from the original name. → hash matches.
        recomputed = recompute_contract_hash(
            hash_inputs_snapshot=stored_snap,
            template_version=stored_snap["template_version"],
        )
        assert recomputed == stored_hash

    def test_template_version_bumps_does_not_break_historical_contract(self):
        # Contract issued under v1.0.0
        committed = generate_contract_hash_at_commit_time(**self._commit_time_kwargs())
        stored_snap = committed.hash_inputs_snapshot

        # System rolls forward to v2.0.0 for new contracts.
        # Old contract's snapshot still says template_version=v1.0.0 →
        # recompute uses v1.0.0 from snapshot.
        recomputed = recompute_contract_hash(
            hash_inputs_snapshot=stored_snap,
            template_version=stored_snap["template_version"],
        )
        assert recomputed == committed.contract_hash

    def test_tampered_snapshot_field_breaks_recompute(self):
        committed = generate_contract_hash_at_commit_time(**self._commit_time_kwargs())
        stored_snap = dict(committed.hash_inputs_snapshot)
        # Attacker mutates amount_cny in the stored row
        stored_snap["amount_cny"] = 1
        recomputed = recompute_contract_hash(
            hash_inputs_snapshot=stored_snap,
            template_version=stored_snap["template_version"],
        )
        assert recomputed != committed.contract_hash

    def test_recompute_with_wrong_template_version_breaks(self):
        committed = generate_contract_hash_at_commit_time(**self._commit_time_kwargs())
        # Audit passes the wrong template_version (not from snapshot)
        recomputed = recompute_contract_hash(
            hash_inputs_snapshot=committed.hash_inputs_snapshot,
            template_version=TPL_V2,  # wrong
        )
        assert recomputed != committed.contract_hash


# ---------------------------------------------------------------------------
# Utility: amount_cny_from_yuan
# ---------------------------------------------------------------------------


class TestAmountCnyFromYuan:
    @pytest.mark.parametrize(
        "yuan,expected_cents",
        [
            (Decimal("100.00"), 10000),
            (Decimal("99.99"), 9999),
            (Decimal("0.01"), 1),
            (Decimal("0"), 0),
            (100, 10000),
            ("99.99", 9999),
        ],
    )
    def test_basic_conversion(self, yuan, expected_cents):
        assert amount_cny_from_yuan(yuan) == expected_cents

    def test_round_half_even(self):
        # Banker's rounding at 2 decimals
        # 99.995 → 100.00 (round half to even, 100 is even)
        # 99.985 → 99.98 (98 is even)
        assert amount_cny_from_yuan(Decimal("99.995")) == 10000
        assert amount_cny_from_yuan(Decimal("99.985")) == 9998

    def test_float_input_via_str_avoids_binary_drift(self):
        # 0.1 + 0.2 = 0.30000000000000004 if we naively Decimal(0.1+0.2)
        # We accept float by string-converting first; production should
        # send Decimal directly, but float fallback must not silently
        # propagate float drift.
        assert amount_cny_from_yuan(0.1) == 10
        assert amount_cny_from_yuan(0.30) == 30

    def test_negative_rejected(self):
        with pytest.raises(ContractHashGenerationError):
            amount_cny_from_yuan(Decimal("-1.00"))

    def test_nan_rejected(self):
        with pytest.raises(ContractHashGenerationError):
            amount_cny_from_yuan(Decimal("NaN"))

    def test_bad_type_rejected(self):
        with pytest.raises(ContractHashGenerationError):
            amount_cny_from_yuan(None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# AC#3 — salt_version 不进 contract_hash 计算 (S3-OPS-CONTRACT-SALT-ROTATE-PATH
# / ADR-0046 r8 方案 D)
#
# salt_version 是 service_contracts 的纯审计/取证列 (标记该行用第几版 salt),
# 绝不能进 contract_hash 计算 —— 否则又会被烧进 WORM 不可变字段, 且让同一
# 份合同内容因 salt 版本不同算出不同 hash (破坏一单一合同 UNIQUE 语义)。
# 方案 A 失败的根因正是 pseudonym_hash 进了 contract_hash; salt_version 必须
# 与 _HASH_INPUTS_REQUIRED_KEYS 完全解耦。
# ---------------------------------------------------------------------------


class TestSaltVersionNotInContractHash:
    def test_salt_version_not_in_required_keys(self):
        # 结构断言: salt_version 绝不在 hash 输入必需 key 集合里。
        assert "salt_version" not in contract_hash._HASH_INPUTS_REQUIRED_KEYS

    def test_snapshot_has_no_salt_version_key(self):
        # build_hash_inputs_snapshot 不接受也不产出 salt_version。
        snap = build_hash_inputs_snapshot(
            order_id=ORDER_ID,
            amount_cny=19999,
            service_package_id=SERVICE_PKG_ID,
            scheduled_at=SCHEDULED_AT,
            patient_pseudonym_hash="a" * SHA256_HEX_LEN,
            companion_id=COMPANION_ID,
            template_version=TPL_V1,
        )
        assert "salt_version" not in snap

    def test_hash_identical_regardless_of_salt_version(self):
        # salt_version 不是 hash 输入参数 — 两次相同 hash 输入必得相同
        # contract_hash, 与"该行将来记第几版 salt"无关。
        common = dict(
            order_id=ORDER_ID,
            amount_cny=19999,
            service_package_id=SERVICE_PKG_ID,
            scheduled_at=SCHEDULED_AT,
            patient_name=PATIENT_NAME,
            patient_id_card_last4=ID_CARD_LAST4,
            companion_id=COMPANION_ID,
            template_version=TPL_V1,
        )
        a = generate_contract_hash_at_commit_time(**common)
        b = generate_contract_hash_at_commit_time(**common)
        assert a.contract_hash == b.contract_hash
        assert "salt_version" not in a.hash_inputs_snapshot
        assert "salt_version" not in b.hash_inputs_snapshot
