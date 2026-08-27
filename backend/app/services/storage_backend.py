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

S3-DEV-000B amendment (2026-06-06):
    ``LocalStorageBackend`` gained an opt-in ``allow_subdirs`` flag so
    downstream stores (contract WORM, feedback attachments) can use nested
    ``namespace/{year}/{month}/...`` paths while preserving cert-image flat
    namespace. ``_safe_key`` defends both modes against traversal / absolute
    paths / control chars / whitespace edges. All key-handling methods
    (``put`` / ``put_if_absent`` / ``sign_read_url`` / ``verify_sig`` /
    ``open`` / ``resolve_path``) funnel through ``_safe_key``; see
    ``TestLocalAllowSubdirs::test_all_key_handling_methods_call_safe_key``
    sentinel guarding future refactors. Refs: S3-DEV-000B-STORAGE-SUBDIR-SUPPORT.
"""
from __future__ import annotations

import hashlib
import hmac
import os
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


@dataclass(frozen=True)
class StoragePutResult:
    """Result of a (conditional) blob put.

    Returned by :meth:`StorageBackend.put_if_absent` to indicate whether the
    write created a new object or hit an existing one. ``already_exists=True``
    is **not** an error and must not raise — callers (合同/反馈 WORM 写入路径)
    rely on this for idempotency without ``try/except FileExistsError`` noise.

    Attributes:
        stored: Reference to the persisted (or pre-existing) blob.
        already_exists: ``True`` if the key was already present and the new
            ``body`` was rejected; ``False`` if the put created the object.
    """

    stored: StoredObject
    already_exists: bool = False


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
    def put_if_absent(
        self,
        key: str,
        content: bytes,
        *,
        content_type: str,
        metadata: dict[str, str] | None = None,
    ) -> StoragePutResult:
        """Persist ``content`` under ``key`` **only if it does not already exist**.

        Used by WORM blob paths (合同 PDF / 用户反馈附件 hash 命名) to guarantee
        idempotent writes without overwriting prior content. ADR-0046 §3.3 +
        ADR-0049 §5.1 require this primitive.

        Returns:
            :class:`StoragePutResult` with ``already_exists=False`` when the
            blob was newly created, ``already_exists=True`` when an existing
            blob matched ``key`` and was **not** overwritten. Callers must not
            rely on byte-equality of the existing blob — only on the fact that
            the key is now stable.

        Raises:
            BadRequestException: ``key`` fails backend validation.
            Backend-level IO errors should propagate (caller decides retry).
        """

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
        *,
        allow_subdirs: bool = False,
    ) -> None:
        self.root = root_dir or (
            Path(__file__).parent.parent.parent / "private" / "certification-images"
        )
        self._sign_url_template = sign_url_template
        # S3-DEV-001 (ADR-0046 §3.1): contract storage needs nested
        # ``contracts/{year}/{month}/...`` paths. Opt-in only; cert-image flat
        # namespace stays unchanged.
        self._allow_subdirs = allow_subdirs

    # -- internal helpers -------------------------------------------------

    def _secret(self) -> bytes:
        return settings.jwt_secret_key.encode("utf-8")

    def _signature(self, key: str, expires: int) -> str:
        payload = f"{key}:{expires}".encode("utf-8")
        return hmac.new(self._secret(), payload, hashlib.sha256).hexdigest()

    def _safe_key(self, key: str) -> str:
        if not key:
            raise BadRequestException("Invalid storage key")
        # Always reject backslash + .. anywhere, regardless of mode
        if "\\" in key or ".." in key:
            raise BadRequestException("Invalid storage key")
        # S3-DEV-000B AC#2: leading/trailing whitespace anywhere is suspicious
        # (often path-injection / spoof). Reject up-front before mode split.
        if key != key.strip():
            raise BadRequestException("Invalid storage key")
        if not self._allow_subdirs:
            # Legacy single-level mode (cert image): no '/' allowed.
            name = Path(key).name
            if name != key or not name:
                raise BadRequestException("Invalid storage key")
            return name
        # Subdir mode (contract storage, ADR-0046 §3.1):
        # Allow '/' separators but defend against traversal / abs path /
        # control chars / empty segments / per-segment whitespace edges.
        if key.startswith("/"):
            raise BadRequestException("Invalid storage key")
        segments = key.split("/")
        for seg in segments:
            if not seg or seg in {".", ".."}:
                raise BadRequestException("Invalid storage key")
            if seg != seg.strip():
                # leading/trailing whitespace inside a segment
                raise BadRequestException("Invalid storage key")
            # Reject NUL + control chars (0x00..0x1F) anywhere in segment
            if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in seg):
                raise BadRequestException("Invalid storage key")
        return key

    # -- StorageBackend interface ----------------------------------------

    def put(
        self, key: str, content: bytes, *, content_type: str
    ) -> StoredObject:
        safe = self._safe_key(key)
        path = self.root / safe
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return StoredObject(scheme=self.scheme, key=safe)

    def put_if_absent(
        self,
        key: str,
        content: bytes,
        *,
        content_type: str,
        metadata: dict[str, str] | None = None,
    ) -> StoragePutResult:
        # ``metadata`` is accepted for API parity with Azure; LocalStorage
        # has no separate metadata channel (filesystem xattr support is
        # platform-dependent and not required for current call sites).
        del metadata
        del content_type
        safe = self._safe_key(key)
        path = self.root / safe
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            # O_CREAT | O_EXCL gives kernel-level atomic create-or-fail.
            # No TOCTOU between exists()-check and write_bytes(): the open
            # itself fails with FileExistsError on race.
            fd = os.open(
                path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o600,
            )
        except FileExistsError:
            return StoragePutResult(
                stored=StoredObject(scheme=self.scheme, key=safe),
                already_exists=True,
            )
        try:
            with os.fdopen(fd, "wb") as fp:
                fp.write(content)
        except Exception:
            # Partial write: best-effort cleanup so a retry can re-create.
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
            raise
        return StoragePutResult(
            stored=StoredObject(scheme=self.scheme, key=safe),
            already_exists=False,
        )

    def sign_read_url(
        self, obj: StoredObject, *, ttl_seconds: int, now: int | None = None
    ) -> SignedReadURL:
        # S3-DEV-000B (AC#4): all key-handling methods must funnel through
        # ``_safe_key`` so traversal/control-char defense is uniform across
        # the surface area (put / put_if_absent / sign_read_url / verify_sig
        # / open / resolve_path). Caller-supplied ``obj.key`` is not trusted.
        safe = self._safe_key(obj.key)
        issued_at = int(time.time() if now is None else now)
        expires = issued_at + ttl_seconds
        sig = self._signature(safe, expires)
        url = self._sign_url_template.format(key=safe, expires=expires, sig=sig)
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
    """Azure Blob storage backend (Phase B: real SDK + Phase A mock fallback).

    Dual-mode (S2-DEV-016-PHASE-B-PREFLIGHT-SDK):
    - **Real SDK mode**: when a ``blob_service_client`` (``BlobServiceClient``)
      is injected, all IO goes through ``azure-storage-blob``. Used in
      production (creds via ENV) and azurite integration tests.
    - **Mock mode**: when no client is injected, an in-memory ``dict`` emulates
      blob storage. Keeps dev/CI independent of cloud credentials and lets
      Phase A unit tests run unchanged.

    Auth (Phase B, ADR-0045 §3.2): production constructs the client from
    ``DefaultAzureCredential`` (service principal via ``AZURE_CLIENT_ID`` /
    ``AZURE_CLIENT_SECRET`` / ``AZURE_TENANT_ID``) or a connection string; see
    ``_build_azure_client`` in the factory section.

    SAS (Phase B): ``sign_read_url`` issues a real **User Delegation SAS** in
    SDK mode (delegation key fetched via ``get_user_delegation_key``); mock mode
    keeps the HMAC stub so tamper/expiry unit tests still pass.

    WORM (Phase B): ``set_worm_policy`` calls Azure immutability APIs
    (``set_immutability_policy`` + ``set_legal_hold``). azurite does NOT support
    immutability (Azure/Azurite Issue #2648), so its dedicated test is
    skip-marked; real enforcement is verified by the REAL task's smoke after
    creds land.
    """

    scheme = "azure-blob://"

    # WORM retention for contract/feedback artefacts (7 years, ADR-0046 §3.5).
    _WORM_RETENTION_DAYS = 2555

    def __init__(
        self,
        account_name: str = "mock-account",
        container_name: str = "yiluan-cert-mock",
        account_url: str | None = None,
        *,
        blob_service_client: object | None = None,
    ) -> None:
        self.account_name = account_name
        self.account_url = (
            account_url or f"https://{account_name}.blob.core.windows.net"
        ).rstrip("/")
        self.container_name = container_name
        # Real SDK client (BlobServiceClient) when injected; else None -> mock.
        self._client = blob_service_client
        # In-memory store (mock mode only): key -> (bytes, content_type)
        self._blobs: dict[str, tuple[bytes, str]] = {}
        # Cached User Delegation key (SDK mode), refreshed on expiry.
        self._delegation_key: object | None = None

    @property
    def is_real_sdk(self) -> bool:
        """True when a real ``BlobServiceClient`` is wired (vs in-memory mock)."""
        return self._client is not None

    def _container_client(self) -> object:
        return self._client.get_container_client(self.container_name)

    def _blob_client(self, key: str) -> object:
        return self._client.get_blob_client(
            container=self.container_name, blob=key
        )

    def _secret(self) -> bytes:
        # Mock SAS uses the same HMAC primitive as local backend so tests can
        # assert tamper detection without real Azure. SDK mode uses real SAS.
        return settings.jwt_secret_key.encode("utf-8")

    def _signature(self, key: str, expires: int) -> str:
        payload = f"azure:{key}:{expires}".encode("utf-8")
        return hmac.new(self._secret(), payload, hashlib.sha256).hexdigest()

    # -- StorageBackend interface ----------------------------------------

    def put(
        self, key: str, content: bytes, *, content_type: str
    ) -> StoredObject:
        if self._client is None:
            self._blobs[key] = (content, content_type)
            return StoredObject(scheme=self.scheme, key=key)
        # Real SDK: upload + overwrite (put is unconditional by contract).
        from azure.storage.blob import ContentSettings

        bc = self._blob_client(key)
        bc.upload_blob(
            content,
            overwrite=True,
            content_settings=ContentSettings(content_type=content_type),
        )
        return StoredObject(scheme=self.scheme, key=key)

    def put_if_absent(
        self,
        key: str,
        content: bytes,
        *,
        content_type: str,
        metadata: dict[str, str] | None = None,
    ) -> StoragePutResult:
        if self._client is None:
            # Mock: dict-membership emulates ``If-None-Match: *``.
            del metadata
            if key in self._blobs:
                return StoragePutResult(
                    stored=StoredObject(scheme=self.scheme, key=key),
                    already_exists=True,
                )
            self._blobs[key] = (content, content_type)
            return StoragePutResult(
                stored=StoredObject(scheme=self.scheme, key=key),
                already_exists=False,
            )
        # Real SDK: ``If-None-Match: *`` => 409/412 when blob exists.
        from azure.core.exceptions import ResourceExistsError
        from azure.storage.blob import ContentSettings

        bc = self._blob_client(key)
        try:
            bc.upload_blob(
                content,
                overwrite=False,
                metadata=metadata or None,
                content_settings=ContentSettings(content_type=content_type),
            )
        except ResourceExistsError:
            return StoragePutResult(
                stored=StoredObject(scheme=self.scheme, key=key),
                already_exists=True,
            )
        return StoragePutResult(
            stored=StoredObject(scheme=self.scheme, key=key),
            already_exists=False,
        )

    def set_worm_policy(
        self, key: str, *, retention_days: int | None = None
    ) -> None:
        """Apply WORM (immutability + legal hold) to an existing blob.

        SDK mode only: calls Azure ``set_immutability_policy`` (locked,
        time-based retention) + ``set_legal_hold``. Requires a
        version-level-immutability or immutability-policy-enabled container.

        NOTE: azurite does NOT support immutability (Azure/Azurite Issue
        #2648); the dedicated test is skip-marked and real enforcement is
        verified by the REAL task smoke after creds land.

        Mock mode: no-op (no immutability semantics in dict store).
        """
        if self._client is None:
            return
        from datetime import datetime, timedelta, timezone

        from azure.storage.blob import ImmutabilityPolicy

        days = retention_days or self._WORM_RETENTION_DAYS
        bc = self._blob_client(key)
        expiry = datetime.now(timezone.utc) + timedelta(days=days)
        policy = ImmutabilityPolicy(
            expiry_time=expiry, policy_mode="Locked"
        )
        bc.set_immutability_policy(immutability_policy=policy)
        bc.set_legal_hold(True)

    def _get_delegation_key(self, start: object, expiry: object) -> object:
        """Fetch (and cache) a User Delegation key for SAS signing (SDK mode)."""
        return self._client.get_user_delegation_key(
            key_start_time=start, key_expiry_time=expiry
        )

    def sign_read_url(
        self, obj: StoredObject, *, ttl_seconds: int, now: int | None = None
    ) -> SignedReadURL:
        issued_at = int(time.time() if now is None else now)
        expires = issued_at + ttl_seconds
        if self._client is None:
            # Mock: append HMAC so tamper tests still pass.
            sig = self._signature(obj.key, expires)
            url = (
                f"{self.account_url}/{self.container_name}/{obj.key}"
                f"?sig=MOCK&se={expires}&_mock_sig={sig}"
            )
            return SignedReadURL(url=url, expires_at=expires)
        # Real SDK: User Delegation SAS (no account key needed; uses AAD).
        from datetime import datetime, timezone

        from azure.storage.blob import (
            BlobSasPermissions,
            generate_blob_sas,
        )

        start_dt = datetime.now(timezone.utc)
        expiry_dt = datetime.fromtimestamp(expires, tz=timezone.utc)
        delegation_key = self._get_delegation_key(start_dt, expiry_dt)
        sas = generate_blob_sas(
            account_name=self.account_name,
            container_name=self.container_name,
            blob_name=obj.key,
            user_delegation_key=delegation_key,
            permission=BlobSasPermissions(read=True),
            expiry=expiry_dt,
            start=start_dt,
        )
        base = f"{self.account_url}/{self.container_name}/{obj.key}"
        return SignedReadURL(url=f"{base}?{sas}", expires_at=expires)

    def verify_sig(self, key: str, expires: int, sig: str) -> StoredObject:
        # Mock mode validates the HMAC stub; SDK mode delegates trust to Azure
        # (SAS is validated server-side), so we only confirm the blob exists.
        if expires < int(time.time()):
            raise ForbiddenException("Storage URL expired")
        if self._client is None:
            expected = self._signature(key, expires)
            if not hmac.compare_digest(expected, sig):
                raise ForbiddenException("Invalid storage signature")
            if key not in self._blobs:
                raise NotFoundException("Storage object not found")
            return StoredObject(scheme=self.scheme, key=key)
        # Real SDK: existence check (SAS itself is Azure-verified).
        from azure.core.exceptions import ResourceNotFoundError

        bc = self._blob_client(key)
        try:
            bc.get_blob_properties()
        except ResourceNotFoundError as exc:
            raise NotFoundException("Storage object not found") from exc
        return StoredObject(scheme=self.scheme, key=key)

    def open(self, obj: StoredObject) -> bytes:
        if self._client is None:
            if obj.key not in self._blobs:
                raise NotFoundException("Storage object not found")
            return self._blobs[obj.key][0]
        # Real SDK: download bytes.
        from azure.core.exceptions import ResourceNotFoundError

        bc = self._blob_client(obj.key)
        try:
            stream = bc.download_blob()
            return stream.readall()
        except ResourceNotFoundError as exc:
            raise NotFoundException("Storage object not found") from exc


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


_backend_singleton: StorageBackend | None = None


_AZURE_CHINA_DOMAIN = "china" + "cloudapi.cn"


def _validated_azure_account_url() -> str:
    """Return the configured Azure Global account URL or fail closed."""
    from urllib.parse import urlparse

    account = (getattr(settings, "azure_storage_account_name", "") or "").strip()
    account_url = (
        getattr(settings, "azure_storage_account_url", "") or ""
    ).strip().rstrip("/")
    authority = os.getenv("AZURE_AUTHORITY_HOST", "").lower()
    if _AZURE_CHINA_DOMAIN in account_url.lower() or _AZURE_CHINA_DOMAIN in authority:
        raise RuntimeError("Azure Global configuration required; Azure China is rejected")
    if not account or not account_url:
        raise RuntimeError(
            "STORAGE_BACKEND=azure requires AZURE_STORAGE_ACCOUNT_NAME and "
            "AZURE_STORAGE_ACCOUNT_URL"
        )
    parsed = urlparse(account_url)
    expected_host = f"{account}.blob.core.windows.net"
    if (
        parsed.scheme != "https"
        or parsed.hostname != expected_host
        or parsed.path not in ("", "/")
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        raise RuntimeError(
            "AZURE_STORAGE_ACCOUNT_URL must be the Azure Global endpoint "
            f"https://{expected_host}"
        )
    return account_url


def _build_azure_client(account_url: str | None = None) -> object:
    """Construct a real ``BlobServiceClient`` from Azure Global config."""
    from azure.storage.blob import BlobServiceClient

    resolved_account_url = account_url or _validated_azure_account_url()
    conn = (getattr(settings, "azure_storage_connection_string", "") or "").strip()
    if _AZURE_CHINA_DOMAIN in conn.lower():
        raise RuntimeError("Azure Global configuration required; Azure China is rejected")
    if conn:
        return BlobServiceClient.from_connection_string(conn)

    from azure.identity import DefaultAzureCredential

    return BlobServiceClient(
        account_url=resolved_account_url, credential=DefaultAzureCredential()
    )


def get_storage_backend() -> StorageBackend:
    """Return process-wide ``StorageBackend`` per ``settings.storage_backend``.

    Singleton: cached after first call. Tests can call ``reset_storage_backend()``
    to drop the cache.

    Production guard (Phase B): when ``storage_backend=azure`` is set but
    Azure ENV vars are missing, falling back to mock here is unacceptable;
    instead we raise immediately so misconfig is caught at startup.
    """
    global _backend_singleton
    if _backend_singleton is not None:
        return _backend_singleton

    backend_name = (getattr(settings, "storage_backend", "local") or "local").lower()
    if backend_name == "azure":
        account_url = _validated_azure_account_url()
        client = _build_azure_client(account_url)
        account = settings.azure_storage_account_name.strip()
        container = (
            getattr(settings, "azure_storage_container_cert", "") or "yiluan-cert-mock"
        ).strip() or "yiluan-cert-mock"
        _backend_singleton = AzureBlobStorageBackend(
            account_name=account,
            account_url=account_url,
            container_name=container,
            blob_service_client=client,
        )
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
    "StoragePutResult",
    "LocalStorageBackend",
    "AzureBlobStorageBackend",
    "get_storage_backend",
    "reset_storage_backend",
]
