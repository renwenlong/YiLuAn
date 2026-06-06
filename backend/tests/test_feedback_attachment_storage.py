"""Tests for ``app.services.feedback_attachment_storage`` (S3-DEV-004-FEEDBACK-STORAGE).

# Coverage map (4 AC + extras)

| AC | Test class |
|----|-----------|
| #1 ADR-0049 merged to main          | doc-level, implicit |
| #2 service module + put_if_absent   | ``TestPutAttachment``, ``TestSignedUrl`` |
| #3 namespace isolation ``feedback/`` | ``TestBlobPathNamespaceIsolation`` |
| #4 upload / sign / expire / traversal | ``TestUploadValidation``, ``TestTraversalDefense`` |

Plus:
- ``TestContentTypeSentinel`` — SVG XSS / HTML / JS / unknown mime
- ``TestSizeLimit`` — 10 MiB cap
- ``TestHashDedup`` — identical bytes → idempotent already_exists
- ``TestOSErrorClassification`` — EACCES / EROFS / ENOSPC / OTHER routing
- ``TestFeedbackIdInputDefense`` — restrictive charset cap
"""

from __future__ import annotations

import errno
import hashlib
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from app.services import feedback_attachment_storage as fas
from app.services.feedback_attachment_storage import (
    FeedbackAttachmentContentTypeError,
    FeedbackAttachmentPutError,
    FeedbackAttachmentRef,
    FeedbackAttachmentSizeError,
    FeedbackViewerRole,
    get_attachment_signed_url,
    put_attachment,
)
from app.services.storage_backend import (
    AzureBlobStorageBackend,
    LocalStorageBackend,
)

FEEDBACK_ID = "fb_01HXX1234567890ABCDEFGHIJK"
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"x" * 1000  # JPEG magic + padding
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"y" * 500  # PNG magic + padding
PDF_BYTES = b"%PDF-1.4\n" + b"z" * 800 + b"\n%%EOF"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def local_backend(tmp_path) -> LocalStorageBackend:
    """LocalStorageBackend with allow_subdirs=True at isolated tmp dir."""
    return LocalStorageBackend(
        root_dir=tmp_path / "feedback-root",
        allow_subdirs=True,
    )


@pytest.fixture()
def azure_backend() -> AzureBlobStorageBackend:
    return AzureBlobStorageBackend(
        account_name="test-account",
        container_name="yiluan-cert-test",
    )


# ---------------------------------------------------------------------------
# AC#2 — put_attachment basic flow
# ---------------------------------------------------------------------------


class TestPutAttachment:
    def test_local_put_returns_ref(self, local_backend):
        ref = put_attachment(
            feedback_id=FEEDBACK_ID,
            content=JPEG_BYTES,
            content_type="image/jpeg",
            backend=local_backend,
        )
        assert isinstance(ref, FeedbackAttachmentRef)
        assert ref.byte_size == len(JPEG_BYTES)
        assert ref.content_type == "image/jpeg"
        assert ref.already_exists is False
        assert ref.blob_path.startswith("feedback/")
        assert ref.blob_path.endswith(".jpg")
        assert FEEDBACK_ID in ref.blob_path
        # File on disk
        on_disk = local_backend.resolve_path(ref.stored)
        assert on_disk.exists()
        assert on_disk.read_bytes() == JPEG_BYTES

    def test_azure_put_returns_ref(self, azure_backend):
        ref = put_attachment(
            feedback_id=FEEDBACK_ID,
            content=PDF_BYTES,
            content_type="application/pdf",
            backend=azure_backend,
        )
        assert ref.already_exists is False
        assert azure_backend.open(ref.stored) == PDF_BYTES

    def test_content_hash_is_sha256_full(self, local_backend):
        ref = put_attachment(
            feedback_id=FEEDBACK_ID,
            content=JPEG_BYTES,
            content_type="image/jpeg",
            backend=local_backend,
        )
        assert ref.content_hash == hashlib.sha256(JPEG_BYTES).hexdigest()
        assert len(ref.content_hash) == 64

    @pytest.mark.parametrize(
        "content_type,content,expected_ext",
        [
            ("image/jpeg", JPEG_BYTES, ".jpg"),
            ("image/png", PNG_BYTES, ".png"),
            ("image/webp", b"RIFFwebpdata", ".webp"),
            ("application/pdf", PDF_BYTES, ".pdf"),
        ],
    )
    def test_blob_path_canonical_ext_from_content_type(
        self, local_backend, content_type, content, expected_ext
    ):
        # Defense: ext comes from content_type allowlist mapping, NOT
        # from user filename (which is never passed in this signature).
        ref = put_attachment(
            feedback_id=FEEDBACK_ID,
            content=content,
            content_type=content_type,
            backend=local_backend,
        )
        assert ref.blob_path.endswith(expected_ext)


# ---------------------------------------------------------------------------
# AC#3 — namespace isolation
# ---------------------------------------------------------------------------


class TestBlobPathNamespaceIsolation:
    def test_blob_path_starts_with_feedback_prefix(self, local_backend):
        ref = put_attachment(
            feedback_id=FEEDBACK_ID,
            content=JPEG_BYTES,
            content_type="image/jpeg",
            backend=local_backend,
        )
        # ADR-0049 §5.1: namespace 隔离 cert/ contracts/ feedback/
        assert ref.blob_path.startswith("feedback/")
        assert "/contracts/" not in ref.blob_path
        assert "/cert/" not in ref.blob_path

    def test_blob_path_year_month_zero_padded_utc(self, local_backend):
        fixed = datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc)
        with patch.object(fas, "datetime") as dt_mock:
            dt_mock.now.return_value = fixed
            ref = put_attachment(
                feedback_id=FEEDBACK_ID,
                content=JPEG_BYTES,
                content_type="image/jpeg",
                backend=local_backend,
            )
        assert "/2026/01/" in ref.blob_path

    def test_blob_path_includes_content_hash_first_16_chars(self, local_backend):
        ref = put_attachment(
            feedback_id=FEEDBACK_ID,
            content=JPEG_BYTES,
            content_type="image/jpeg",
            backend=local_backend,
        )
        assert ref.content_hash[:16] in ref.blob_path

    def test_blob_path_uses_utc_not_local_timezone(self, local_backend):
        # Regression: must use UTC, not naive now()
        captured = {}

        class _DT:
            @staticmethod
            def now(tz=None):
                captured["tz"] = tz
                return datetime(2026, 6, 15, tzinfo=timezone.utc)

        with patch.object(fas, "datetime", _DT):
            put_attachment(
                feedback_id=FEEDBACK_ID,
                content=JPEG_BYTES,
                content_type="image/jpeg",
                backend=local_backend,
            )
        assert captured["tz"] is timezone.utc


# ---------------------------------------------------------------------------
# AC#4 — upload validation (size + content_type + feedback_id)
# ---------------------------------------------------------------------------


class TestUploadValidation:
    def test_oversize_rejected(self, local_backend):
        oversize = b"x" * (10 * 1024 * 1024 + 1)
        with pytest.raises(FeedbackAttachmentSizeError):
            put_attachment(
                feedback_id=FEEDBACK_ID,
                content=oversize,
                content_type="image/jpeg",
                backend=local_backend,
            )

    def test_exact_max_size_accepted(self, local_backend):
        at_limit = b"x" * (10 * 1024 * 1024)
        ref = put_attachment(
            feedback_id=FEEDBACK_ID,
            content=at_limit,
            content_type="image/jpeg",
            backend=local_backend,
        )
        assert ref.byte_size == 10 * 1024 * 1024


class TestContentTypeSentinel:
    """ADR-0049 §5.1 sentinel: allowlist drift rejection.

    SVG / HTML / JS / unknown MIME must be rejected at service boundary.
    If a future PR widens the allowlist (e.g. adding video/mp4 or
    image/heic), this test fails and forces the conversation through
    ADR amend + test update.
    """

    def test_allowed_set_pinned_to_adr0049(self):
        assert fas._ALLOWED_CONTENT_TYPES == frozenset(
            {
                "image/jpeg",
                "image/png",
                "image/webp",
                "application/pdf",
            }
        )

    @pytest.mark.parametrize(
        "bad_mime",
        [
            "image/svg+xml",  # SVG XSS vector
            "text/html",  # HTML smuggling
            "application/javascript",  # JS exec
            "image/heic",  # not in allowlist (iPhone format)
            "video/mp4",  # not in allowlist
            "video/quicktime",  # not in allowlist
            "application/zip",  # archive smuggling
            "",  # empty
            "IMAGE/JPEG",  # case sensitivity
        ],
    )
    def test_disallowed_mime_rejected(self, local_backend, bad_mime):
        with pytest.raises(FeedbackAttachmentContentTypeError):
            put_attachment(
                feedback_id=FEEDBACK_ID,
                content=JPEG_BYTES,
                content_type=bad_mime,
                backend=local_backend,
            )

    def test_svg_rejection_does_not_create_blob(self, local_backend):
        with pytest.raises(FeedbackAttachmentContentTypeError):
            put_attachment(
                feedback_id=FEEDBACK_ID,
                content=b"<svg onload='alert(1)'/>",
                content_type="image/svg+xml",
                backend=local_backend,
            )
        # No blob written
        assert list(local_backend.root.rglob("*")) == []


class TestFeedbackIdInputDefense:
    @pytest.mark.parametrize(
        "bad_id",
        [
            "",  # empty
            "a" * 65,  # too long
            "../../etc/passwd",  # traversal attempt
            "fb/../../etc",  # mid traversal
            "fb id with spaces",  # spaces
            "fb\x00null",  # NUL
            "fb\nstuff",  # newline
            "fb|pipe",  # pipe
            "fb;cmd",  # shell injection
        ],
    )
    def test_invalid_feedback_id_rejected(self, local_backend, bad_id):
        with pytest.raises(FeedbackAttachmentContentTypeError):
            put_attachment(
                feedback_id=bad_id,
                content=JPEG_BYTES,
                content_type="image/jpeg",
                backend=local_backend,
            )


# ---------------------------------------------------------------------------
# Hash-based dedup → idempotent re-upload
# ---------------------------------------------------------------------------


class TestHashDedup:
    def test_identical_bytes_returns_already_exists(self, local_backend):
        ref1 = put_attachment(
            feedback_id=FEEDBACK_ID,
            content=JPEG_BYTES,
            content_type="image/jpeg",
            backend=local_backend,
        )
        assert ref1.already_exists is False

        # Re-upload same bytes → same blob_path → already_exists
        ref2 = put_attachment(
            feedback_id=FEEDBACK_ID,
            content=JPEG_BYTES,
            content_type="image/jpeg",
            backend=local_backend,
        )
        assert ref2.already_exists is True
        assert ref2.blob_path == ref1.blob_path

    def test_different_bytes_different_blob_path(self, local_backend):
        ref1 = put_attachment(
            feedback_id=FEEDBACK_ID,
            content=JPEG_BYTES,
            content_type="image/jpeg",
            backend=local_backend,
        )
        ref2 = put_attachment(
            feedback_id=FEEDBACK_ID,
            content=JPEG_BYTES + b"DIFFERENT",
            content_type="image/jpeg",
            backend=local_backend,
        )
        assert ref1.blob_path != ref2.blob_path
        assert ref1.already_exists is False
        assert ref2.already_exists is False


# ---------------------------------------------------------------------------
# Traversal defense (relies on LocalStorageBackend allow_subdirs + _safe_key)
# ---------------------------------------------------------------------------


class TestTraversalDefense:
    """Defense in depth: feedback_id validator + backend _safe_key.

    Even if a future refactor weakens the feedback_id regex, the storage
    backend's _safe_key will still reject traversal attempts at the
    storage boundary. These tests exercise the *combined* defense.
    """

    def test_traversal_in_feedback_id_blocked_at_service_layer(self, local_backend):
        with pytest.raises(FeedbackAttachmentContentTypeError):
            put_attachment(
                feedback_id="../../../etc/passwd",
                content=JPEG_BYTES,
                content_type="image/jpeg",
                backend=local_backend,
            )

    def test_signed_url_for_evil_blob_path_blocked_at_backend(self, local_backend):
        # If caller fakes a blob_path with traversal, sign_read_url
        # funnels through _safe_key (S3-DEV-000B / PR #196) → rejection.
        from app.exceptions import BadRequestException

        with pytest.raises(BadRequestException):
            get_attachment_signed_url(
                "../../../etc/passwd",
                FeedbackViewerRole.USER,
                backend=local_backend,
            )


# ---------------------------------------------------------------------------
# Signed URL TTL per role
# ---------------------------------------------------------------------------


class TestSignedUrl:
    def test_user_role_ttl_15min(self, local_backend):
        ref = put_attachment(
            feedback_id=FEEDBACK_ID,
            content=JPEG_BYTES,
            content_type="image/jpeg",
            backend=local_backend,
        )
        signed = get_attachment_signed_url(
            ref.blob_path,
            FeedbackViewerRole.USER,
            backend=local_backend,
            now=1_000_000,
        )
        assert signed.expires_at == 1_000_000 + 15 * 60

    def test_companion_role_ttl_30min(self, local_backend):
        ref = put_attachment(
            feedback_id=FEEDBACK_ID,
            content=JPEG_BYTES,
            content_type="image/jpeg",
            backend=local_backend,
        )
        signed = get_attachment_signed_url(
            ref.blob_path,
            FeedbackViewerRole.COMPANION,
            backend=local_backend,
            now=1_000_000,
        )
        assert signed.expires_at == 1_000_000 + 30 * 60

    def test_admin_role_ttl_5min(self, local_backend):
        ref = put_attachment(
            feedback_id=FEEDBACK_ID,
            content=JPEG_BYTES,
            content_type="image/jpeg",
            backend=local_backend,
        )
        signed = get_attachment_signed_url(
            ref.blob_path,
            FeedbackViewerRole.ADMIN,
            backend=local_backend,
            now=1_000_000,
        )
        assert signed.expires_at == 1_000_000 + 5 * 60

    def test_signed_url_contains_blob_path(self, local_backend):
        ref = put_attachment(
            feedback_id=FEEDBACK_ID,
            content=JPEG_BYTES,
            content_type="image/jpeg",
            backend=local_backend,
        )
        signed = get_attachment_signed_url(
            ref.blob_path,
            FeedbackViewerRole.USER,
            backend=local_backend,
            now=1_000_000,
        )
        # Encoded blob_path round-trips into the signed URL template
        assert ref.blob_path in signed.url


# ---------------------------------------------------------------------------
# OSError classification (same shape as contract_storage)
# ---------------------------------------------------------------------------


class _FaultyBackend(LocalStorageBackend):
    def __init__(self, root_dir, raise_errno):
        super().__init__(root_dir=root_dir, allow_subdirs=True)
        self._raise_errno = raise_errno

    def put_if_absent(self, key, content, *, content_type, metadata=None):
        err = OSError("injected")
        err.errno = self._raise_errno
        raise err


class TestOSErrorClassification:
    @pytest.mark.parametrize(
        "raised_errno,expected_label",
        [
            (errno.EACCES, "EACCES"),
            (errno.EROFS, "EROFS"),
            (errno.ENOSPC, "ENOSPC"),
            (errno.EIO, "OTHER"),
        ],
    )
    def test_oserror_mapped_to_label_and_raised(self, tmp_path, raised_errno, expected_label):
        faulty = _FaultyBackend(tmp_path, raise_errno=raised_errno)
        with pytest.raises(FeedbackAttachmentPutError) as exc_info:
            put_attachment(
                feedback_id=FEEDBACK_ID,
                content=JPEG_BYTES,
                content_type="image/jpeg",
                backend=faulty,
            )
        assert exc_info.value.errno_label == expected_label
        assert isinstance(exc_info.value.__cause__, OSError)
