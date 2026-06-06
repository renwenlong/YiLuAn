"""Contract PDF WORM storage service (S3-DEV-001 / ADR-0046 §3).

# Design pattern: Service module + composition (not ABC subclass)

ADR-0046 §3.1 literally writes `class ContractStorageBackend(StorageBackend)`
(继承), but codebase precedent (``certification_image.py``) uses **service
module + composition**: get a backend instance via ``get_storage_backend()``
and wrap it with domain-specific helpers (namespace / WORM / ViewerRole TTL).

Reasons we chose composition here:

1. **factory reuse** — ``get_storage_backend()`` already returns the right
   Local/Azure singleton; no duplicate factory branch.
2. **mock simplicity** — tests can ``monkeypatch get_storage_backend`` once
   instead of plumbing a second ABC subclass through the DI graph.
3. **0 new backend class** — Azure account_name / container_name / sign URL
   template all live on ``AzureBlobStorageBackend``; ``ContractStorage``
   never owns blob bytes directly, only adds policy on top.
4. **WORM is orthogonal** — ``set_immutability_policy`` is an Azure-side
   side effect after a successful ``put_if_absent``, not a different way to
   write bytes. A subclass would have to ``super().put_if_absent`` then add
   the policy call — same code, one indirection deeper.
5. **ViewerRole TTL** — different TTL per role is a *call-site* concern, not
   a *backend* concern; service module is the right home.

Follow-up: a thin ADR-0046 patch note (post-merge) should record the chosen
service-module pattern so future readers see the rationale without grepping.

# Layered defense (ADR-0046 §3.3)

| Layer | Defense |
|-------|---------|
| 1. Storage | Azure immutable policy Locked 7y (prod), even owner key cannot delete/overwrite |
| 2. App     | ``put_contract`` uses ``put_if_absent``; Azure ``If-None-Match: *``; idempotent |
| 3. DB      | ``service_contracts.contract_hash`` UNIQUE; ``is_immutable`` TRUE; UPDATE rejects |
| 4. API     | No ``PUT /admin/contracts/{id}``; admin GET only |

This module owns Layer 1 + Layer 2.

# OSError responsibility split (魈 AC#6 + 刻晴 D1)

``StorageBackend.put_if_absent`` only guarantees create-or-already-exists.
**Callers (this module) must** catch ``OSError`` and partition:

- ``errno.EEXIST`` → not possible here (backend already maps to
  ``already_exists=True``), but defensive branch retained.
- ``errno.EACCES`` / ``errno.EROFS`` / ``errno.ENOSPC`` → re-raise as
  :class:`ContractStoragePutError`, increment
  ``contract_storage_put_error_total{errno=<NAME>}``, log for admin alert.
- Other ``OSError`` → re-raise as :class:`ContractStoragePutError` with
  ``errno="OTHER"`` label.
"""

from __future__ import annotations

import errno
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from app.config import settings
from app.services.storage_backend import (
    AzureBlobStorageBackend,
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
# Public types
# ---------------------------------------------------------------------------


SHA256_HEX_LEN = 64
_CONTRACT_HASH_RE = re.compile(r"^[0-9a-fA-F]+$")
_NAMESPACE_PREFIX = "contracts"  # 与 ``cert/`` 隔离 (ADR-0046 §3.1)
_RETENTION_DAYS = 365 * 7  # 7 年保留 (民法典合同存档)
_ALLOWED_CONTENT_TYPES = frozenset({"application/pdf"})  # 刻晴 D2: 哨兵

# Contract storage local root: separate from cert images so cleanup / size
# accounting / RBAC stay independent. Tests monkeypatch this.
CONTRACT_STORAGE_LOCAL_DIR = Path(__file__).parent.parent.parent / "private" / "contracts"


class ViewerRole(str, Enum):
    """Who is reading the signed contract URL — drives signed-URL TTL."""

    USER = "user"
    COMPANION = "companion"
    ADMIN = "admin"


# ViewerRole → signed URL TTL (seconds). Conservative defaults; tune per RT.
_VIEWER_TTL_SECONDS: dict[ViewerRole, int] = {
    ViewerRole.USER: 15 * 60,  # 15min — short-lived, user-side mobile flow
    ViewerRole.COMPANION: 30 * 60,  # 30min — companion may keep PDF open during job
    ViewerRole.ADMIN: 5 * 60,  # 5min — audit access, principle of least exposure
}


@dataclass(frozen=True)
class ContractStorageRef:
    """Reference to a stored contract PDF.

    Returned by :func:`put_contract`. Combines the persisted blob ref with
    structural metadata callers need to write a ``service_contracts`` row.
    """

    stored: StoredObject
    blob_path: str  # e.g. "contracts/2026/06/<order_id>_<hash>.pdf"
    contract_hash: str  # SHA-256 hex
    already_exists: bool  # True → put_if_absent matched existing (idempotent)
    immutability_applied: bool  # True → Azure Locked policy actually set


class ContractStoragePutError(RuntimeError):
    """Raised when contract PDF write fails for a non-EEXIST IO reason.

    ``__cause__`` carries the original ``OSError`` for log forensics.
    ``errno_label`` is the metric label already emitted before raise.
    """

    def __init__(self, message: str, *, errno_label: str) -> None:
        super().__init__(message)
        self.errno_label = errno_label


class ContractContentTypeError(ValueError):
    """Raised when content_type is not in :data:`_ALLOWED_CONTENT_TYPES`.

    刻晴 D2 sentinel: contract storage is PDF-only. Reject anything else
    (SVG XSS, HTML smuggling, etc.) at the service boundary.
    """


class ContractHashInputError(ValueError):
    """Raised when ``contract_hash`` arg is not a 64-char SHA-256 hex string.

    魈 AC#9: caller-side mistakes (None / empty / wrong length / bad chars)
    must fail loud before any IO happens.
    """


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _utc_year_month() -> tuple[str, str]:
    """Return ``(YYYY, MM)`` strings derived from current UTC time.

    魈 AC#8: blob_path partition uses UTC, never local timezone, to avoid
    cross-day/month/year skew between containers in different regions.
    """
    now = datetime.now(timezone.utc)
    return f"{now.year:04d}", f"{now.month:02d}"


def _build_blob_path(order_id: str, contract_hash: str) -> str:
    """Construct ``contracts/{YYYY}/{MM}/{order_id}_{hash}.pdf`` (ADR-0046 §3.1)."""
    year, month = _utc_year_month()
    return f"{_NAMESPACE_PREFIX}/{year}/{month}/{order_id}_{contract_hash}.pdf"


def _validate_contract_hash(contract_hash: str | None) -> str:
    """Validate ``contract_hash`` is a 64-char hex string (魈 AC#9)."""
    if not contract_hash:
        raise ContractHashInputError("contract_hash must be a non-empty string")
    if len(contract_hash) != SHA256_HEX_LEN:
        raise ContractHashInputError(
            f"contract_hash must be {SHA256_HEX_LEN} hex chars, got {len(contract_hash)}"
        )
    if not _CONTRACT_HASH_RE.match(contract_hash):
        raise ContractHashInputError("contract_hash must contain only hex digits (0-9a-fA-F)")
    return contract_hash


def _assert_content_type_allowed(content_type: str) -> None:
    """Reject non-PDF uploads (刻晴 D2 sentinel)."""
    if content_type not in _ALLOWED_CONTENT_TYPES:
        raise ContractContentTypeError(
            f"contract storage only accepts {sorted(_ALLOWED_CONTENT_TYPES)}, "
            f"got {content_type!r}"
        )


def _errno_label(err: OSError) -> str:
    """Map ``OSError.errno`` to a prometheus-safe label (魈 AC#6)."""
    if err.errno == errno.EACCES:
        return "EACCES"
    if err.errno == errno.EROFS:
        return "EROFS"
    if err.errno == errno.ENOSPC:
        return "ENOSPC"
    return "OTHER"


def _set_worm_policy_if_azure(backend: StorageBackend, blob_path: str) -> bool:
    """Apply Azure immutability policy (Locked, 7y) if conditions met.

    Conditions:
    - Backend is :class:`AzureBlobStorageBackend`
    - ``settings.s3_contract_immutability_enabled`` is True (魈 AC#7)

    Returns:
        True if policy was applied; False if skipped (Local backend or
        immutability disabled by env).

    Phase A (current): mock — records intent in ``backend._immutability``
    so tests can verify call-shape without a real Azure account.
    Phase B (post 21Vianet):
    ``container_client.set_immutability_policy(
        blob_name=blob_path,
        immutability_policy=ImmutabilityPolicy(
            expiry_time=datetime.now(tz=utc) + timedelta(days=2555),
            policy_mode='Locked',
        ),
    )``
    """
    if not isinstance(backend, AzureBlobStorageBackend):
        return False
    if not settings.s3_contract_immutability_enabled:
        logger.info(
            "contract_storage.worm_policy_skipped",
            extra={"reason": "S3_CONTRACT_IMMUTABILITY_ENABLED=false", "blob_path": blob_path},
        )
        return False
    # Phase A mock: stash policy on the backend instance so tests can assert.
    policy_log = getattr(backend, "_immutability_log", None)
    if policy_log is None:
        policy_log = []
        setattr(backend, "_immutability_log", policy_log)
    policy_log.append(
        {
            "blob_path": blob_path,
            "period_days": _RETENTION_DAYS,
            "policy_mode": "Locked",
        }
    )
    logger.info(
        "contract_storage.worm_policy_applied",
        extra={
            "blob_path": blob_path,
            "period_days": _RETENTION_DAYS,
            "policy_mode": "Locked",
        },
    )
    return True


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _resolve_backend() -> StorageBackend:
    """Return the right backend for contract storage.

    - ``settings.storage_backend == 'azure'`` → use the process-wide
      ``get_storage_backend()`` singleton (Azure mock / real SDK).
    - else → build a contract-only :class:`LocalStorageBackend` with
      ``allow_subdirs=True`` pointed at ``CONTRACT_STORAGE_LOCAL_DIR``.

    Mirrors the ``cert_image._local_backend_with_dir`` pattern so tests can
    monkeypatch ``CONTRACT_STORAGE_LOCAL_DIR`` without disturbing the cert
    image flat namespace.
    """
    backend_name = (getattr(settings, "storage_backend", "local") or "local").lower()
    if backend_name == "azure":
        return get_storage_backend()
    return LocalStorageBackend(
        root_dir=CONTRACT_STORAGE_LOCAL_DIR,
        allow_subdirs=True,
    )


def put_contract(
    *,
    order_id: str,
    contract_hash: str,
    pdf_bytes: bytes,
    template_version: str,
    backend: StorageBackend | None = None,
) -> ContractStorageRef:
    """WORM-write a contract PDF and return its storage reference.

    Args:
        order_id: Order primary key; goes into the blob path.
        contract_hash: SHA-256 hex (64 chars) of (template_version |
            canonical_order_snapshot). Must be pre-computed by caller
            (see ADR-0046 §3.2 — :mod:`app.services.contract_hash`).
        pdf_bytes: Rendered contract bytes. Service does **not** sniff or
            transform; caller owns generation.
        template_version: Template semver (e.g. ``"v1.0.0"``) stored as blob
            metadata for forensic recovery.
        backend: Optional ``StorageBackend`` injection; defaults to the
            process-wide ``get_storage_backend()`` singleton.

    Returns:
        :class:`ContractStorageRef` with the persisted (or pre-existing) blob
        ref, blob_path, contract_hash echo, ``already_exists`` flag, and
        ``immutability_applied`` flag (True when Azure Locked policy fired).

    Raises:
        ContractHashInputError: ``contract_hash`` not a 64-char hex string.
        ContractContentTypeError: (reserved; always raised for non-PDF if
            we add content_type arg in a future PR — current signature
            implies PDF so we don't take it as a param to keep callers honest).
        ContractStoragePutError: backend ``put_if_absent`` failed with
            non-EEXIST ``OSError`` (EACCES / EROFS / ENOSPC / OTHER).
    """
    contract_hash = _validate_contract_hash(contract_hash)
    # Content-type哨兵: caller can only call this fn for PDF bytes; we hardcode
    # 'application/pdf' as the contract content type. Future variants
    # (signed-pdf, pdf/a) must go through their own helper to keep the
    # allowlist explicit.
    content_type = "application/pdf"
    _assert_content_type_allowed(content_type)

    if backend is None:
        backend = _resolve_backend()

    blob_path = _build_blob_path(order_id, contract_hash)
    metadata = {
        "contract_hash": contract_hash,
        "template_version": template_version,
        "order_id": order_id,
    }
    try:
        result: StoragePutResult = backend.put_if_absent(
            blob_path,
            pdf_bytes,
            content_type=content_type,
            metadata=metadata,
        )
    except OSError as err:
        label = _errno_label(err)
        contract_storage_put_error_total.labels(errno=label).inc()
        logger.error(
            "contract_storage.put_failed",
            extra={
                "blob_path": blob_path,
                "errno_label": label,
                "errno": err.errno,
                "order_id": order_id,
            },
        )
        raise ContractStoragePutError(
            f"contract storage put failed: errno={label}",
            errno_label=label,
        ) from err

    immutability_applied = _set_worm_policy_if_azure(backend, blob_path)
    return ContractStorageRef(
        stored=result.stored,
        blob_path=blob_path,
        contract_hash=contract_hash,
        already_exists=result.already_exists,
        immutability_applied=immutability_applied,
    )


def get_contract_signed_url(
    blob_path: str,
    viewer_role: ViewerRole,
    *,
    backend: StorageBackend | None = None,
    now: int | None = None,
) -> SignedReadURL:
    """Return a signed read URL for a contract blob, TTL derived from role.

    Args:
        blob_path: Blob key as returned by :func:`put_contract` (the
            ``contracts/YYYY/MM/<order>_<hash>.pdf`` form).
        viewer_role: Who is consuming the URL; selects TTL bucket.
        backend: Optional injection (testing).
        now: Optional clock injection for deterministic tests.

    Returns:
        :class:`SignedReadURL` whose ``url`` is consumable by the matching
        backend (HTTPS SAS for Azure, ``/__media__/...`` HMAC URL for Local).
    """
    if backend is None:
        backend = _resolve_backend()
    ttl_seconds = _VIEWER_TTL_SECONDS[viewer_role]
    obj = StoredObject(scheme=backend.scheme, key=blob_path)
    return backend.sign_read_url(obj, ttl_seconds=ttl_seconds, now=now)


__all__ = [
    "CONTRACT_STORAGE_LOCAL_DIR",
    "ContractContentTypeError",
    "ContractHashInputError",
    "ContractStoragePutError",
    "ContractStorageRef",
    "SHA256_HEX_LEN",
    "ViewerRole",
    "get_contract_signed_url",
    "put_contract",
]
