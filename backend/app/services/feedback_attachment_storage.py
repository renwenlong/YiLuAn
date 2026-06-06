"""Feedback attachment storage (S3-DEV-004-FEEDBACK-STORAGE / ADR-0049 §5.1).

# Design pattern: Service module + composition (NOT ABC subclass)

ADR-0049 §5.1 literally writes
``class FeedbackAttachmentStorageBackend(StorageBackend)``, but the
ADR-0046 §3.1 amendment (PR #194) established the codebase convention:
storage **business logic** (namespace / content-type allowlist / size
limits / metadata convention) lives in a **service module** that
composes ``get_storage_backend()`` rather than subclassing
``StorageBackend``. See:

- ``certification_image.py`` (S2-DEV-016) — flat namespace service
- ``contract_storage.py`` (S3-DEV-001) — WORM contract service

The same reasons apply here (and arguably more strongly than contract
storage, since feedback attachments have richer per-mime validation
and a hash-based dedup story):

1. **codebase consistency** — three storage domains (cert / contract /
   feedback) all use the service-module pattern. A fourth dev wiring
   ``class XxxStorageBackend(StorageBackend)`` immediately raises a
   review flag.
2. **ABC stays minimal** — ``StorageBackend`` is only
   ``put`` / ``put_if_absent`` / ``sign_read_url`` / ``open`` /
   ``verify_sig`` / ``parse_uri``. Per-domain allowlist + size +
   dedup hash are *not* storage-backend concerns; they're
   business-policy concerns.
3. **mock simplicity** — tests inject a backend; we never need to mock
   a second ABC subclass.
4. **opt-in subdirs** — ``feedback/{YYYY}/{MM}/...`` reuses
   ``LocalStorageBackend(allow_subdirs=True)`` (S3-DEV-000B), no fork.

# Layered defense for SVG XSS / mime smuggling

| Layer | Defense |
|-------|---------|
| 1. Storage | ``_ALLOWED_CONTENT_TYPES`` allowlist; SVG / HTML / JS rejected |
| 2. App     | ``put_attachment`` re-asserts content_type + size before put |
| 3. Hash    | ``content_hash[:16]`` in blob path → dedup + tamper-evident |
| 4. Sign    | TTL signed URL only; raw blob never served by FastAPI directly |

# OSError responsibility split (same as contract_storage)

``StorageBackend.put_if_absent`` only guarantees create-or-already-exists.
Callers (this module) catch ``OSError`` and partition:

- ``errno.EEXIST`` → not possible (backend already maps to
  ``already_exists=True``); defensive branch retained.
- ``errno.EACCES`` / ``errno.EROFS`` / ``errno.ENOSPC`` → re-raise as
  :class:`FeedbackAttachmentStoragePutError`, increment
  ``feedback_attachment_put_error_total{errno=<NAME>}``.
- Other ``OSError`` → re-raise with ``errno="OTHER"`` label.
"""

from __future__ import annotations

import errno
import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from app.config import settings
from app.services.storage_backend import (
    LocalStorageBackend,
    SignedReadURL,
    StorageBackend,
    StoragePutResult,
    StoredObject,
    get_storage_backend,
)
from app.utils.metrics import contract_storage_put_error_total

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


_NAMESPACE_PREFIX = "feedback"  # 与 ``cert/`` / ``contracts/`` 隔离

# ADR-0049 §5.1 allowlist — 拒绝 SVG / HTML / JS / 任何脚本类 MIME
_ALLOWED_CONTENT_TYPES = frozenset(
    {
        "image/jpeg",
        "image/png",
        "image/webp",
        "application/pdf",
    }
)

# ADR-0049 §5.1 max size — 10 MiB
_MAX_SIZE_BYTES = 10 * 1024 * 1024

# Filename extension whitelist — what we'll allow in the blob path suffix.
# Independent of content_type allowlist so a misnamed PDF cannot smuggle
# in an unexpected extension. Maps lowercase content_type → canonical ext.
_CONTENT_TYPE_TO_EXT: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
}

# Feedback attachment local root (separate from cert images + contracts so
# RBAC / cleanup / size accounting stay independent). Tests monkeypatch.
FEEDBACK_ATTACHMENT_LOCAL_DIR = (
    Path(__file__).parent.parent.parent / "private" / "feedback-attachments"
)

# Viewer role → signed URL TTL (seconds). Conservative defaults.
_VIEWER_TTL_SECONDS: dict[str, int] = {
    "user": 15 * 60,  # 15min — user re-viewing own attachment
    "companion": 30 * 60,  # 30min — companion reviewing flagged feedback
    "admin": 5 * 60,  # 5min — audit access, least exposure
}


class FeedbackViewerRole(str, Enum):
    """Who is reading the signed feedback attachment URL."""

    USER = "user"
    COMPANION = "companion"
    ADMIN = "admin"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class FeedbackAttachmentContentTypeError(ValueError):
    """Rejected because content_type is not in :data:`_ALLOWED_CONTENT_TYPES`.

    Sentinel against SVG XSS / HTML / JS smuggling. Any extension of the
    allowlist must update both ADR-0049 §5.1 and the test sentinel
    :class:`TestFeedbackContentTypeSentinel`.
    """


class FeedbackAttachmentSizeError(ValueError):
    """Rejected because byte count > :data:`_MAX_SIZE_BYTES`."""


class FeedbackAttachmentPutError(RuntimeError):
    """Raised when storage put failed for a non-EEXIST IO reason."""

    def __init__(self, message: str, *, errno_label: str) -> None:
        super().__init__(message)
        self.errno_label = errno_label


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FeedbackAttachmentRef:
    """Reference to a stored feedback attachment.

    Returned by :func:`put_attachment`. Combines the persisted blob ref
    with the structural metadata callers need to write a
    ``feedback_attachments`` row (S3-DEV-004-FEEDBACK-DOMAIN owns the
    table; this module only stages the blob and returns its address).
    """

    stored: StoredObject
    blob_path: str  # e.g. "feedback/2026/06/<feedback_id>_<hash16>.jpg"
    content_hash: str  # SHA-256 hex of bytes (full 64-char)
    content_type: str
    byte_size: int
    already_exists: bool  # True → idempotent re-upload of identical bytes


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


_FEEDBACK_ID_RE = re.compile(r"^[0-9A-Za-z_-]{1,64}$")
"""Restrictive regex for feedback_id (UUID hex / ULID / safe string).

We never embed user-controlled feedback_id into the blob path without
this check — even with subdir traversal defense at the storage layer,
defense in depth means caller input also gets a length + charset cap.
"""


def _assert_content_type_allowed(content_type: str) -> None:
    if content_type not in _ALLOWED_CONTENT_TYPES:
        raise FeedbackAttachmentContentTypeError(
            f"feedback storage rejects {content_type!r}; "
            f"allowlist = {sorted(_ALLOWED_CONTENT_TYPES)}"
        )


def _assert_size_within(byte_size: int) -> None:
    if byte_size > _MAX_SIZE_BYTES:
        raise FeedbackAttachmentSizeError(
            f"feedback attachment {byte_size} bytes exceeds limit "
            f"{_MAX_SIZE_BYTES} bytes (10 MiB)"
        )


def _assert_feedback_id_safe(feedback_id: str) -> None:
    if not feedback_id or not _FEEDBACK_ID_RE.match(feedback_id):
        raise FeedbackAttachmentContentTypeError(
            f"feedback_id must match [0-9A-Za-z_-]{{1,64}}; got {feedback_id!r}"
        )


def _utc_year_month() -> tuple[str, str]:
    """Return ``(YYYY, MM)`` zero-padded UTC strings (NOT local timezone)."""
    now = datetime.now(timezone.utc)
    return f"{now.year:04d}", f"{now.month:02d}"


def _build_blob_path(feedback_id: str, content_hash: str, content_type: str) -> str:
    """Construct ``feedback/{YYYY}/{MM}/{feedback_id}_{hash16}.{ext}``.

    ADR-0049 §5.1: blob path encodes feedback_id (FK back-pointer) +
    content_hash[:16] (idempotency + tamper-evident) + canonical ext
    (from content_type, not user filename — defense against ext spoofing).
    """
    year, month = _utc_year_month()
    ext = _CONTENT_TYPE_TO_EXT[content_type]
    short_hash = content_hash[:16]
    return f"{_NAMESPACE_PREFIX}/{year}/{month}/{feedback_id}_{short_hash}{ext}"


def _errno_label(err: OSError) -> str:
    if err.errno == errno.EACCES:
        return "EACCES"
    if err.errno == errno.EROFS:
        return "EROFS"
    if err.errno == errno.ENOSPC:
        return "ENOSPC"
    return "OTHER"


def _resolve_backend() -> StorageBackend:
    """Return the right backend for feedback storage.

    Mirror of ``contract_storage._resolve_backend``:
    - ``settings.storage_backend == 'azure'`` → process-wide singleton
    - else → local backend with ``allow_subdirs=True`` pointed at
      ``FEEDBACK_ATTACHMENT_LOCAL_DIR``.
    """
    backend_name = (getattr(settings, "storage_backend", "local") or "local").lower()
    if backend_name == "azure":
        return get_storage_backend()
    return LocalStorageBackend(
        root_dir=FEEDBACK_ATTACHMENT_LOCAL_DIR,
        allow_subdirs=True,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def put_attachment(
    *,
    feedback_id: str,
    content: bytes,
    content_type: str,
    backend: StorageBackend | None = None,
) -> FeedbackAttachmentRef:
    """Persist a feedback attachment after content-type + size validation.

    Layered defense:
    1. ``_assert_content_type_allowed`` — SVG / HTML / JS rejected here
    2. ``_assert_size_within`` — 10 MiB cap (ADR-0049 §5.1)
    3. ``_assert_feedback_id_safe`` — restrictive charset cap
    4. Hash dedup — identical bytes → same blob_path → ``already_exists``
    5. Blob path uses canonical ext from content_type, not user filename
       (defense against ext spoofing)

    Args:
        feedback_id: Feedback PK (UUID hex / ULID / safe id, ≤64 chars).
        content: Raw bytes; size capped at 10 MiB.
        content_type: Must be in :data:`_ALLOWED_CONTENT_TYPES`.
        backend: Optional injection for testing; defaults to
            :func:`_resolve_backend`.

    Returns:
        :class:`FeedbackAttachmentRef` with stored blob ref + blob_path +
        content_hash (64-char) + canonical content_type + byte_size +
        ``already_exists`` flag (True iff the exact bytes were uploaded
        before).

    Raises:
        FeedbackAttachmentContentTypeError: bad content_type or feedback_id
        FeedbackAttachmentSizeError: bytes exceed 10 MiB limit
        FeedbackAttachmentPutError: backend put failed for non-EEXIST OSError
    """
    _assert_feedback_id_safe(feedback_id)
    _assert_content_type_allowed(content_type)
    byte_size = len(content)
    _assert_size_within(byte_size)

    if backend is None:
        backend = _resolve_backend()

    content_hash = hashlib.sha256(content).hexdigest()
    blob_path = _build_blob_path(feedback_id, content_hash, content_type)
    metadata = {
        "domain": "feedback",
        "feedback_id": feedback_id,
        "content_hash": content_hash,
        "content_type": content_type,
    }
    try:
        result: StoragePutResult = backend.put_if_absent(
            blob_path,
            content,
            content_type=content_type,
            metadata=metadata,
        )
    except OSError as err:
        label = _errno_label(err)
        # Reuse the contract counter (same shape) for now; if/when
        # ops want per-domain dashboards we can split into a
        # feedback_attachment_put_error_total counter via a small follow-up.
        contract_storage_put_error_total.labels(errno=label).inc()
        logger.error(
            "feedback_attachment.put_failed",
            extra={
                "blob_path": blob_path,
                "errno_label": label,
                "errno": err.errno,
                "feedback_id": feedback_id,
            },
        )
        raise FeedbackAttachmentPutError(
            f"feedback attachment put failed: errno={label}",
            errno_label=label,
        ) from err

    return FeedbackAttachmentRef(
        stored=result.stored,
        blob_path=blob_path,
        content_hash=content_hash,
        content_type=content_type,
        byte_size=byte_size,
        already_exists=result.already_exists,
    )


def get_attachment_signed_url(
    blob_path: str,
    viewer_role: FeedbackViewerRole,
    *,
    backend: StorageBackend | None = None,
    now: int | None = None,
) -> SignedReadURL:
    """Return a signed read URL for a feedback attachment.

    TTL depends on role:
    - USER: 15 min (re-viewing own attachment)
    - COMPANION: 30 min (reviewing flagged feedback during shift)
    - ADMIN: 5 min (audit access, principle of least exposure)
    """
    if backend is None:
        backend = _resolve_backend()
    ttl_seconds = _VIEWER_TTL_SECONDS[viewer_role.value]
    obj = StoredObject(scheme=backend.scheme, key=blob_path)
    return backend.sign_read_url(obj, ttl_seconds=ttl_seconds, now=now)


__all__ = [
    "FEEDBACK_ATTACHMENT_LOCAL_DIR",
    "FeedbackAttachmentContentTypeError",
    "FeedbackAttachmentPutError",
    "FeedbackAttachmentRef",
    "FeedbackAttachmentSizeError",
    "FeedbackViewerRole",
    "get_attachment_signed_url",
    "put_attachment",
]
