"""Tests for ``app.services.contract_storage`` (S3-DEV-001 / ADR-0046 §3).

# Coverage map (9 AC)

| AC | Test class / case |
|----|-------------------|
| #1 ContractStorage put_contract with put_if_absent | ``TestPutContractBasic`` |
| #2 Azure WORM set_immutability_policy 7y | ``TestImmutabilityPolicy`` |
| #3 blob_path namespace contracts/{year}/{month}/...| ``TestBlobPathNamespace`` |
| #4 put_if_absent reject existing + WORM mock verify | ``TestPutContractIdempotency`` |
| #5 ruff + storage suite | (covered by suite run, not unit assertion) |
| #6 OSError classification + metric | ``TestPutContractOSErrorClassification`` |
| #7 env-driven immutability switch | ``TestImmutabilityPolicy`` |
| #8 blob_path UTC timezone + cross-year | ``TestBlobPathNamespace`` |
| #9 contract_hash input validation | ``TestContractHashValidation`` |

Plus content_type sentinel (刻晴 D2): ``TestContentTypeSentinel``.
"""

from __future__ import annotations

import errno
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from app.services import contract_storage
from app.services.contract_storage import (
    ContractContentTypeError,
    ContractHashInputError,
    ContractStoragePutError,
    ContractStorageRef,
    ViewerRole,
    get_contract_signed_url,
    put_contract,
)
from app.services.storage_backend import (
    AzureBlobStorageBackend,
    LocalStorageBackend,
)

# Realistic 64-char hex (use 'a'*64 for determinism)
VALID_HASH = "a" * 64
ALT_HASH = "b" * 64
ORDER_ID = "ord_01HXX1234567890ABCDEFGHIJK"
TPL_VERSION = "v1.0.0"
PDF_BYTES = b"%PDF-1.4\nfake contract body\n%%EOF"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def local_backend(tmp_path) -> LocalStorageBackend:
    """LocalStorageBackend pointed at an isolated tmp dir.

    ``allow_subdirs=True`` matches the runtime config that
    ``contract_storage._resolve_backend`` would build, so tests exercise the
    real nested-path codepath instead of a flat-only legacy variant.
    """
    return LocalStorageBackend(
        root_dir=tmp_path / "contracts-root",
        allow_subdirs=True,
    )


@pytest.fixture()
def azure_backend() -> AzureBlobStorageBackend:
    """Phase A Azure mock backend (fresh instance per test)."""
    return AzureBlobStorageBackend(
        account_name="test-account",
        container_name="yiluan-cert-test",
    )


@pytest.fixture(autouse=True)
def _reset_immutability_env(monkeypatch):
    """Default: immutability OFF (staging-like). Tests opt-in to prod-like."""
    monkeypatch.setattr(contract_storage.settings, "s3_contract_immutability_enabled", False)


# ---------------------------------------------------------------------------
# AC #1 / #5 — basic put_contract flow
# ---------------------------------------------------------------------------


class TestPutContractBasic:
    def test_local_put_contract_returns_ref(self, local_backend):
        ref = put_contract(
            order_id=ORDER_ID,
            contract_hash=VALID_HASH,
            pdf_bytes=PDF_BYTES,
            template_version=TPL_VERSION,
            backend=local_backend,
        )
        assert isinstance(ref, ContractStorageRef)
        assert ref.contract_hash == VALID_HASH
        assert ref.already_exists is False
        assert ref.immutability_applied is False  # Local backend
        assert ref.blob_path.startswith("contracts/")
        assert ref.blob_path.endswith(f"{ORDER_ID}_{VALID_HASH}.pdf")
        assert ref.stored.scheme == LocalStorageBackend.scheme
        # File actually on disk
        path = local_backend.resolve_path(ref.stored)
        assert path.exists()
        assert path.read_bytes() == PDF_BYTES

    def test_azure_put_contract_returns_ref(self, azure_backend):
        ref = put_contract(
            order_id=ORDER_ID,
            contract_hash=VALID_HASH,
            pdf_bytes=PDF_BYTES,
            template_version=TPL_VERSION,
            backend=azure_backend,
        )
        assert ref.stored.scheme == AzureBlobStorageBackend.scheme
        assert ref.already_exists is False
        # Phase A mock: blob accessible via backend.open
        assert azure_backend.open(ref.stored) == PDF_BYTES


# ---------------------------------------------------------------------------
# AC #4 — idempotency: second put with same key is already_exists
# ---------------------------------------------------------------------------


class TestPutContractIdempotency:
    def test_local_second_put_already_exists(self, local_backend):
        ref1 = put_contract(
            order_id=ORDER_ID,
            contract_hash=VALID_HASH,
            pdf_bytes=PDF_BYTES,
            template_version=TPL_VERSION,
            backend=local_backend,
        )
        assert ref1.already_exists is False

        # Same args: second call must NOT overwrite, must return already_exists
        ref2 = put_contract(
            order_id=ORDER_ID,
            contract_hash=VALID_HASH,
            pdf_bytes=b"DIFFERENT BYTES THAT MUST NOT WIN",
            template_version=TPL_VERSION,
            backend=local_backend,
        )
        assert ref2.already_exists is True
        assert ref2.blob_path == ref1.blob_path
        # On-disk bytes still the original ones
        assert local_backend.resolve_path(ref1.stored).read_bytes() == PDF_BYTES

    def test_azure_second_put_already_exists(self, azure_backend):
        ref1 = put_contract(
            order_id=ORDER_ID,
            contract_hash=VALID_HASH,
            pdf_bytes=PDF_BYTES,
            template_version=TPL_VERSION,
            backend=azure_backend,
        )
        ref2 = put_contract(
            order_id=ORDER_ID,
            contract_hash=VALID_HASH,
            pdf_bytes=b"OTHER BYTES",
            template_version=TPL_VERSION,
            backend=azure_backend,
        )
        assert ref1.already_exists is False
        assert ref2.already_exists is True
        # Mock backend keeps the original bytes
        assert azure_backend.open(ref1.stored) == PDF_BYTES


# ---------------------------------------------------------------------------
# AC #2 / #7 — Azure WORM immutability policy (env-driven, prod vs staging)
# ---------------------------------------------------------------------------


class TestImmutabilityPolicy:
    def test_immutability_off_by_default_no_policy_log(self, azure_backend, monkeypatch):
        # autouse fixture already forces False; assert side effect absent
        ref = put_contract(
            order_id=ORDER_ID,
            contract_hash=VALID_HASH,
            pdf_bytes=PDF_BYTES,
            template_version=TPL_VERSION,
            backend=azure_backend,
        )
        assert ref.immutability_applied is False
        # No _immutability_log attribute means we never even tried
        assert getattr(azure_backend, "_immutability_log", None) is None

    def test_immutability_on_applies_locked_7y_policy(self, azure_backend, monkeypatch):
        monkeypatch.setattr(
            contract_storage.settings,
            "s3_contract_immutability_enabled",
            True,
        )
        ref = put_contract(
            order_id=ORDER_ID,
            contract_hash=VALID_HASH,
            pdf_bytes=PDF_BYTES,
            template_version=TPL_VERSION,
            backend=azure_backend,
        )
        assert ref.immutability_applied is True
        log = azure_backend._immutability_log  # type: ignore[attr-defined]
        assert len(log) == 1
        entry = log[0]
        assert entry["blob_path"] == ref.blob_path
        assert entry["period_days"] == 365 * 7
        assert entry["policy_mode"] == "Locked"

    def test_immutability_on_local_backend_skipped(self, local_backend, monkeypatch):
        # Even with prod-style env enabled, Local backend must NOT pretend to
        # apply Azure-specific immutability (no-op + immutability_applied=False)
        monkeypatch.setattr(
            contract_storage.settings,
            "s3_contract_immutability_enabled",
            True,
        )
        ref = put_contract(
            order_id=ORDER_ID,
            contract_hash=VALID_HASH,
            pdf_bytes=PDF_BYTES,
            template_version=TPL_VERSION,
            backend=local_backend,
        )
        assert ref.immutability_applied is False


# ---------------------------------------------------------------------------
# AC #3 / #8 — blob_path namespace + UTC timezone + cross-year
# ---------------------------------------------------------------------------


class TestBlobPathNamespace:
    def test_blob_path_uses_contracts_prefix_and_year_month(self, local_backend):
        # Freeze UTC clock to a known instant inside the put call
        fixed_now = datetime(2026, 6, 15, 12, 30, 0, tzinfo=timezone.utc)
        with patch.object(contract_storage, "datetime") as dt_mock:
            dt_mock.now.return_value = fixed_now
            ref = put_contract(
                order_id=ORDER_ID,
                contract_hash=VALID_HASH,
                pdf_bytes=PDF_BYTES,
                template_version=TPL_VERSION,
                backend=local_backend,
            )
        assert ref.blob_path == f"contracts/2026/06/{ORDER_ID}_{VALID_HASH}.pdf"

    def test_blob_path_zero_pads_month(self, local_backend):
        fixed_now = datetime(2026, 1, 5, 0, 0, 0, tzinfo=timezone.utc)
        with patch.object(contract_storage, "datetime") as dt_mock:
            dt_mock.now.return_value = fixed_now
            ref = put_contract(
                order_id=ORDER_ID,
                contract_hash=VALID_HASH,
                pdf_bytes=PDF_BYTES,
                template_version=TPL_VERSION,
                backend=local_backend,
            )
        assert "/2026/01/" in ref.blob_path

    def test_blob_path_uses_utc_not_local_across_year_boundary(self, local_backend):
        # Edge: 23:59 UTC Dec 31 vs 00:00 UTC Jan 1 — partitions differ.
        nye = datetime(2026, 12, 31, 23, 59, 0, tzinfo=timezone.utc)
        nyd = datetime(2027, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        with patch.object(contract_storage, "datetime") as dt_mock:
            dt_mock.now.return_value = nye
            ref_dec = put_contract(
                order_id=ORDER_ID,
                contract_hash=VALID_HASH,
                pdf_bytes=PDF_BYTES,
                template_version=TPL_VERSION,
                backend=local_backend,
            )
        with patch.object(contract_storage, "datetime") as dt_mock:
            dt_mock.now.return_value = nyd
            ref_jan = put_contract(
                order_id="ord_01HXX1234567890ABCDEFGHIJL",  # diff order
                contract_hash=ALT_HASH,
                pdf_bytes=PDF_BYTES,
                template_version=TPL_VERSION,
                backend=local_backend,
            )
        assert "/2026/12/" in ref_dec.blob_path
        assert "/2027/01/" in ref_jan.blob_path

    def test_blob_path_uses_utc_timezone_aware_call(self, local_backend, monkeypatch):
        # Confirm we pass timezone.utc explicitly (not naive now())
        captured = {}

        class _DT:
            @staticmethod
            def now(tz=None):
                captured["tz"] = tz
                return datetime(2026, 6, 15, tzinfo=timezone.utc)

        monkeypatch.setattr(contract_storage, "datetime", _DT)
        put_contract(
            order_id=ORDER_ID,
            contract_hash=VALID_HASH,
            pdf_bytes=PDF_BYTES,
            template_version=TPL_VERSION,
            backend=local_backend,
        )
        assert captured["tz"] is timezone.utc


# ---------------------------------------------------------------------------
# AC #6 — OSError classification + prometheus counter
# ---------------------------------------------------------------------------


class _FaultyBackend(LocalStorageBackend):
    """Backend that raises a configurable OSError on put_if_absent."""

    def __init__(self, root_dir, raise_errno):
        super().__init__(root_dir=root_dir, allow_subdirs=True)
        self._raise_errno = raise_errno

    def put_if_absent(self, key, content, *, content_type, metadata=None):
        err = OSError("injected")
        err.errno = self._raise_errno
        raise err


class TestPutContractOSErrorClassification:
    @pytest.mark.parametrize(
        "raised_errno,expected_label",
        [
            (errno.EACCES, "EACCES"),
            (errno.EROFS, "EROFS"),
            (errno.ENOSPC, "ENOSPC"),
            (errno.EIO, "OTHER"),
        ],
    )
    def test_oserror_subtype_mapped_to_label(self, tmp_path, raised_errno, expected_label):
        faulty = _FaultyBackend(tmp_path, raise_errno=raised_errno)
        # Snapshot counter value before call
        counter = contract_storage.contract_storage_put_error_total.labels(errno=expected_label)
        before = counter._value.get()
        with pytest.raises(ContractStoragePutError) as exc_info:
            put_contract(
                order_id=ORDER_ID,
                contract_hash=VALID_HASH,
                pdf_bytes=PDF_BYTES,
                template_version=TPL_VERSION,
                backend=faulty,
            )
        assert exc_info.value.errno_label == expected_label
        # Original OSError preserved as __cause__
        assert isinstance(exc_info.value.__cause__, OSError)
        # Counter advanced by exactly 1
        after = counter._value.get()
        assert after - before == 1


# ---------------------------------------------------------------------------
# AC #9 — contract_hash input validation
# ---------------------------------------------------------------------------


class TestContractHashValidation:
    @pytest.mark.parametrize(
        "bad_hash",
        [
            None,
            "",
            "a" * 63,  # too short
            "a" * 65,  # too long
            "g" * 64,  # non-hex char
            "a" * 32 + " " * 32,  # whitespace
            "a" * 32 + "../etc",  # path traversal attempt
        ],
    )
    def test_invalid_hash_rejected_before_io(self, local_backend, bad_hash):
        with pytest.raises(ContractHashInputError):
            put_contract(
                order_id=ORDER_ID,
                contract_hash=bad_hash,
                pdf_bytes=PDF_BYTES,
                template_version=TPL_VERSION,
                backend=local_backend,
            )
        # No file ever written
        assert list(local_backend.root.rglob("*")) == []

    def test_uppercase_hex_accepted(self, local_backend):
        # SHA-256 hex from hashlib is lowercase, but accept mixed for safety
        ref = put_contract(
            order_id=ORDER_ID,
            contract_hash="A" * 64,
            pdf_bytes=PDF_BYTES,
            template_version=TPL_VERSION,
            backend=local_backend,
        )
        assert ref.contract_hash == "A" * 64


# ---------------------------------------------------------------------------
# Content-type sentinel (刻晴 D2) — Currently hardcoded inside put_contract;
# this test guards the constant + the helper independently so future variants
# (signed-pdf / pdf-a) don't silently widen the allowlist.
# ---------------------------------------------------------------------------


class TestContentTypeSentinel:
    def test_allowed_set_contains_only_pdf(self):
        # Sentinel: drift here means an attacker-controlled MIME could land in
        # WORM storage. Anyone widening this set must update both ADR + tests.
        assert contract_storage._ALLOWED_CONTENT_TYPES == frozenset({"application/pdf"})

    def test_assert_content_type_rejects_svg(self):
        with pytest.raises(ContractContentTypeError):
            contract_storage._assert_content_type_allowed("image/svg+xml")

    def test_assert_content_type_rejects_html(self):
        with pytest.raises(ContractContentTypeError):
            contract_storage._assert_content_type_allowed("text/html")

    def test_assert_content_type_accepts_pdf(self):
        # No raise = pass
        contract_storage._assert_content_type_allowed("application/pdf")


# ---------------------------------------------------------------------------
# ViewerRole signed URL TTL
# ---------------------------------------------------------------------------


class TestSignedUrlTTL:
    def test_user_role_ttl_15min(self, local_backend):
        ref = put_contract(
            order_id=ORDER_ID,
            contract_hash=VALID_HASH,
            pdf_bytes=PDF_BYTES,
            template_version=TPL_VERSION,
            backend=local_backend,
        )
        signed = get_contract_signed_url(
            ref.blob_path,
            ViewerRole.USER,
            backend=local_backend,
            now=1_000_000,
        )
        assert signed.expires_at == 1_000_000 + 15 * 60

    def test_companion_role_ttl_30min(self, local_backend):
        ref = put_contract(
            order_id=ORDER_ID,
            contract_hash=VALID_HASH,
            pdf_bytes=PDF_BYTES,
            template_version=TPL_VERSION,
            backend=local_backend,
        )
        signed = get_contract_signed_url(
            ref.blob_path,
            ViewerRole.COMPANION,
            backend=local_backend,
            now=1_000_000,
        )
        assert signed.expires_at == 1_000_000 + 30 * 60

    def test_admin_role_ttl_5min(self, local_backend):
        ref = put_contract(
            order_id=ORDER_ID,
            contract_hash=VALID_HASH,
            pdf_bytes=PDF_BYTES,
            template_version=TPL_VERSION,
            backend=local_backend,
        )
        signed = get_contract_signed_url(
            ref.blob_path,
            ViewerRole.ADMIN,
            backend=local_backend,
            now=1_000_000,
        )
        assert signed.expires_at == 1_000_000 + 5 * 60
