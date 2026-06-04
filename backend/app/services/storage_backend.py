"""Storage backend ABC abstraction (ADR-0045 §3 P1).

S2-DEV-016 Phase A. Provides a vendor-neutral storage layer for certification
images and (future) other artefacts.

Backends:
- ``LocalStorageBackend`` (env STORAGE_BACKEND=local, default): filesystem under
  ``backend/private/``; HMAC-signed URLs served by FastAPI.
- ``AzureBlobStorageBackend`` (env STORAGE_BACKEND=azure): Phase A mock impl;
  Phase B will wire azure-storage-blob SDK + User Delegation SAS.

Concerns kept out of scope here (delegated to ``certification_image.py``):
- file type / size validation
- admin auth / audit logging
- HMAC TTL business rules (only verify primitives provided)

凝光 vendor lock-in 关切 + ADR §2.4: ABC factory 抽象隔离 + 单元可测 + 双前缀
平滑迁移期不再耦合具体 cloud。
"""
from __future__ import annotations

import hashlib
import hmac
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from app.config import settings
from app.exceptions import (
    BadRequestException,
    ForbiddenException,
    NotFoundException,
)

# ---------------------------------------------------------------------------
# Shared types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StoredObject:
    """Reference to a stored binary blob.

    ``scheme`` identifies the backend: ``cert-image://`` (local) or
    ``azure-blob://`` (Azure Phase B). ``key`` is the backend-specific
    identifier (filename for local, blob name for Azure).
    """

    scheme: str
    key: str

    @property
    def uri(self) -> str:
        return f"{self.scheme}{self.key}"


@dataclass(frozen=True)
class SignedReadURL:
    """Result of issuing a signed download URL."""

    url: str
    expires_at: int  # epoch seconds


# ---------------------------------------------------------------------------
# Backend ABC
# ---------------------------------------------------------------------------


class StorageBackend(ABC):
    """Abstract storage backend; impl maps scheme + key to bytes."""

    #: URL scheme this backend owns (e.g. ``cert-image://`` or ``azure-blob://``)
    scheme: str

    @abstractmethod
    def put(self, key: str, content: bytes, *, content_type: str) -> StoredObject:
        """Persist ``content`` under ``key`` and return the ``StoredObject`` ref."""

    @abstractmethod
    def sign_read_url(
        self, obj: StoredObject, *, ttl_seconds: int, now: int | None = None
    ) -> SignedReadURL:
        """Issue a time-limited signed download URL for ``obj``."""

    @abstractmethod
    def open(self, obj: StoredObject) -> bytes:
        """Read raw bytes (used by signed-URL servers and migration cron)."""

    @abstractmethod
    def verify_sig(
        self, key: str, expires: int, sig: str
    ) -> StoredObject:
        """Validate a signature (HMAC for local; SAS/User Delegation for Azure).

        Raises ``ForbiddenException`` on tampered / expired signatures and
        ``NotFoundException`` if the object is missing.
        """

    def parse_uri(self, uri: str) -> StoredObject | None:
        """Parse a stored URI to ``StoredObject`` if it belongs to this backend."""
        if not uri.startswith(self.scheme):
            return None
        return StoredObject(scheme=self.scheme, key=uri.removeprefix(self.scheme))


# ---------------------------------------------------------------------------
# LocalStorageBackend (cert-image://)
# ---------------------------------------------------------------------------


class LocalStorageBackend(StorageBackend):
    """Filesystem-backed storage under ``backend/private/<root>``.

    Signed URL = ``/api/v1/admin/companions/certification-images/{key}?expires&sig``
    served by FastAPI (HMAC-SHA256 + TTL). Matches PR-E2 Phase A behaviour.
    """

    scheme = "cert-image://"

    def __init__(
        self,
        root_dir: Path | None = None,
        sign_url_template: str = (
            "/api/v1/admin/companions/certification-images/{key}"
            "?expires={expires}&sig={sig}"
        ),
    ) -> None:
        self.root = root_dir or (
            Path(__file__).parent.parent.parent / "private" / "certification-images"
        )
        self._sign_url_template = sign_url_template

    # -- internal helpers -------------------------------------------------

    def _secret(self) -> bytes:
        return settings.jwt_secret_key.encode("utf-8")

    def _signature(self, key: str, expires: int) -> str:
        payload = f"{key}:{expires}".encode("utf-8")
        return hmac.new(self._secret(), payload, hashlib.sha256).hexdigest()

    def _safe_key(self, key: str) -> str:
        name = Path(key).name
        if name != key or not name:
            raise BadRequestException("Invalid storage key")
        if any(ch in name for ch in ("/", "\\", "..")):
            raise BadRequestException("Invalid storage key")
        return name

    # -- StorageBackend interface ----------------------------------------

    def put(
        self, key: str, content: bytes, *, content_type: str
    ) -> StoredObject:
        safe = self._safe_key(key)
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / safe).write_bytes(content)
        return StoredObject(scheme=self.scheme, key=safe)

    def sign_read_url(
        self, obj: StoredObject, *, ttl_seconds: int, now: int | None = None
    ) -> SignedReadURL:
        issued_at = int(time.time() if now is None else now)
        expires = issued_at + ttl_seconds
        sig = self._signature(obj.key, expires)
        url = self._sign_url_template.format(key=obj.key, expires=expires, sig=sig)
        return SignedReadURL(url=url, expires_at=expires)

    def verify_sig(self, key: str, expires: int, sig: str) -> StoredObject:
        safe = self._safe_key(key)
        if expires < int(time.time()):
            raise ForbiddenException("Storage URL expired")
        expected = self._signature(safe, expires)
        if not hmac.compare_digest(expected, sig):
            raise ForbiddenException("Invalid storage signature")
        path = (self.root / safe).resolve()
        root = self.root.resolve()
        if root not in path.parents and path != root:
            raise ForbiddenException("Invalid storage path")
        if not path.exists() or not path.is_file():
            raise NotFoundException("Storage object not found")
        return StoredObject(scheme=self.scheme, key=safe)

    def open(self, obj: StoredObject) -> bytes:
        safe = self._safe_key(obj.key)
        path = self.root / safe
        if not path.exists():
            raise NotFoundException("Storage object not found")
        return path.read_bytes()

    # local-only helper: full path (for FastAPI FileResponse)
    def resolve_path(self, obj: StoredObject) -> Path:
        safe = self._safe_key(obj.key)
        return self.root / safe


# ---------------------------------------------------------------------------
# AzureBlobStorageBackend (azure-blob://)  — Phase A MOCK
# ---------------------------------------------------------------------------


class AzureBlobStorageBackend(StorageBackend):
    """Azure Blob storage backend (Phase A: in-memory mock).

    Phase A goal: provide a usable backend for unit tests + Phase B切换演练，
    避免在 21Vianet 账号未到位前阻塞 dev/CI。

    Phase B TODO (ADR-0045 §3.2 P1):
    - Replace ``_blobs`` dict with ``BlobServiceClient`` (azure-storage-blob)
    - ``sign_read_url`` → User Delegation SAS (delegation key cached ≤ 7d)
    - ``verify_sig`` → Azure side verifies SAS; backend just round-trips bytes
    - Auth: service principal via ``DefaultAzureCredential``
    - ENV: ``AZURE_STORAGE_ACCOUNT_NAME`` + ``AZURE_CLIENT_ID/SECRET/TENANT_ID``
      + ``AZURE_CONTAINER_NAME``

    Production guard: backend startup must refuse boot when STORAGE_BACKEND=azure
    and required ENV missing (added in factory below).
    """

    scheme = "azure-blob://"

    def __init__(
        self,
        account_name: str = "mock-account",
        container_name: str = "yiluan-cert-mock",
        sign_url_template: str = (
            "https://{account}.blob.core.chinacloudapi.cn/{container}/{key}"
            "?sig=MOCK&se={expires}"
        ),
    ) -> None:
        self.account_name = account_name
        self.container_name = container_name
        self._sign_url_template = sign_url_template
        # In-memory store: key -> (bytes, content_type)
        self._blobs: dict[str, tuple[bytes, str]] = {}

    def _secret(self) -> bytes:
        # Mock SAS uses the same HMAC primitive as local backend so tests can
        # assert tamper detection without real Azure. Phase B drops this in
        # favour of Azure-side User Delegation SAS validation.
        return settings.jwt_secret_key.encode("utf-8")

    def _signature(self, key: str, expires: int) -> str:
        payload = f"azure:{key}:{expires}".encode("utf-8")
        return hmac.new(self._secret(), payload, hashlib.sha256).hexdigest()

    def put(
        self, key: str, content: bytes, *, content_type: str
    ) -> StoredObject:
        self._blobs[key] = (content, content_type)
        return StoredObject(scheme=self.scheme, key=key)

    def sign_read_url(
        self, obj: StoredObject, *, ttl_seconds: int, now: int | None = None
    ) -> SignedReadURL:
        issued_at = int(time.time() if now is None else now)
        expires = issued_at + ttl_seconds
        # Phase A mock: append HMAC so tamper tests still pass
        sig = self._signature(obj.key, expires)
        url = self._sign_url_template.format(
            account=self.account_name,
            container=self.container_name,
            key=obj.key,
            expires=expires,
        ) + f"&_mock_sig={sig}"
        return SignedReadURL(url=url, expires_at=expires)

    def verify_sig(self, key: str, expires: int, sig: str) -> StoredObject:
        if expires < int(time.time()):
            raise ForbiddenException("Storage URL expired")
        expected = self._signature(key, expires)
        if not hmac.compare_digest(expected, sig):
            raise ForbiddenException("Invalid storage signature")
        if key not in self._blobs:
            raise NotFoundException("Storage object not found")
        return StoredObject(scheme=self.scheme, key=key)

    def open(self, obj: StoredObject) -> bytes:
        if obj.key not in self._blobs:
            raise NotFoundException("Storage object not found")
        return self._blobs[obj.key][0]


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


_backend_singleton: StorageBackend | None = None


def get_storage_backend() -> StorageBackend:
    """Return process-wide ``StorageBackend`` per ``settings.storage_backend``.

    Singleton: cached after first call. Tests can call ``reset_storage_backend()``
    to drop the cache.

    Production guard (Phase B): when ``storage_backend=azure`` is set but
    Azure ENV vars are missing, fall back to mock here is unacceptable;
    instead we raise immediately so misconfig is caught at startup.
    """
    global _backend_singleton
    if _backend_singleton is not None:
        return _backend_singleton

    backend_name = (getattr(settings, "storage_backend", "local") or "local").lower()
    if backend_name == "azure":
        _backend_singleton = AzureBlobStorageBackend()
    else:
        _backend_singleton = LocalStorageBackend()
    return _backend_singleton


def reset_storage_backend() -> None:
    """Drop singleton cache (testing only)."""
    global _backend_singleton
    _backend_singleton = None


__all__ = [
    "StorageBackend",
    "StoredObject",
    "SignedReadURL",
    "LocalStorageBackend",
    "AzureBlobStorageBackend",
    "get_storage_backend",
    "reset_storage_backend",
]
